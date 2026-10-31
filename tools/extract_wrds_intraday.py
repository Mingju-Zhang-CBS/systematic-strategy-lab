"""Run on WRDS Cloud with wrds and an explicit session calendar; output is PRIVATE.

Current-vintage consolidated records are not an archived point-in-time feed.
No keys, credentials, market orders or licensed observations are distributed.
"""
from pathlib import Path
import argparse
import json
import time
import hashlib
import pandas as pd
import wrds
from sqlalchemy.exc import SQLAlchemyError


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--calendar",type=Path,required=True,help="Explicit scheduled session CSV: session,open,close in UTC")
    parser.add_argument("--full",action="store_true",help="All scheduled 2016-2025 sessions; otherwise five audit dates")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    schedule=pd.read_csv(args.calendar,index_col='session',parse_dates=['session','open','close'])
    schedule['open']=pd.to_datetime(schedule['open'],utc=True)
    schedule['close']=pd.to_datetime(schedule['close'],utc=True)
    if not args.full:
        schedule=schedule.loc[pd.to_datetime(["2016-01-04","2019-11-29","2020-03-09","2023-12-29","2025-12-01"])]
    schedule.to_csv(args.output/"scheduled_calendar.csv")
    db=wrds.Connection()
    db.raw_sql("SELECT set_config('statement_timeout','90000',false)")
    receipts=[]
    for session,row in schedule.iterrows():
        stamp=session.strftime("%Y%m%d");schema=f"taqm_{session.year}"
        destination=args.output/stamp
        if (destination/"receipt.json").exists():
            receipts.append(json.loads((destination/"receipt.json").read_text()));continue
        destination.mkdir(exist_ok=True)
        started=time.perf_counter()
        opened=row['open'].tz_convert('America/New_York');closed=row['close'].tz_convert('America/New_York')
        close=closed.strftime("%H:%M:%S")
        trade_sql=f"""WITH t AS (
          SELECT sym_root,time_m,time_m_nano,tr_seqnum,price::double precision AS price,size,
                 COALESCE(tr_scond,'') AS cond,
                 floor((extract(epoch FROM time_m)-34200)/1800)::int AS bucket
          FROM {schema}.ctm_{stamp}
          WHERE sym_root=ANY(%s) AND (sym_suffix IS NULL OR trim(sym_suffix)='')
            AND time_m >= '09:30:00' AND time_m < %s::time
            AND tr_corr='00' AND price>0 AND size>0
        ), regular AS (SELECT * FROM t WHERE cond !~ '[^ @FI]')
        SELECT sym_root AS asset,bucket,sum(size)::double precision AS volume,
               sum(price*size)::double precision AS dollar_volume,
               (array_agg(price ORDER BY time_m DESC,time_m_nano DESC,tr_seqnum DESC)
                  FILTER (WHERE cond !~ '[^ @F]'))[1] AS close,
               min(time_m) AS first_trade,max(time_m) AS last_trade
        FROM regular GROUP BY sym_root,bucket ORDER BY sym_root,bucket"""
        open_sql=f"""SELECT DISTINCT ON (sym_root) sym_root AS asset,price::double precision AS open_price,
                 time_m AS opening_time,tr_scond,ex
           FROM {schema}.ctm_{stamp}
           WHERE sym_root=ANY(%s) AND (sym_suffix IS NULL OR trim(sym_suffix)='')
             AND time_m >= '09:30:00' AND time_m < '10:00:00' AND tr_corr='00' AND price>0 AND size>0
             AND ((sym_root='SPY' AND ex='P') OR (sym_root='QQQ' AND ex='Q'))
             AND position('Q' IN COALESCE(tr_scond,''))>0
           ORDER BY sym_root,time_m,time_m_nano,tr_seqnum"""
        columns=db.raw_sql("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",params=(schema,'complete_nbbo_'+stamp))
        nano='time_m_nano' if 'time_m_nano' in columns.column_name.to_list() else '0::smallint'
        closing_seconds=int((closed-closed.normalize()).total_seconds())
        # One scan replaces 52 repeated symbol scans. Selection windows and first
        # observation semantics are unchanged; old schema precision is explicit.
        quote_sql=f"""WITH source AS (
          SELECT sym_root AS asset,time_m,{nano} AS time_m_nano,
             extract(epoch FROM time_m)::double precision AS sec,
             best_bid::double precision AS bid,best_ask::double precision AS ask,
             best_bidsizeshares AS bid_size,best_asksizeshares AS ask_size,qu_cond AS condition
          FROM {schema}.complete_nbbo_{stamp}
          WHERE sym_root=ANY(%s) AND (sym_suffix IS NULL OR trim(sym_suffix)='')
            AND time_m>='10:00:00' AND time_m<=%s::time
            AND best_bid>0 AND best_ask>=best_bid AND best_bidsizeshares>0 AND best_asksizeshares>0
            AND qu_cond='R'
        ), selected AS (
          SELECT *,CASE WHEN sec>={closing_seconds}-59 THEN {closing_seconds}-60
                    ELSE floor((sec-34200)/1800)*1800+34200 END AS decision_sec,
             CASE WHEN sec>={closing_seconds} THEN 60
                  WHEN sec>={closing_seconds}-59 THEN 1
                  WHEN sec-34200-floor((sec-34200)/1800)*1800>=60 THEN 60 ELSE 1 END AS latency
          FROM source WHERE
             (sec<{closing_seconds}-60 AND
               ((sec-34200-floor((sec-34200)/1800)*1800 BETWEEN 1 AND 6)
                 OR (sec-34200-floor((sec-34200)/1800)*1800 BETWEEN 60 AND 65)))
             OR sec BETWEEN {closing_seconds}-59 AND {closing_seconds}-54
             OR sec={closing_seconds}
        ), ranked AS (
          SELECT *,dense_rank() OVER (PARTITION BY asset,decision_sec,latency ORDER BY time_m,time_m_nano) AS rn
          FROM selected
        ) SELECT asset,('00:00:00'::time+decision_sec*interval '1 second') AS decision,
                 latency,time_m,time_m_nano,bid,ask,bid_size,ask_size,condition
          FROM ranked WHERE rn<=2 ORDER BY asset,decision,latency,time_m,time_m_nano"""
        # Individual remote query errors are actual source failures, retained for review.
        try:
            bars=db.raw_sql(trade_sql,params=(['SPY','QQQ'],close))
            auctions=db.raw_sql(open_sql,params=(['SPY','QQQ'],))
            quotes=db.raw_sql(quote_sql,params=(['SPY','QQQ'],close))
        except SQLAlchemyError as error:
            receipt={"session":str(session.date()),"status":"source_query_failed","error":str(error)[:1500]}
            (destination/"failure.json").write_text(json.dumps(receipt,indent=2));receipts.append(receipt)
            (args.output/"progress.json").write_text(json.dumps(receipts,indent=2));continue
        bars=bars.merge(auctions,on='asset',how='left',validate='many_to_one')
        bars['bar_end']=[opened+pd.Timedelta(minutes=30*(int(k)+1)) for k in bars.bucket]
        bars['session_open']=opened;bars['session_close']=closed
        # Corporate actions must be independently joined before strategy evaluation.
        bars['cash_dividend']=float('nan');bars['split']=float('nan')
        quotes['quote_time']=[pd.NaT if pd.isna(t) else pd.Timestamp(str(session.date())+' '+str(t),tz='America/New_York')
                              +pd.Timedelta(nanoseconds=int(ns)) for t,ns in zip(quotes.time_m,quotes.time_m_nano)]
        quotes=quotes.dropna(subset=['quote_time'])
        # Two observations with conflicting same-time quotes have no resolvable feed order here.
        duplicate=quotes.duplicated(['asset','quote_time'],keep=False)
        unique=quotes.drop_duplicates(['asset','quote_time','bid','ask','bid_size','ask_size'])
        ambiguous=unique.duplicated(['asset','quote_time'],keep=False)
        unique.loc[ambiguous].to_csv(destination/'ambiguous_quotes.csv',index=False)
        unique=unique.loc[~ambiguous].sort_values(['asset','quote_time'])
        bars.to_csv(destination/'bars.csv',index=False);unique.to_csv(destination/'quotes.csv',index=False)
        receipt={"session":str(session.date()),"status":"extracted_not_strategy_ready",
                 "bar_rows":len(bars),"quote_rows":len(unique),"duplicate_request_rows":int(duplicate.sum()),
                 "ambiguous_quote_rows":int(ambiguous.sum()),"missing_auction_assets":int(bars.loc[bars.open_price.isna(),'asset'].nunique()),
                 "elapsed_seconds":time.perf_counter()-started,
                 "rights":"private WRDS/NYSE licensed data; aggregate publication rights not inferred",
                 "corporate_actions":"pending; blocks strategy evaluation",
                 "files":{n:hashlib.sha256((destination/n).read_bytes()).hexdigest() for n in ['bars.csv','quotes.csv']}}
        (destination/'receipt.json').write_text(json.dumps(receipt,indent=2));receipts.append(receipt)
        (args.output/'progress.json').write_text(json.dumps(receipts,indent=2))
        print(stamp,receipt['elapsed_seconds'],len(bars),len(unique),flush=True)
    db.close()


if __name__=='__main__':main()

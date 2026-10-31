"""Evidence checks, separate from trading rules and vendor observations."""
import numpy as np
import pandas as pd


def select_quote_sources(raw):
    """Select raw NBBO and explicitly self-NBBO CQM messages, retaining rejects.

    ``session`` is the source file's date, not a date inferred from a UTC clock.
    Source N uses UTP indicator 4; source C uses the dated CTA 1/G convention.
    This does not reconstruct an exchange book or infer the other NBBO side.
    """
    x = raw.copy()
    dates = pd.to_datetime(x.session)
    if (dates.isna().any() or dates.dt.tz is not None
            or not dates.eq(dates.dt.normalize()).all()
            or not x.raw_file.isin(['NBBO', 'CQM']).all()
            or not x.source.isin(['N', 'C']).all()):
        raise ValueError('Dated NBBO/CQM files and explicit SIP source required')
    ind = x.natbbo_ind.fillna('').astype(str)
    self_nbbo = (x.source.eq('N') & ind.eq('4')) | (
        x.source.eq('C') & ((dates.lt('2017-10-30') & ind.eq('1'))
                           | (dates.ge('2017-10-30') & ind.eq('G'))))
    eligible = x.raw_file.eq('NBBO') | (x.raw_file.eq('CQM') & self_nbbo)
    x['source_status'] = np.where(eligible, 'source_eligible', 'not_self_nbbo')
    keys = ['asset', 'session', 'sip_time', 'nano', 'sequence', 'source',
            'bid', 'ask', 'bid_lots', 'ask_lots', 'condition']
    selected = x.loc[eligible].drop_duplicates(keys).copy()
    # A repeated sequence with differing payloads is not resolved by file priority.
    conflict = selected.duplicated(['asset', 'session', 'source', 'sequence'], keep=False)
    bad_keys = selected.loc[conflict, ['asset', 'session', 'source', 'sequence']]
    if not bad_keys.empty:
        bad_index = pd.MultiIndex.from_frame(bad_keys)
        mask = pd.MultiIndex.from_frame(x[['asset', 'session', 'source', 'sequence']]).isin(bad_index)
        x.loc[eligible & mask, 'source_status'] = 'conflicting_sequence_payload'
    selected = selected.loc[~conflict].drop(columns='source_status')
    return selected.reset_index(drop=True), x


def resolve_dated_lots(master, assets):
    """Resolve one dated master file; never carry lot sizes across dates.

    Exact symbol_15 is a fallback only when root and suffix are absent. Prefix
    lookalikes and conflicting duplicate identities do not establish units.
    """
    m = master.copy()
    root = m.sym_root.fillna('').str.strip()
    suffix = m.sym_suffix.fillna('').str.strip()
    symbol = m.symbol_15.fillna('').str.strip()
    m['asset'] = root.where(root.ne(''), symbol)
    m = m.loc[suffix.eq('') & m.asset.isin(assets), ['asset', 'round_lot']].drop_duplicates()
    bad = (m.duplicated('asset', keep=False) | ~np.isfinite(m.round_lot)
           | (m.round_lot <= 0) | (m.round_lot % 1 != 0))
    return m.loc[~bad].rename(columns={'round_lot': 'lot_size'}).reset_index(drop=True)


def recover_quote_clusters(coarse, fine):
    """Recover only uniquely matched microsecond clusters from finer SIP records.

    Fine input has ``sip_time`` plus a 0..999 ns remainder, a dated ``lot_size``,
    lot quantities, ``source`` and ``sequence``. Callers must establish source
    identity and lot units; passing these checks does not authenticate a feed.
    Outputs include all recovered clock observations and every cluster decision.
    """
    c, f = coarse.copy(), fine.copy()
    if (not all(pd.Timestamp(t).tzinfo is not None for t in c.quote_time)
            or not all(pd.Timestamp(t).tzinfo is not None for t in f.sip_time)):
        raise ValueError('Explicit source timezones required before clock recovery')
    c['quote_time'] = pd.to_datetime(c.quote_time, utc=True, format='mixed')
    f['sip_time'] = pd.to_datetime(f.sip_time, utc=True, format='mixed')
    keys = ['asset', 'quote_time', 'bid', 'ask', 'bid_size', 'ask_size']
    numeric = ['bid', 'ask', 'bid_lots', 'ask_lots', 'lot_size', 'nano', 'sequence']
    integers = ['bid_lots', 'ask_lots', 'lot_size', 'nano', 'sequence']
    if (c.duplicated(keys).any() or not np.isfinite(c[keys[2:]]).all().all()
            or not np.isfinite(f[numeric]).all().all()
            or (f[integers] % 1 != 0).any().any() or not f.nano.between(0, 999).all()
            or (f[['bid_lots', 'ask_lots', 'lot_size']] <= 0).any().any()
            or (c[['bid', 'bid_size', 'ask_size']] <= 0).any().any()
            or (f.bid <= 0).any() or (c.ask < c.bid).any() or (f.ask < f.bid).any()
            or c.quote_time.isna().any() or f.sip_time.isna().any()
            or (c.quote_time.astype('int64') % 1000 != 0).any()
            or (f.sip_time.astype('int64') % 1000 != 0).any()
            or f.source.isna().any() or f.source.eq('').any()):
        raise ValueError('Unique coarse tuples, explicit lot units and valid micro/nanosecond clocks required')
    f['fine_time'] = f.sip_time + pd.to_timedelta(f.nano.astype('int64'), unit='ns')
    f['quote_time'] = f.fine_time.dt.round('us')
    f['bid_size'] = f.bid_lots * f.lot_size
    f['ask_size'] = f.ask_lots * f.lot_size
    selected, audit = [], []
    for (asset, clock), group in c.groupby(['asset', 'quote_time'], sort=True):
        raw = f.loc[f.asset.eq(asset) & f.quote_time.eq(clock)].copy()
        reason = 'matched_fine_clock'
        left = set(map(tuple, group[keys[2:]].to_numpy()))
        right = set(map(tuple, raw[keys[2:]].to_numpy()))
        ordered = raw.sort_values(['fine_time', 'sequence'])
        if len(raw) != len(group) or left != right:
            reason = 'tuple_coverage_mismatch'
        elif raw.duplicated(keys).any():
            reason = 'nonunique_fine_match'
        elif not raw.condition.eq('R').all():
            reason = 'quote_condition_unverified'
        elif (raw.nano == 500).any():
            reason = 'half_quantum_tie'
        elif raw.source.nunique() != 1 or raw.sequence.duplicated().any():
            reason = 'sequence_scope_ambiguous'
        elif not ordered.sequence.is_monotonic_increasing:
            reason = 'clock_sequence_disagreement'
        if reason == 'matched_fine_clock':
            # With identical full clocks, the first same-feed message is the
            # observable selected by the engine's first-at/after-request rule.
            out = ordered.drop_duplicates('fine_time', keep='first').copy()
            out['coarse_time'] = clock
            out['quote_time'] = out.fine_time
            selected.append(out[['asset', 'quote_time', 'bid', 'ask', 'bid_size', 'ask_size',
                                 'condition', 'source', 'sequence', 'coarse_time']])
        audit.append({'asset': asset, 'coarse_time': clock, 'coarse_rows': len(group),
                      'fine_rows': len(raw), 'status': reason,
                      'max_clock_difference_ns': None if raw.empty else int((raw.fine_time-clock).abs().max().value)})
    columns = ['asset', 'quote_time', 'bid', 'ask', 'bid_size', 'ask_size', 'condition',
               'source', 'sequence', 'coarse_time']
    recovered = pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(columns=columns)
    return recovered.sort_values(['asset', 'quote_time']).reset_index(drop=True), pd.DataFrame(audit)


def evaluate_action_evidence(evidence):
    """Assess analyst-verified facts; never infer publication from an ex-date.

    This is a schema/policy check, not automated source authentication. Preserve
    the original document, release listing and identity/amount comparison.
    """
    e = evidence.copy()
    if (not all(pd.Timestamp(t).tzinfo is not None for t in e.decision_at)
            or not all(pd.isna(t) or pd.Timestamp(t).tzinfo is not None for t in e.published_at)):
        raise ValueError('Explicit publication and decision timezones required')
    e['published_at'] = pd.to_datetime(e.published_at, utc=True, format='mixed')
    e['decision_at'] = pd.to_datetime(e.decision_at, utc=True, format='mixed')
    if (e.evidence_id.duplicated().any() or e.decision_at.isna().any()
            or not e.identity_verified.isin([True, False]).all()
            or not e.amount_verified.isin([True, False]).all()):
        raise ValueError('Unique evidence IDs, explicit decisions and verification flags required')
    reasons = []
    for row in e.itertuples():
        if row.kind != 'gross_cash_amount':
            reason = 'schedule_or_other_fact_not_amount'
        elif not row.identity_verified or not row.amount_verified:
            reason = 'identity_or_amount_unverified'
        elif row.currency != 'USD' or row.unit != 'gross_per_share':
            reason = 'currency_or_unit_mismatch'
        elif row.clock_basis not in ['exchange_release_timestamp', 'issuer_archive_timestamp']:
            reason = 'publication_clock_not_verified'
        elif not isinstance(row.source_sha256, str) or len(row.source_sha256) != 64:
            reason = 'document_fingerprint_missing'
        elif pd.isna(row.published_at) or row.published_at >= row.decision_at:
            reason = 'not_known_before_decision'
        else:
            reason = 'verified_before_decision'
        reasons.append(reason)
    e['evidence_status'] = reasons
    e['strict_usable'] = e.evidence_status.eq('verified_before_decision')
    return e

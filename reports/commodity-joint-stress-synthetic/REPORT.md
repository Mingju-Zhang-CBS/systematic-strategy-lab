# Longer outages, adverse prices and collateral pressure

INVENTED INPUTS. Nine scenarios × eight funded accounts = 72 dependent paths. All magnitudes and windows were fixed before results.

## Read the experiment correctly

Outages last 10/20 scheduled sessions; reserve can rise from 10% to 40% of gross. A 5%/10% additive leg-price step is adverse to the frozen baseline side, using its last available absolute USD settlement through d−2. Both spread members can move against their respective sides: this is a basis deformation, not a common parallel move. Steps persist after the outage rather than creating a favorable automatic rebound. Fixed annual cohorts and signs do not move or flip when the stressed account differs.

Historical signal directions, contract selection and unit-risk reference histories stay fixed. Shocked references affect actual VM, execution and collateral; only lagged shocked price history enters the gross price basis. This conditional fixed-policy test is not a fully re-estimated trading system or a calibrated market equilibrium. Missing quotes stay missing, negative references are allowed, and costs remain the original fixed assumptions.

Each account has its own baseline-directed adverse path. Cross-strategy alpha, a shared-market benchmark comparison and confidence intervals for such a premium would be inappropriate here; none are supplied. Earlier historical research and failed paths remain available.

## Every result, including stopped prefixes

|Case|Account|Primary status|End date|Min equity USD|Min free cash USD|Max collateral shortfall USD|
|---|---|---|---|---:|---:|---:|
|control|base/long_only|completed_exploratory_path|2022-12-30|947,429.74|688,932.50|0.00|
|outage10|base/long_only|completed_exploratory_path|2022-12-30|967,807.87|683,816.15|0.00|
|outage20|base/long_only|completed_exploratory_path|2022-12-30|980,178.49|690,169.96|0.00|
|margin4_20|base/long_only|completed_exploratory_path|2022-12-30|960,215.01|597,051.45|0.00|
|price5_margin4_20|base/long_only|completed_exploratory_path|2022-12-30|782,885.12|451,585.30|0.00|
|outage20_margin4|base/long_only|failed_proxy_collateral_shortfall|2021-01-05|999,170.00|-92,382.42|92,382.42|
|joint_outage10_price5_margin4|base/long_only|failed_proxy_collateral_shortfall|2021-01-05|869,605.87|-227,616.59|227,616.59|
|joint_outage20_price5_margin4|base/long_only|failed_proxy_collateral_shortfall|2021-01-05|869,605.87|-227,616.59|227,616.59|
|joint_outage20_price10_margin4|base/long_only|failed_proxy_collateral_shortfall|2021-01-05|733,648.03|-363,574.43|363,574.43|
|control|base/trend|completed_exploratory_path|2022-12-30|990,761.14|716,805.39|0.00|
|outage10|base/trend|completed_exploratory_path|2022-12-30|998,423.42|715,631.43|0.00|
|outage20|base/trend|completed_exploratory_path|2022-12-30|994,814.42|712,238.92|0.00|
|margin4_20|base/trend|completed_exploratory_path|2022-12-30|996,640.88|636,702.24|0.00|
|price5_margin4_20|base/trend|completed_exploratory_path|2022-12-30|844,359.33|495,263.53|0.00|
|outage20_margin4|base/trend|failed_proxy_collateral_shortfall|2021-01-05|999,170.00|-95,996.88|95,996.88|
|joint_outage10_price5_margin4|base/trend|failed_proxy_collateral_shortfall|2021-01-05|865,991.41|-254,157.28|254,157.28|
|joint_outage20_price5_margin4|base/trend|failed_proxy_collateral_shortfall|2021-01-05|865,991.41|-254,157.28|254,157.28|
|joint_outage20_price10_margin4|base/trend|failed_proxy_collateral_shortfall|2021-01-05|730,033.56|-416,964.29|416,964.29|
|control|base/carry|completed_exploratory_path|2022-12-30|859,832.64|609,623.54|0.00|
|outage10|base/carry|completed_exploratory_path|2022-12-30|778,348.10|574,048.40|0.00|
|outage20|base/carry|completed_exploratory_path|2022-12-30|818,691.26|593,493.26|0.00|
|margin4_20|base/carry|completed_exploratory_path|2022-12-30|874,537.98|475,296.70|0.00|
|price5_margin4_20|base/carry|completed_exploratory_path|2022-12-30|623,346.66|319,049.75|0.00|
|outage20_margin4|base/carry|failed_proxy_collateral_shortfall|2021-01-05|998,183.21|-146,997.87|146,997.87|
|joint_outage10_price5_margin4|base/carry|failed_proxy_collateral_shortfall|2021-01-05|856,144.17|-317,700.50|317,700.50|
|joint_outage20_price5_margin4|base/carry|failed_proxy_collateral_shortfall|2021-01-05|856,144.17|-317,700.50|317,700.50|
|joint_outage20_price10_margin4|base/carry|failed_proxy_collateral_shortfall|2021-01-05|714,105.13|-488,403.14|488,403.14|
|control|base/bm_outright|completed_exploratory_path|2022-12-30|929,416.37|648,727.22|0.00|
|outage10|base/bm_outright|completed_exploratory_path|2022-12-30|863,172.93|632,035.40|0.00|
|outage20|base/bm_outright|completed_exploratory_path|2022-12-30|916,817.68|645,487.85|0.00|
|margin4_20|base/bm_outright|completed_exploratory_path|2022-12-30|950,486.85|513,184.05|0.00|
|price5_margin4_20|base/bm_outright|completed_exploratory_path|2022-12-30|641,985.07|343,479.65|0.00|
|outage20_margin4|base/bm_outright|failed_proxy_collateral_shortfall|2021-01-05|999,382.50|-146,885.88|146,885.88|
|joint_outage10_price5_margin4|base/bm_outright|failed_proxy_collateral_shortfall|2021-01-05|857,945.75|-312,662.58|312,662.58|
|joint_outage20_price5_margin4|base/bm_outright|failed_proxy_collateral_shortfall|2021-01-05|857,945.75|-312,662.58|312,662.58|
|joint_outage20_price10_margin4|base/bm_outright|failed_proxy_collateral_shortfall|2021-01-05|716,120.75|-482,258.15|482,258.15|
|control|base/bm_spread|completed_exploratory_path|2022-12-30|994,476.67|742,752.27|0.00|
|outage10|base/bm_spread|completed_exploratory_path|2022-12-30|982,540.20|689,746.65|0.00|
|outage20|base/bm_spread|completed_exploratory_path|2022-12-30|984,948.93|691,843.66|0.00|
|margin4_20|base/bm_spread|completed_exploratory_path|2022-12-30|995,433.80|669,804.18|0.00|
|price5_margin4_20|base/bm_spread|completed_exploratory_path|2022-12-30|862,036.03|559,468.14|0.00|
|outage20_margin4|base/bm_spread|completed_exploratory_path|2022-12-30|986,874.28|172,295.14|0.00|
|joint_outage10_price5_margin4|base/bm_spread|completed_exploratory_path|2022-12-30|810,043.22|51,196.15|0.00|
|joint_outage20_price5_margin4|base/bm_spread|completed_exploratory_path|2022-12-30|846,419.48|51,196.15|0.00|
|joint_outage20_price10_margin4|base/bm_spread|failed_proxy_collateral_shortfall|2021-01-05|794,055.89|-71,771.99|71,771.99|
|control|base/trend_half|completed_exploratory_path|2022-12-30|494,917.21|365,343.90|0.00|
|outage10|base/trend_half|completed_exploratory_path|2022-12-30|498,225.60|357,575.65|0.00|
|outage20|base/trend_half|completed_exploratory_path|2022-12-30|496,718.50|348,288.74|0.00|
|margin4_20|base/trend_half|completed_exploratory_path|2022-12-30|497,196.14|350,510.60|0.00|
|price5_margin4_20|base/trend_half|completed_exploratory_path|2022-12-30|422,068.55|293,206.55|0.00|
|outage20_margin4|base/trend_half|failed_proxy_collateral_shortfall|2021-01-05|499,607.50|-17,887.25|17,887.25|
|joint_outage10_price5_margin4|base/trend_half|failed_proxy_collateral_shortfall|2021-01-05|436,500.59|-93,221.56|93,221.56|
|joint_outage20_price5_margin4|base/trend_half|failed_proxy_collateral_shortfall|2021-01-05|436,500.59|-93,221.56|93,221.56|
|joint_outage20_price10_margin4|base/trend_half|failed_proxy_collateral_shortfall|2021-01-05|372,280.43|-170,866.29|170,866.29|
|control|base/carry_half|completed_exploratory_path|2022-12-30|430,359.03|314,227.35|0.00|
|outage10|base/carry_half|completed_exploratory_path|2022-12-30|393,184.56|282,174.43|0.00|
|outage20|base/carry_half|completed_exploratory_path|2022-12-30|410,178.63|298,226.34|0.00|
|margin4_20|base/carry_half|completed_exploratory_path|2022-12-30|438,253.89|260,006.50|0.00|
|price5_margin4_20|base/carry_half|completed_exploratory_path|2022-12-30|325,396.50|206,238.24|0.00|
|outage20_margin4|base/carry_half|failed_proxy_collateral_shortfall|2021-01-05|498,971.16|-48,584.82|48,584.82|
|joint_outage10_price5_margin4|base/carry_half|failed_proxy_collateral_shortfall|2021-01-05|431,046.09|-130,551.64|130,551.64|
|joint_outage20_price5_margin4|base/carry_half|failed_proxy_collateral_shortfall|2021-01-05|431,046.09|-130,551.64|130,551.64|
|joint_outage20_price10_margin4|base/carry_half|failed_proxy_collateral_shortfall|2021-01-05|363,121.03|-212,518.45|212,518.45|
|control|delay_plus_3/carry|completed_exploratory_path|2022-12-30|864,887.15|614,678.05|0.00|
|outage10|delay_plus_3/carry|completed_exploratory_path|2022-12-30|794,557.59|571,590.40|0.00|
|outage20|delay_plus_3/carry|completed_exploratory_path|2022-12-30|843,082.86|614,014.17|0.00|
|margin4_20|delay_plus_3/carry|completed_exploratory_path|2022-12-30|886,913.43|488,403.81|0.00|
|price5_margin4_20|delay_plus_3/carry|completed_exploratory_path|2022-12-30|612,495.43|348,997.11|0.00|
|outage20_margin4|delay_plus_3/carry|failed_proxy_collateral_shortfall|2021-01-05|998,183.21|-146,997.87|146,997.87|
|joint_outage10_price5_margin4|delay_plus_3/carry|failed_proxy_collateral_shortfall|2021-01-05|856,144.17|-317,700.50|317,700.50|
|joint_outage20_price5_margin4|delay_plus_3/carry|failed_proxy_collateral_shortfall|2021-01-05|856,144.17|-317,700.50|317,700.50|
|joint_outage20_price10_margin4|delay_plus_3/carry|failed_proxy_collateral_shortfall|2021-01-05|714,105.13|-488,403.14|488,403.14|

Different stop dates imply different observed horizons. Prefix minima are diagnostics, not comparable full-period return/risk estimates. Severity need not monotonically rank ending dollars once accounts stop.

![Joint-stress completion and stops](completion.png)

![Minimum free cash](minimum_free_cash.png)

## Failure causes and paired exposure

![Overlapping failure flags](failure_flags.png)

The selected primary status follows the existing engine; all simultaneous equity, delivery-boundary and cash-shortfall events remain in all_failure_flags and the event logs. A 50% risk-buffer breach alone is not insolvency. No deadline extension, external top-up, new price floor or unobserved liquidation is used.

Both spread legs reduce equal units bounded by the weaker current offer and shared daily sides. A zero-capacity member blocks the paired fill. New risk is gated against both day-start and planned post-reduction inventory, retaining v0.7.1. Reserve is encumbered cash, not another expense: equity = prior equity + VM − costs. Terminal reconciliation uses shocked open-position marks together with shocked fills.

## Reproduction and evidence

Inspect FROZEN_RUN.json, FROZEN_COHORTS.csv, FROZEN_LEGS.csv, summary.csv and RUN_MANIFEST.json. Account price_events.csv records signed USD steps; its hypothetical full-baseline-leg impulse is not the account’s realized P&L. Compare actual pnl/holdings/trades, admissions, exit plans and stress budgets/sessions. terminal_inventory.csv preserves remaining legs, mark offsets, deadline, offered/used/remaining capacity, cash and every failure flag.

Reproduce: python -m strategy_lab.commodities.joint_report --fixture --output NEW_DIRECTORY. Licensed work uses --input PRIVATE_INPUT --cohorts FROZEN_PRIVATE_CSV --legs FROZEN_PRIVATE_LEGS; keep outputs private.

Scheduled calendars, current-vintage metadata and missing first-position archives remain limitations. Reserve is a proxy without historical SPAN/spread credits or broker add-ons. EOD paired references are not intraday queues, real close-out or proven tradability. This deterministic conditional stress has no occurrence-probability, worst-possible-shock or unseen-OOS claim. Only original code/methods/tests and invented inputs are public; licensed sources, anchors, event dates and all real derived findings stay private. Research direction was selected by Mingju Zhang; implementation/experiments were AI-assisted and unaided review remains separately tracked.

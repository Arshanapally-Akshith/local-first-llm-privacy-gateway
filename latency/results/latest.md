# Phase 7 Latency Harness Results

Commit: `ab7222a5368dd60e6c29f3f1863467c595522e3e`
Concurrency levels: 1, 2, 4, 8, 16
Steady-state repetitions per cell: 200 (+10 warm-up, discarded)
Per-request timeout: 120s

> measured-on-benchmark, not real traffic -- tier-hit rate is a property of this harness's own fixed workload matrix's PII density, not of real traffic (ARCHITECTURE.md, 'The cascade'). Every row below states its own concurrency level; this artifact never reports a p99 without one, per BUILD.md Phase 7. Cold start (n=10, a fresh process each time) is reported separately and is never folded into any steady-state row. A request that timed out (or otherwise failed to complete) within this run's --request-timeout ceiling is excluded from every latency percentile below and counted instead in that cell's own timeout_count/error_count -- a cell with a nonzero count completed fewer than n requests and that is itself part of the finding, not a gap silently papered over.

## Cold start

n=10 fresh processes. mean / p95 / p99 (cv) in ms, min / max also available in the JSON artifact. A small n makes p95/p99 here indicative only, not statistically robust.

`16659.4 / 20343.1 / 21500.8 (cv=0.13)` ms (min=14644.9, max=21790.3)

## Per-workload, per-concurrency results

Each latency column reports `mean / p95 / p99 (cv)` in ms, computed only over requests that actually completed (`n`) -- `timeout`/`error` counts are reported alongside, never folded into the percentiles. `tier_hit` is a categorical distribution over completed requests only. Each workload's table is followed by a per-tier TTFT breakdown (BUILD.md Phase 7 DoD: "Per-tier p50/p95/p99") -- TTFT with the window, grouped by which tier resolved the request, shown only for tier classes with at least one completed sample in that cell.

### baseline_clean

Zero-PII cost floor: a single short message with no detectable entity. Tier 1 and Tier 2 both still run and both find nothing -- the honest 'real traffic is mostly PII-free' case (ARCHITECTURE.md, 'The cascade').

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 1058.3 / 2085.0 / 2879.2 (cv=0.50) | 1056.6 / 2080.7 / 2875.6 (cv=0.50) | 1.4 / 3.0 / 3.0 (cv=0.48) | 0.1 / 0.2 / 0.3 (cv=0.36) | 1059.2 / 2086.6 / 2880.6 (cv=0.50) | neither=1.00 |
| 2 | 200 (200) | 0 | 0 | 1743.9 / 3320.4 / 4534.5 (cv=0.38) | 1742.3 / 3318.6 / 4532.3 (cv=0.38) | 1.3 / 2.0 / 2.4 (cv=0.39) | 0.1 / 0.1 / 0.1 (cv=0.43) | 1768.9 / 3322.1 / 4537.2 (cv=0.38) | neither=1.00 |
| 4 | 200 (200) | 0 | 0 | 3108.2 / 3995.4 / 4622.2 (cv=0.21) | 3106.2 / 3993.8 / 4620.6 (cv=0.21) | 1.3 / 2.0 / 2.0 (cv=0.37) | 0.0 / 0.1 / 0.1 (cv=0.41) | 3275.3 / 4128.9 / 4623.9 (cv=0.17) | neither=1.00 |
| 8 | 200 (200) | 0 | 0 | 5907.6 / 6802.3 / 7128.9 (cv=0.12) | 5906.1 / 6801.3 / 7127.5 (cv=0.12) | 1.3 / 2.0 / 2.1 (cv=0.44) | 0.0 / 0.0 / 0.0 (cv=0.45) | 6162.1 / 7136.2 / 7491.8 (cv=0.11) | neither=1.00 |
| 16 | 200 (200) | 0 | 0 | 12014.8 / 14036.5 / 14463.0 (cv=0.10) | 12013.4 / 14034.9 / 14461.9 (cv=0.10) | 1.2 / 2.0 / 2.1 (cv=0.37) | 0.0 / 0.0 / 0.0 (cv=0.37) | 12390.2 / 14266.4 / 14661.9 (cv=0.10) | neither=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | neither | 1058.3 / 2085.0 / 2879.2 (cv=0.50) |
| 2 | neither | 1743.9 / 3320.4 / 4534.5 (cv=0.38) |
| 4 | neither | 3108.2 / 3995.4 / 4622.2 (cv=0.21) |
| 8 | neither | 5907.6 / 6802.3 / 7128.9 (cv=0.12) |
| 16 | neither | 12014.8 / 14036.5 / 14463.0 (cv=0.10) |

### tier1_only

Deterministic-path cost: structured entities only (Aadhaar, PAN, card), no names/orgs/addresses.

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 888.3 / 1133.0 / 1155.6 (cv=0.15) | 885.0 / 1128.7 / 1152.1 (cv=0.15) | 3.0 / 4.0 / 5.0 (cv=0.24) | 0.3 / 0.5 / 0.5 (cv=0.21) | 890.3 / 1135.5 / 1157.9 (cv=0.15) | tier1_only=1.00 |
| 2 | 200 (200) | 0 | 0 | 1609.4 / 1864.3 / 2413.3 (cv=0.18) | 1606.1 / 1861.1 / 2410.2 (cv=0.18) | 3.0 / 4.0 / 4.1 (cv=0.22) | 0.2 / 0.3 / 0.5 (cv=0.35) | 1655.3 / 1888.7 / 2430.9 (cv=0.15) | tier1_only=1.00 |
| 4 | 200 (200) | 0 | 0 | 3265.7 / 3791.7 / 4289.2 (cv=0.13) | 3262.3 / 3789.8 / 4286.0 (cv=0.13) | 3.1 / 4.0 / 5.0 (cv=0.26) | 0.1 / 0.1 / 0.2 (cv=0.35) | 3418.5 / 4196.0 / 4486.8 (cv=0.11) | tier1_only=1.00 |
| 8 | 200 (200) | 0 | 0 | 6428.9 / 7778.5 / 8071.6 (cv=0.13) | 6425.5 / 7771.2 / 8068.9 (cv=0.13) | 3.1 / 4.0 / 5.0 (cv=0.23) | 0.0 / 0.1 / 0.1 (cv=0.25) | 6695.3 / 8073.5 / 8357.9 (cv=0.12) | tier1_only=1.00 |
| 16 | 200 (200) | 0 | 0 | 12971.8 / 15356.7 / 15588.0 (cv=0.12) | 12968.5 / 15353.7 / 15584.8 (cv=0.12) | 3.1 / 4.0 / 5.0 (cv=0.28) | 0.0 / 0.0 / 0.1 (cv=0.30) | 13382.4 / 15592.2 / 17379.6 (cv=0.12) | tier1_only=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | tier1_only | 888.3 / 1133.0 / 1155.6 (cv=0.15) |
| 2 | tier1_only | 1609.4 / 1864.3 / 2413.3 (cv=0.18) |
| 4 | tier1_only | 3265.7 / 3791.7 / 4289.2 (cv=0.13) |
| 8 | tier1_only | 6428.9 / 7778.5 / 8071.6 (cv=0.13) |
| 16 | tier1_only | 12971.8 / 15356.7 / 15588.0 (cv=0.12) |

### tier2_only

Model-inference cost: unstructured entities only (person, org, address), no structured entities.

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 849.4 / 938.7 / 1070.9 (cv=0.08) | 846.4 / 935.2 / 1067.2 (cv=0.08) | 2.7 / 4.0 / 4.1 (cv=0.72) | 0.3 / 0.4 / 0.5 (cv=0.78) | 851.2 / 940.6 / 1072.8 (cv=0.08) | tier2_only=1.00 |
| 2 | 200 (200) | 0 | 0 | 1574.4 / 1824.5 / 2580.5 (cv=0.20) | 1571.4 / 1820.7 / 2576.9 (cv=0.20) | 2.7 / 4.0 / 4.2 (cv=0.26) | 0.2 / 0.4 / 0.5 (cv=0.41) | 1631.8 / 1879.2 / 2583.0 (cv=0.17) | tier2_only=1.00 |
| 4 | 200 (200) | 0 | 0 | 3245.9 / 3660.0 / 4367.3 (cv=0.12) | 3242.8 / 3657.2 / 4363.2 (cv=0.12) | 2.8 / 4.0 / 4.0 (cv=0.25) | 0.1 / 0.1 / 0.2 (cv=0.29) | 3340.8 / 4116.0 / 4520.8 (cv=0.13) | tier2_only=1.00 |
| 8 | 200 (200) | 0 | 0 | 6330.7 / 7100.7 / 7356.8 (cv=0.10) | 6327.7 / 7096.9 / 7353.8 (cv=0.10) | 2.8 / 4.0 / 4.0 (cv=0.22) | 0.0 / 0.1 / 0.1 (cv=0.24) | 6570.9 / 7359.4 / 7880.1 (cv=0.08) | tier2_only=1.00 |
| 16 | 200 (200) | 0 | 0 | 12590.8 / 13994.0 / 14072.2 (cv=0.08) | 12587.7 / 13991.0 / 14067.8 (cv=0.08) | 2.8 / 4.0 / 4.0 (cv=0.22) | 0.0 / 0.0 / 0.0 (cv=0.22) | 13134.4 / 14156.0 / 14880.4 (cv=0.07) | tier2_only=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | tier2_only | 849.4 / 938.7 / 1070.9 (cv=0.08) |
| 2 | tier2_only | 1574.4 / 1824.5 / 2580.5 (cv=0.20) |
| 4 | tier2_only | 3245.9 / 3660.0 / 4367.3 (cv=0.12) |
| 8 | tier2_only | 6330.7 / 7100.7 / 7356.8 (cv=0.10) |
| 16 | tier2_only | 12590.8 / 13994.0 / 14072.2 (cv=0.08) |

### mixed_dense

Combined-cascade cost: one of every entity type with a registered surrogate domain, across both tiers (EMAIL/UPI excluded -- see the module-level note above).

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 1015.1 / 1176.3 / 1258.5 (cv=0.09) | 1011.8 / 1173.0 / 1255.4 (cv=0.09) | 2.9 / 4.0 / 7.0 (cv=0.30) | 0.3 / 0.4 / 0.7 (cv=0.31) | 1023.4 / 1185.6 / 1268.3 (cv=0.09) | both=1.00 |
| 2 | 200 (200) | 0 | 0 | 1961.2 / 2219.7 / 3120.0 (cv=0.19) | 1957.8 / 2215.2 / 3117.0 (cv=0.19) | 3.1 / 4.0 / 4.1 (cv=0.20) | 0.2 / 0.3 / 0.4 (cv=0.35) | 2042.5 / 2508.7 / 3227.0 (cv=0.16) | both=1.00 |
| 4 | 200 (200) | 0 | 0 | 3977.8 / 4837.4 / 6045.5 (cv=0.16) | 3974.4 / 4834.8 / 6042.2 (cv=0.16) | 3.2 / 4.1 / 5.0 (cv=0.25) | 0.1 / 0.1 / 0.1 (cv=0.25) | 4134.4 / 5147.1 / 6055.0 (cv=0.14) | both=1.00 |
| 8 | 200 (200) | 0 | 0 | 7562.9 / 8543.8 / 9323.0 (cv=0.11) | 7559.6 / 8540.9 / 9319.7 (cv=0.11) | 3.0 / 4.0 / 4.0 (cv=0.24) | 0.0 / 0.1 / 0.1 (cv=0.25) | 7901.5 / 9085.6 / 9603.1 (cv=0.09) | both=1.00 |
| 16 | 200 (200) | 0 | 0 | 15236.2 / 16819.7 / 16983.4 (cv=0.08) | 15232.8 / 16815.7 / 16980.7 (cv=0.08) | 3.1 / 4.0 / 4.3 (cv=0.22) | 0.0 / 0.0 / 0.0 (cv=0.22) | 15792.2 / 16979.3 / 18034.0 (cv=0.07) | both=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | both | 1015.1 / 1176.3 / 1258.5 (cv=0.09) |
| 2 | both | 1961.2 / 2219.7 / 3120.0 (cv=0.19) |
| 4 | both | 3977.8 / 4837.4 / 6045.5 (cv=0.16) |
| 8 | both | 7562.9 / 8543.8 / 9323.0 (cv=0.11) |
| 16 | both | 15236.2 / 16819.7 / 16983.4 (cv=0.08) |

### multiturn_5

Session-map growth over an extended, 5-turn message history (5 distinct real-valued entities needing allocation/FF1 within one sanitize() call). This is NOT a live ingress-surrogate scenario: constructing one honestly would require already knowing this exact session's own FF1/name-allocation output, which a static, pre-generated workload cannot predict ahead of a real run against a real FPE_KEY. Ingress-recognition correctness itself is already covered by Phase 3's own dedicated tests; what this workload isolates for latency purposes is the cost of a longer accumulated session, not that one specific branch.

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 4651.4 / 5440.9 / 6588.8 (cv=0.10) | 4647.9 / 5438.0 / 6585.0 (cv=0.10) | 3.2 / 4.0 / 7.2 (cv=0.88) | 0.1 / 0.1 / 0.2 (cv=0.87) | 4652.1 / 5441.6 / 6589.9 (cv=0.10) | both=1.00 |
| 2 | 200 (200) | 0 | 0 | 8844.1 / 10041.4 / 12262.4 (cv=0.18) | 8840.7 / 10037.9 / 12258.5 (cv=0.18) | 3.1 / 4.0 / 6.0 (cv=0.65) | 0.0 / 0.1 / 0.1 (cv=0.72) | 9087.6 / 12233.4 / 14069.2 (cv=0.18) | both=1.00 |
| 4 | 200 (200) | 0 | 0 | 17413.6 / 20739.2 / 24711.1 (cv=0.16) | 17410.2 / 20734.9 / 24707.2 (cv=0.16) | 3.1 / 4.0 / 4.5 (cv=0.24) | 0.0 / 0.0 / 0.0 (cv=0.32) | 18001.7 / 22755.2 / 24712.8 (cv=0.14) | both=1.00 |
| 8 | 199 (200) | 1 | 0 | 53676.2 / 75593.3 / 82870.6 (cv=0.25) | 53671.2 / 75586.5 / 82864.8 (cv=0.25) | 4.6 / 8.7 / 30.0 (cv=0.83) | 0.0 / 0.0 / 0.0 (cv=0.86) | 55489.0 / 82010.6 / 83074.5 (cv=0.26) | both=1.00 |
| 16 | 177 (200) | 22 | 1 | 80506.9 / 114977.7 / 127926.6 (cv=0.20) | 80501.7 / 114970.1 / 127920.1 (cv=0.20) | 4.2 / 8.0 / 28.5 (cv=1.01) | 0.0 / 0.0 / 0.0 (cv=1.02) | 83226.7 / 120209.8 / 129951.9 (cv=0.20) | both=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | both | 4651.4 / 5440.9 / 6588.8 (cv=0.10) |
| 2 | both | 8844.1 / 10041.4 / 12262.4 (cv=0.18) |
| 4 | both | 17413.6 / 20739.2 / 24711.1 (cv=0.16) |
| 8 | both | 53676.2 / 75593.3 / 82870.6 (cv=0.25) |
| 16 | both | 80506.9 / 114977.7 / 127926.6 (cv=0.20) |

### field_walker_heavy

Field-walking cost independent of PII density: PII planted in the system prompt, a tool definition, and a tool-result message -- not just messages[].content (ARCHITECTURE.md, Body Field Walker: 'the field you forget is the leak').

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 6232.4 / 8960.3 / 10471.1 (cv=0.19) | 6227.4 / 8956.5 / 10463.2 (cv=0.19) | 4.6 / 9.0 / 31.0 (cv=1.03) | 0.1 / 0.2 / 0.6 (cv=1.11) | 6233.3 / 8961.2 / 10471.9 (cv=0.19) | both=1.00 |
| 2 | 200 (200) | 0 | 0 | 9742.6 / 16566.0 / 19885.4 (cv=0.35) | 9737.4 / 16556.4 / 19882.5 (cv=0.35) | 4.9 / 29.0 / 30.0 (cv=1.37) | 0.1 / 0.2 / 0.4 (cv=1.39) | 10010.5 / 16569.1 / 19888.8 (cv=0.34) | both=1.00 |
| 4 | 200 (200) | 0 | 0 | 15432.5 / 17244.8 / 19007.9 (cv=0.11) | 15429.2 / 17242.7 / 19004.7 (cv=0.11) | 2.8 / 4.0 / 7.0 (cv=0.76) | 0.0 / 0.0 / 0.0 (cv=0.71) | 16006.9 / 17440.1 / 19191.6 (cv=0.09) | both=1.00 |
| 8 | 200 (200) | 0 | 0 | 30322.8 / 33942.9 / 34770.4 (cv=0.10) | 30320.0 / 33940.1 / 34767.4 (cv=0.10) | 2.5 / 3.0 / 4.0 (cv=0.27) | 0.0 / 0.0 / 0.0 (cv=0.30) | 31402.0 / 35199.9 / 37023.2 (cv=0.09) | both=1.00 |
| 16 | 200 (200) | 0 | 0 | 60824.7 / 65867.0 / 66295.4 (cv=0.08) | 60821.9 / 65864.0 / 66292.4 (cv=0.08) | 2.5 / 3.0 / 4.0 (cv=0.22) | 0.0 / 0.0 / 0.0 (cv=0.27) | 62871.9 / 67053.1 / 70315.8 (cv=0.08) | both=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | both | 6232.4 / 8960.3 / 10471.1 (cv=0.19) |
| 2 | both | 9742.6 / 16566.0 / 19885.4 (cv=0.35) |
| 4 | both | 15432.5 / 17244.8 / 19007.9 (cv=0.11) |
| 8 | both | 30322.8 / 33942.9 / 34770.4 (cv=0.10) |
| 16 | both | 60824.7 / 65867.0 / 66295.4 (cv=0.08) |

### pathological_chunking

Window/rehydration cost under stress: mixed_dense's own request body, plus the mock's `chunking.n` directive forcing every surrogate in the echoed response across 40 chunks (src/mock_upstream/chunking.py) -- isolates rehydration-under- fragmentation cost from normal streaming cost.

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 1001.1 / 1114.2 / 1158.3 (cv=0.07) | 998.5 / 1111.0 / 1155.8 (cv=0.07) | 2.3 / 3.0 / 7.0 (cv=0.35) | 0.2 / 0.3 / 0.7 (cv=0.35) | 1009.4 / 1124.1 / 1166.3 (cv=0.07) | both=1.00 |
| 2 | 200 (200) | 0 | 0 | 1936.9 / 2193.0 / 2914.7 (cv=0.17) | 1934.1 / 2189.7 / 2912.9 (cv=0.17) | 2.5 / 3.0 / 4.0 (cv=0.79) | 0.1 / 0.2 / 0.3 (cv=0.75) | 1993.3 / 2624.5 / 3086.5 (cv=0.17) | both=1.00 |
| 4 | 200 (200) | 0 | 0 | 3897.5 / 4526.3 / 5337.4 (cv=0.14) | 3894.9 / 4524.4 / 5335.0 (cv=0.14) | 2.3 / 3.0 / 4.0 (cv=0.29) | 0.1 / 0.1 / 0.1 (cv=0.36) | 4042.7 / 4955.7 / 5347.5 (cv=0.12) | both=1.00 |
| 8 | 200 (200) | 0 | 0 | 7740.9 / 8583.2 / 9184.5 (cv=0.11) | 7738.2 / 8580.0 / 9181.5 (cv=0.11) | 2.4 / 3.0 / 3.1 (cv=0.23) | 0.0 / 0.0 / 0.0 (cv=0.22) | 8039.5 / 9006.8 / 9476.9 (cv=0.08) | both=1.00 |
| 16 | 200 (200) | 0 | 0 | 15225.2 / 17131.2 / 17682.3 (cv=0.09) | 15222.5 / 17127.2 / 17679.8 (cv=0.09) | 2.4 / 3.0 / 3.1 (cv=0.24) | 0.0 / 0.0 / 0.0 (cv=0.24) | 15751.2 / 17602.1 / 18693.6 (cv=0.08) | both=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | both | 1001.1 / 1114.2 / 1158.3 (cv=0.07) |
| 2 | both | 1936.9 / 2193.0 / 2914.7 (cv=0.17) |
| 4 | both | 3897.5 / 4526.3 / 5337.4 (cv=0.14) |
| 8 | both | 7740.9 / 8583.2 / 9184.5 (cv=0.11) |
| 16 | both | 15225.2 / 17131.2 / 17682.3 (cv=0.09) |

### long_response

Window accumulation over a long stream: 20 short paragraphs, each naming a distinct person and org, normal (non- pathological) chunking -- isolates whether window overhead compounds over stream length rather than per-surrogate.

| Concurrency | n (attempted) | timeout | error | TTFT (with window) | TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | Tier hit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 200 (200) | 0 | 0 | 2030.9 / 2227.0 / 2331.8 (cv=0.07) | 2026.7 / 2222.7 / 2327.8 (cv=0.07) | 3.9 / 5.1 / 6.1 (cv=0.24) | 0.2 / 0.3 / 0.3 (cv=0.23) | 2083.7 / 2284.7 / 2384.4 (cv=0.07) | tier2_only=1.00 |
| 2 | 200 (200) | 0 | 0 | 4419.1 / 5237.2 / 5915.8 (cv=0.13) | 4414.5 / 5232.2 / 5911.3 (cv=0.13) | 4.3 / 6.0 / 8.0 (cv=0.27) | 0.1 / 0.1 / 0.2 (cv=0.29) | 4474.6 / 5299.7 / 5970.5 (cv=0.13) | tier2_only=1.00 |
| 4 | 200 (200) | 0 | 0 | 7975.9 / 10699.7 / 11044.6 (cv=0.22) | 7971.0 / 10693.6 / 11040.5 (cv=0.22) | 4.3 / 6.0 / 7.0 (cv=0.28) | 0.1 / 0.1 / 0.2 (cv=0.42) | 8331.1 / 11069.7 / 12553.9 (cv=0.23) | tier2_only=1.00 |
| 8 | 200 (200) | 0 | 0 | 15768.2 / 20074.2 / 21434.7 (cv=0.16) | 15763.6 / 20069.5 / 21430.0 (cv=0.16) | 4.0 / 6.0 / 7.0 (cv=0.26) | 0.0 / 0.0 / 0.0 (cv=0.30) | 16196.2 / 20248.5 / 23449.4 (cv=0.16) | tier2_only=1.00 |
| 16 | 200 (200) | 0 | 0 | 31741.9 / 35449.0 / 37511.5 (cv=0.09) | 31736.9 / 35444.2 / 37506.6 (cv=0.09) | 4.3 / 7.0 / 8.0 (cv=0.29) | 0.0 / 0.0 / 0.0 (cv=0.29) | 33049.3 / 37089.3 / 38242.1 (cv=0.08) | tier2_only=1.00 |

Per-tier TTFT (with window) — only populated tier classes shown:

| Concurrency | Tier class | TTFT (with window) |
|---|---|---|
| 1 | tier2_only | 2030.9 / 2227.0 / 2331.8 (cv=0.07) |
| 2 | tier2_only | 4419.1 / 5237.2 / 5915.8 (cv=0.13) |
| 4 | tier2_only | 7975.9 / 10699.7 / 11044.6 (cv=0.22) |
| 8 | tier2_only | 15768.2 / 20074.2 / 21434.7 (cv=0.16) |
| 16 | tier2_only | 31741.9 / 35449.0 / 37511.5 (cv=0.09) |


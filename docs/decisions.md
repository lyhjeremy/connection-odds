# Data and method decisions

Judgment calls the spec (`docs/spec.md`) did not settle, in the order they come up in the pipeline.

## Data

1. **Source table.** BTS "Marketing Carrier On-Time Performance (Beginning January 2018)", monthly zips from `transtats.bts.gov/PREZIP/`. Window September 2023 to August 2026 (36 months) for everything the tool uses, plus January to December 2019 as a comparison. Only 18 of the file's 120 columns are kept (`scripts/fetch_bts.py`). The header has a trailing space in `"Operating_Airline "`.
2. **Row counts.** `results/fetch_manifest.csv` records rows per month as read from each file. All 48 months were checked: every row has `Duplicate = N`, so no row is dropped as a code-share duplicate. Each zip passed a CRC check (`zipfile.testzip`) before conversion; downloads that stalled were resumed and rechecked.
3. **Actual times.** Actual gate times are the scheduled time plus `DepDelay` or `ArrDelay` in minutes, which BTS already computes across midnight. On August 2026 this matches the reported `hhmm` actual time (modulo 24 hours) for 99.9998% of arrivals and 100% of departures.
4. **Arrival date.** BTS gives one date per flight, the departure date at the origin. The scheduled arrival is placed on that date or the next (or the previous, for short westbound hops that land "before" they leave in local time) by taking the day offset that puts it nearest to departure plus the scheduled block time. Time-zone gaps inside the 50 states are under 12 hours, so the choice is never ambiguous.
5. **Local time.** Both legs of a connection are timed at the hub, so gaps are differences of two local times at the same airport and no time-zone table is needed.

## Pairs

6. **Month boundaries.** Each month's arrivals are paired with that month's departures plus the first day of the next month, so a 23:40 arrival on the 31st can connect to a 00:30 departure. The two months with no cached successor (December 2019 and August 2026) lose those after-midnight connections on their last night.
7. **Diverted departures** count as flown: the traveler boarded. A diverted arrival is a miss.
8. **Missing actual times.** A pair whose flights both operated but lacks an actual time is dropped. There are very few.
9. **Sampling** is one random departure per arrival per 15-minute layover bucket, with the random draw seeded by year, month and hub (`build_pairs.py`).
10. **Airline threshold.** An airline is kept at a hub if it has at least 1,000 sampled pairs there over the 36 months.
11. **Same-tail share** is counted before sampling, against all candidate pairs.

## Analysis

12. **Layover needed for 90, 95 or 99%.** The shortest layover at which the miss rate is at or below the target and stays there at every longer layover, using only bins with at least 200 pairs. If no such layover exists within 180 minutes, it is reported as "over 180". Hub and airline curves use 5-minute bins; hour-level tables use 15-minute buckets.
13. **"If both flights operate".** Cancellations are counted as misses, as the spec says, and they put a floor under every curve that no layover removes. The tables also give the 95% layover computed on flown pairs only, so the two effects can be told apart.
14. **Intervals** are Wilson 95% intervals that treat pairs as independent. They are not: one arrival appears in up to ten pairs, and pairs on the same day share weather. The intervals are too narrow, and the page says so.
15. **The shortcut** reads only the inbound flight: missed if it was cancelled or diverted, or arrived more than layover minus W minus D late. It ignores both the outbound delay and outbound cancellations. The tables split the gap into those two parts.
16. **Cell-average lookup** for the evaluation: training-period mean of the outcome in the cell (hub, airline, arrival hour, month, 15-minute bucket); when a cell has fewer than 200 pairs, it backs off to (hub, airline, hour, bucket), then (hub, airline, bucket), (hub, bucket) and (bucket). The naive shortcut uses the same cells and backoff, so the two differ only in the outcome they average.
17. **Logistic model** terms: hub-airline, 5-minute layover bin, arrival hour, month, weekday, plus layover by hub-airline, month by hub and hour by hub. L2 penalty with C = 1, fitted on a seeded sample of 3 million training pairs. The browser averages the prediction over the seven weekdays because the tool does not ask for one.
18. **"Calibrates best"** means the lowest expected calibration error across deciles of the prediction (count-weighted mean of the absolute gap between predicted and observed), with Brier score breaking a tie. Brier score and log loss are reported for all three.
19. **What ships.** The evaluation fits on September 2023 to February 2026 and tests on March to August 2026. The tool then uses the same estimator refitted on all 36 months.
20. **Drivers.** Each factor is dropped in turn (with its interactions) and the model refitted on 600,000 training pairs; the increase in test log loss ranks the factors. Layover and hub-airline share the layover-by-hub-airline term, so dropping either removes it.

## Tool

21. **W slider** runs from 10 to 30 minutes in steps of 5, with one model per value; D stays at 10 minutes. The range stops at 30 to keep `tool.json` under its 2 MB budget: each extra W value adds a count to every observed cell.
22. **Minimum connection times.** The spec asks for layovers below an airline's minimum to be greyed. No public table of airline minimum connection times was found; the figures that turn up online come from forums and travel blogs and disagree. The tool greys layovers under 35 minutes and says it lacks the airlines' own tables.
23. **Cells in the tool** are (hub, airline, arrival hour, month, 15-minute bucket) with at least 200 pairs. Thinner cells show the model and say so.

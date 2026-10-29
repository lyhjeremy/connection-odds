# Connection Odds: spec

Project 39. Drafted 2026-10-28. Status: locked 2026-10-28, approved for build.

## 1. Question

If you book a connection at a US hub with a given layover, how often do you miss it? Using every domestic flight the US Department of Transportation recorded, estimate the chance that a connection of 30 to 180 minutes fails, by hub, airline, time of day and month, and find the layover that gets a traveler to 95% safe. Then show how wrong the obvious shortcut is: reading only the inbound flight's delay ignores that the outbound flight is often late too, on the same weather and the same congested airport.

Working headline: "At __, a 45-minute connection failed __% of the time; it took __ minutes to reach 95%. The shortcut that ignores the outbound delay overstates risk by __ points."

## 2. Locked decisions

| Decision | Choice |
|---|---|
| Running cost | $0. Static site on GitHub Pages; the lookup tool reads a precomputed JSON. |
| Data | BTS "Marketing Carrier On-Time Performance (Beginning January 2018)", monthly zips from `transtats.bts.gov/PREZIP/`, public domain (US government). Latest month available: August 2026. |
| Raw cache | Outside My Drive (`$CONN_CACHE`, default `~/data-cache/connection-odds/`), converted once to parquet with only the needed columns. About 38 MB zipped and 335 MB unzipped per month, so roughly 1.4 GB of zips for three years; none of it is committed. |
| Repo | `connection-odds` |
| Family | workshop |
| Language | Python: pandas or polars, pyarrow; plain JS and inline SVG for the tool. |
| LLM calls | None. |
| Numbers in copy | Generated only, Fuel Lockstep pattern (`export_numbers.py`, `build_site.py`). |

## 3. Why the marketing-carrier table

A traveler books with a marketing carrier: a United ticket may fly a SkyWest-operated United Express leg. The older reporting-carrier table lists that leg under SkyWest, so pairing by airline would miss most real regional connections. The marketing table carries both. Checked 2026-10-28 against the August 2026 file (38 MB zipped, 335 MB as CSV): it has `Marketing_Airline_Network`, `Operating_Airline`, `Tail_Number`, scheduled and actual gate times (`CRSDepTime`, `DepTime`, `CRSArrTime`, `ArrTime`), `Cancelled` and `Diverted`.

## 4. Building connections

The data has flights, not passenger itineraries, so connections are constructed and the page says so.

1. For each hub, each day and each marketing airline, take every arriving flight and every departing flight.
2. A candidate connection is an arrival and a departure on the same marketing airline (alliance partners out of v1) with a scheduled gap between 30 and 180 minutes, the departure going somewhere other than the arrival's origin.
3. Drop pairs flown by the same tail number: the plane cannot leave without its own inbound passengers.
4. Sampling: a large hub produces tens of millions of pairs a year. For each arrival, keep one random departure per 15-minute gap bucket, seeded and stored, which keeps every arrival represented evenly.
5. Outcome, per pair:
   - missed if the arrival was cancelled or diverted, or the departure was cancelled (the traveler is rebooked either way);
   - otherwise missed if actual gate arrival + W > actual gate departure − D, where W is the gate-to-gate time and D is how long before pushback the door closes.
   - Defaults: W = 20 minutes, D = 10 minutes (section 9). The tool exposes W as a slider so the reader can set their own.
6. Hubs: the 30 busiest US airports by departures in the window; airlines: those with at least 1,000 pairs at a hub.

## 5. Analysis

1. **EDA.** Delay distributions by hub, airline, hour and month; cancellation rates; how delay builds through the day; the share of pairs that are same-tail (dropped) per hub.
2. **Miss-rate curves.** Miss probability against scheduled layover, per hub and airline, with Wilson intervals.
3. **The 95% layover.** For each hub, airline and arrival hour, the shortest layover whose miss rate is at most 5%.
4. **The shortcut.** Naive estimate: P(arrival delay > layover − W − D), ignoring the outbound. Compare with the paired estimate. The gap is the correlation between inbound and outbound delays, and it is reported per hub.
5. **What drives risk.** Logistic model of a miss on layover, hub, airline, arrival hour, month and weekday, to rank the factors and give the tool a smooth estimate where cells are thin.
6. **Evaluation.** Fit on the first 30 months, test on the last 6. Report calibration (predicted against observed miss rate in deciles) and Brier score for three estimators: the naive shortcut, the cell-average lookup, and the logistic model. The tool ships whichever calibrates best, and the page says which.

## 6. Outputs

- Lookup tool: choose hub, airline, arrival hour, month and layover; it shows the miss rate, its interval and the sample size, plus the layover needed for 90%, 95% and 99%. Cells under 200 pairs fall back to the model and say so.
- Static figures: miss rate against layover for the ten largest hubs; the 95% layover heatmap by hub and hour; naive against paired.
- `README.md`, `writeup.md`, landing page, `/overview/` fragment, `tables/`, `results/numbers.json`.
- JSON budget for the tool: under 2 MB, gzip-friendly.
- lyhjeremy.com card (tools group), profile hub row.

## 7. Limitations to state on the page

- Constructed pairs are not real bookings. Airlines do not sell every pair, and their own minimum connection times (often 35 to 60 minutes domestic) remove the shortest ones; results below an airline's minimum are shown greyed.
- Gate-to-gate time differs by terminal. One W per hub is a simplification, which is why the reader can move it.
- Only US domestic flights by reporting carriers. No international legs, no customs time.
- Airlines sometimes hold a departure for connecting passengers. That shows up in the data as outbound delay, so it is counted, but it cannot be told apart from ordinary delay.
- A missed connection here means rebooking, not a lost trip; the hours lost are out of v1.

## 8. Phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Repo skeleton, fetch script with resume, parquet cache, column check | three years plus any comparison year cached and row counts match the BTS totals |
| 1 | Pair builder with tests (same-tail drop, cancellations, overnight arrivals across midnight, time zones are local in BTS so gaps are computed in local time at the hub) | unit tests pass, one hub hand-checked |
| 2 | EDA, curves, shortcut comparison, model, calibration | `numbers.json` written, blanks filled |
| 3 | Tool, writeup, overview, landing, privacy note (no data leaves the browser) | designcheck, 390px, live check |
| 4 | Hub card, profile row, PROJECTS_SUMMARY, handoff | live link check clean |

## 9. Decisions (Jeremy, 2026-10-28)

1. Window: September 2023 to August 2026 for the tool, plus calendar 2019 as a pre-pandemic comparison.
2. Defaults W = 20 and D = 10 minutes; the tool has a slider for W.
3. Name: `connection-odds`.
4. Alliance partners out of v1.
5. Build: fully autonomous, the three projects in parallel; create public repos, push to main as Jeremy Lee <lyhjeremy@gmail.com> with no AI trailer, add hub cards and profile rows, then report.

## 10. Cut lines

First to go: the 2019 comparison, then the logistic model (the lookup falls back to cell averages with intervals). The column risk is cleared (section 3). The remaining failure mode is memory: if a full year at the largest hubs will not fit, pairs are built one month at a time and only bucket counts are kept.

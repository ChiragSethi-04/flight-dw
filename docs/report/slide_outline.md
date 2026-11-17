# 12-minute presentation outline

Roughly one minute per slide, with slide 7 (live demo) given two
minutes. Every number in the speaker notes is from `exports/` or
`docs/evidence/`; nothing here is invented for the talk.

## 1. Title and problem (1 min)
**Slide:** Flight Delay Analytics Data Warehouse. One line: "Why do US
domestic flights run late, and where should an airline act first?"
**Notes:** Built for a Data Warehousing and BI course assignment.
Source of truth throughout: `docs/brief.pdf`.

## 2. Scope and users (1 min)
**Slide:** 4 user types (ops managers, planners, station managers,
executives), 6 business questions, 8 KPIs. One calendar year, 2025,
US domestic only.
**Notes:** In scope versus out of scope (no prices, no ML, no
real-time), per the brief's own locked decisions.

## 3. Architecture (1 min)
**Slide:** 4 sources -> staging -> star schema (2 facts, 7 dimensions)
-> OLAP views -> dashboard. Point to `docs/diagrams/etl_flow.svg`.
**Notes:** S4 (BTS lookup tables) is blocked; name the 2 columns
that stay as placeholder codes because of it (`docs/DECISIONS.md`,
item B1). Everything else loaded in full: 7,001,619 flight rows,
334,896 airport-day weather rows.

## 4. Data model (1.5 min)
**Slide:** Star schema diagram (`docs/diagrams/star_schema.svg` or
`docs/diagrams/eer_diagram.png`). Call out the role-playing
`dim_airport` (origin and destination), `dim_carrier`'s SCD Type 2,
and the junk dimensions.
**Notes:** Grain statement for each fact table. Every dimension has a
real `-1` Unknown row, enforced by real foreign keys, not convention.

## 5. Data quality (1.5 min)
**Slide:** The nine-problem table from `docs/profiling/summary.md`,
condensed to the 3 most interesting rows (midnight 2400, the US
territory airport bug, the 14 cause-sum mismatches).
**Notes:** Name one real bug found by running the pipeline, not by
reading the code: the country-name filter that silently dropped 8 real
US territory airports (~92,000 flight-row mentions) until it was
caught by comparing unmatched-key counts against what Phase 2 had
already found.

## 6. Validation (1 min)
**Slide:** The six checks from brief section 6, all PASS, with the
real numbers (row reconciliation 7,001,619 = 7,001,619 + 0; 0 orphan
keys; 0 duplicates).
**Notes:** Two full pipeline runs produced byte-identical counts
everywhere (idempotency, hard rule 4).

## 7. Live demo (2 min)
**SQL drill-down:** run Q1's worst-routes query live
(`sql/07_olap_queries.sql`, the first block), narrating: "ORD-ASE is
the worst route in the network, 55.2% on-time against a system-wide
77.5%." Then re-run it with the 500-flight floor removed, to show why
that floor exists (small routes with 100% or 0% on-time rates flood
the top of the list otherwise).
**Dashboard filter:** on the Routes and Carriers page, filter to a
single carrier on a route from Q6's widest-spread list (e.g. BWI-ORD)
and show its delay against the route average changing as the filter
is applied.

## 8. Findings (2 min)
**Slide:** The 4 hypotheses, one line each: late aircraft confirmed
largest cause (39.2%); delay builds through the day, confirmed with a
night-time caveat; snow/rain hypothesis partly supported (true for
light/moderate snow, not for heavy snow or precipitation alone);
some routes late regardless of carrier, partly supported (73% of
routes show tight carrier agreement, but a real tail does not).
**Notes:** Say explicitly that one hypothesis (H3) is only partly
supported and that heavy snow actually shows lower disruption than
light snow, a genuine, checked finding, not a hedge. This is
deliberate: the brief asks for association, not forced confirmation.

## 9. Recommendations (1 min)
**Slide:** 4 recommendations, one per hypothesis, from
`docs/report/08_findings_and_limitations.md`.
**Notes:** Each recommendation follows directly from its own evidence
above it; none is generic advice bolted on afterward.

## 10. Limitations and next steps (1 min)
**Slide:** The 6 limitations from brief section 9 (daily weather vs.
hourly flights, carrier-reported causes, reporting-threshold carriers
missing, one year only, association not proof, no cost/passenger
data). "If the project continued": hourly weather, tail-number
propagation chains, a predictive model.

## Live-demo script, verbatim

1. Open a SQL client connected to `flight_dw`.
2. Paste and run Q1a from `sql/07_olap_queries.sql` (the `route_stats`
   / `route_ranked` CTE block). Point at `ORD-ASE`, 55.2%, row 1.
3. Change `WHERE flight_count >= 500` to `>= 10` and re-run. Point out
   how several 0% or 100% on-time routes with only a handful of
   flights now dominate the top of the list, and explain that this is
   exactly why the 500-flight floor exists.
4. Switch to the dashboard (or `exports/vw_routes_carriers.csv` if the
   dashboard is not available for the demo). Filter to `BWI-ORD`.
   Show `OO`'s average delay against the route average, then remove
   the filter to show the full route again.

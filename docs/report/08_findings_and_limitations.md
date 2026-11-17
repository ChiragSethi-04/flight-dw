# Task 8: Findings and limitations

Every number below comes from `exports/` or a query run directly
against the real warehouse for this report (saved in
`docs/evidence/hypothesis_testing.txt`); none is invented. Every
finding is association, not proof: one year of observational data
cannot establish that weather, time of day or carrier *causes* a given
delay outcome, only that they are associated with it. Each finding is
written as evidence, then interpretation, then recommendation, and
none is forced to a clean answer where the data does not support one.

## Hypothesis 1: late inbound aircraft account for the largest share of delay minutes

**Evidence.** Across the full 2025 year, late-aircraft delay is
43,862,971 of 111,934,625 total delay-cause minutes (39.2%), ahead of
carrier delay (32.5%), the air traffic system / NAS (21.9%), weather
(6.4%) and security (0.1%). Q5's hourly breakdown for the 10 busiest
airports shows the same pattern locally: late-aircraft share exceeds
40% in most afternoon and evening hours, peaking at 62.8% at 8 p.m. at
Las Vegas.

**Interpretation.** The hypothesis is **confirmed**. Late-arriving
aircraft, not weather or security, are the largest single driver of
the delay minutes this warehouse can measure. This is consistent with
a fleet that reuses the same aircraft and crew across several flights
a day, so a delay early in the day's rotation compounds later.

**Recommendation.** Add turnaround buffers on tightly scheduled
aircraft rotations, concentrated on routes and hours already shown to
carry the highest late-aircraft share (Q5's output names the specific
airport-hour combinations).

## Hypothesis 2: delay builds through the day

**Evidence.** Fleet-wide, by departure band:

| Departure band | Flights | Avg arrival delay (min) | Late-aircraft share | On-time rate |
|---|---|---|---|---|
| Early morning | 215,288 | -2.20 | 16.0% | 90.3% |
| Morning | 2,742,560 | 1.18 | 27.0% | 85.0% |
| Afternoon | 2,041,291 | 11.53 | 40.5% | 74.3% |
| Evening | 1,554,088 | 17.63 | 46.9% | 68.0% |
| Night | 448,392 | 13.40 | 45.5% | 72.0% |

**Interpretation. Confirmed for the main operating day, with one
caveat.** Both average delay and late-aircraft share rise
monotonically from early morning through evening, covering 93.6% of
all flights (6,553,227 of 7,001,619). The night band (6.4% of
flights) breaks the simple monotonic story: both metrics ease back
slightly rather than continuing to rise. A plausible association,
not yet tested directly, is that the much thinner overnight schedule
carries more slack per aircraft, giving late inbound aircraft more
room to recover before their next departure.

**Recommendation.** Move recovery capacity and spare aircraft toward
the afternoon, as the hypothesis anticipated, with the added
refinement that the night schedule does not need the same treatment:
it is already recovering on its own, not accumulating delay.

## Hypothesis 3: snow and heavy rain raise cancellations more than delay minutes

**Evidence.** By precipitation band, both cancellation rate and
average arrival delay rise by almost exactly the same multiple from
"none" to "extreme" (cancellation 5.47x, delay 5.49x). By snow band,
the picture is mixed: light snow (5.63x cancellation vs. 4.12x delay)
and moderate snow (21.77x cancellation vs. 11.75x delay) both show
cancellation rising faster than delay, but heavy snow shows *both*
metrics *below* the no-snow baseline (0.79x and 0.58x).

**Interpretation. Partly supported.** The hypothesis holds clearly for
light and moderate snow, the two most common snow conditions by flight
count (118,840 and 8,090 flights respectively), where cancellation
responds much more sharply than delay, exactly as predicted. It does
not hold for precipitation alone, where both metrics move together.
Heavy snow (1,101,871 flights, the single most common non-none snow
band by flight count) is a genuine exception, not an artifact of a
small sample: a plausible association is that heavy-snowfall days
cluster at a smaller set of high-volume, winter-equipped hub airports
(station-day evidence for this project shows heavy-snow days
concentrated in states like CO, MI, ND, NY) that are comparatively
well practiced at operating through snow, while light snow more often
falls on airports with less snow-handling capacity, causing
disproportionate disruption from even a little.

**Recommendation.** Pre-plan cancellation and rebooking specifically
for light and moderate snow and for any heavy-precipitation forecast;
heavy snow at a well-equipped hub does not need the same contingency
level this hypothesis originally assumed.

## Hypothesis 4: some routes are late regardless of carrier

**Evidence.** Across the 3,119 routes flown by 2 or more carriers
(minimum 20 flights per carrier on the route), the average within-route
spread between carriers (standard deviation 7.42 minutes) is nearly
identical to the spread between different routes overall (standard
deviation 7.31 minutes). 73.2% of these routes have every carrier
within 10 minutes of each other. A real minority does not: BWI-ORD
(Q6's single widest gap, 102.4 minutes), IAD-SJU (71.5 minutes
carrier-to-carrier spread), MIA-XNA (54.3 minutes) and others.

**Interpretation. Partly supported.** For about three-quarters of
multi-carrier routes, the route itself, not the operating carrier,
appears to be the dominant factor, consistent with the hypothesis.
But carrier-level variation is, in aggregate, about as large as
route-level variation, and a real tail of routes shows one carrier
performing dramatically differently from its peers on the identical
route. Treating "the route" as the explanation everywhere would
overstate the case; both matter, and which one dominates is itself
route-specific.

**Recommendation.** Retime the schedule for the 73% of routes where
carriers agree with each other, since no single carrier change would
fix a route-level problem there. For the tail of routes with a wide
carrier spread (starting from `exports/q6_carrier_vs_route_avg_delay.csv`,
sorted by spread), investigate the specific underperforming carrier's
operation on that route instead.

## Limitations and assumptions (brief section 9)

- Weather is daily and taken from the nearest station (median distance
  evidence in `docs/profiling/summary.md`, problem 7), so it
  approximates conditions at the airport and cannot match an
  individual flight's hour.
- BTS cause fields are carrier-reported, and the weather cause
  specifically covers extreme weather only; routine weather delay may
  be recorded under a different cause.
- BTS covers carriers above a reporting threshold, so smaller carriers
  are absent from this warehouse entirely, not merely small in it.
- One year of data (2025) cannot show year-over-year change; `dim_carrier`'s
  SCD Type 2 structure is ready for it, but has nothing to show yet
  (`docs/DECISIONS.md`, decision 6).
- The data shows association, not proof of cause; every finding above
  is written that way deliberately, not as a stylistic caveat.
- No cost or passenger data exists in this warehouse, so impact above
  is measured only in delay minutes and cancellations, never in
  dollars or passengers affected.

## If the project continued

Add hourly (not daily) weather, so a flight's actual departure hour
can be matched to the weather at that hour rather than the day's
average; add a previous-flight link by tail number to trace an actual
propagation chain rather than inferring it from the late-aircraft
cause field; add a predictive delay model once enough years of data
exist to validate one against real held-out outcomes.

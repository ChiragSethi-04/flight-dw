# Source file columns (Phase 1)

This records what each raw source file actually contains, verified by
downloading and inspecting a real file on 2026-11-17, rather than by
assuming the brief's summary lists are exhaustive. Column names are kept
exactly as the source spells them; staging tables (Phase 2) load every
one of them as text.

## S1: BTS Reporting Carrier On-Time Performance

File inspected: `On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip`,
downloaded from the verified PREZIP URL (see `docs/DECISIONS.md`).

Full header, in order, as it appears in the CSV (109 columns total):

```
Year, Quarter, Month, DayofMonth, DayOfWeek, FlightDate, Reporting_Airline,
DOT_ID_Reporting_Airline, IATA_CODE_Reporting_Airline, Tail_Number,
Flight_Number_Reporting_Airline, OriginAirportID, OriginAirportSeqID,
OriginCityMarketID, Origin, OriginCityName, OriginState, OriginStateFips,
OriginStateName, OriginWac, DestAirportID, DestAirportSeqID,
DestCityMarketID, Dest, DestCityName, DestState, DestStateFips,
DestStateName, DestWac, CRSDepTime, DepTime, DepDelay, DepDelayMinutes,
DepDel15, DepartureDelayGroups, DepTimeBlk, TaxiOut, WheelsOff, WheelsOn,
TaxiIn, CRSArrTime, ArrTime, ArrDelay, ArrDelayMinutes, ArrDel15,
ArrivalDelayGroups, ArrTimeBlk, Cancelled, CancellationCode, Diverted,
CRSElapsedTime, ActualElapsedTime, AirTime, Flights, Distance,
DistanceGroup, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay,
LateAircraftDelay, FirstDepTime, TotalAddGTime, LongestAddGTime,
DivAirportLandings, DivReachedDest, DivActualElapsedTime, DivArrDelay,
DivDistance, Div1Airport .. Div5Airport (and their AirportID, AirportSeqID,
WheelsOn, TotalGTime, LongestGTime, WheelsOff, TailNum variants, for up to
5 diversions)
```

### Comparison against the brief's section 3 field list

The brief's "important BTS fields" list is: `FlightDate, Reporting_Airline,
Flight_Number_Reporting_Airline, Tail_Number, Origin, Dest, CRSDepTime,
DepTime, DepDelay, CRSArrTime, ArrTime, ArrDelay, Cancelled,
CancellationCode, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay,
LateAircraftDelay, TaxiOut, TaxiIn, Distance`.

| Field | In the brief's list | Present in the real file |
|---|---|---|
| All 22 fields the brief names | yes | **Yes, every one, exact spelling match.** |
| `Diverted` | no | **Present.** Needed for `dim_flight_status`'s diverted flag. |
| `Year`, `Month`, `DayOfWeek` | no | **Present.** Useful for `dim_date`, though `FlightDate` alone is enough to derive them. |
| `OriginCityName`, `DestCityName` | no | **Present.** Needed for `dim_airport` city attribute (also available from S3, which is the primary source for airport reference data; S1's version is kept as a cross-check). |
| `OriginAirportID`, `DestAirportID` | no | **Present**, but not needed for the join: section 3's own matching logic joins `Origin`/`Dest` (the IATA code) to S3's IATA code, not to this numeric ID. Kept as a staging column for traceability only. |
| `ArrDelayMinutes`, `DepDelayMinutes`, `ArrDel15`, `DepDel15`, `DepartureDelayGroups`, `ArrivalDelayGroups` | no | Present, derived fields BTS computes itself (for example `ArrDel15` is already a 0/1 flag for the 15-minute threshold). Not required since the warehouse derives `on_time_flag` itself from `ArrDelay`, but worth knowing they exist as a cross-check during validation. |
| `Flights` | no | Present, always 1.00 for a non-diverted single-leg row in the sample inspected; not used. |
| `Div1Airport` .. `Div5Airport` and related diversion columns | no | Present. Out of scope per the brief (diverted flights stay in the fact table with a flag, but per-diversion-leg detail is not modelled). |

Conclusion: no field the brief needs is missing. The extra columns found
are either derivable, redundant with a dimension, or out of the agreed
scope, and are not loaded into the warehouse beyond staging.

## S2: NOAA GHCN-Daily

`ghcnd-stations.txt` and `ghcnd-inventory.txt` are fixed-width text, not
CSV. Verified format (from the NOAA GHCN-Daily documentation, matching
the downloaded files):

**ghcnd-stations.txt**: `ID` (cols 1-11), `LATITUDE` (13-20), `LONGITUDE`
(22-30), `ELEVATION` (32-37), `STATE` (39-40), `NAME` (42-71), `GSN FLAG`
(73-75), `HCN/CRN FLAG` (77-79), `WMO ID` (81-85).

**ghcnd-inventory.txt**: `ID` (1-11), `LATITUDE` (13-20), `LONGITUDE`
(22-30), `ELEMENT` (32-35, e.g. `PRCP`, `SNOW`, `TMAX`, `TMIN`, `AWND`),
`FIRSTYEAR` (37-40), `LASTYEAR` (42-45).

Per-station daily data files are not downloaded in Phase 1. Per
`docs/BUILD_PLAN.md`, they are fetched in a later phase, only for the
stations actually selected by the airport-to-station distance map, to
avoid downloading the full global archive.

## S3: OpenFlights `airports.dat`

No header row; 14 comma-separated fields per line, fields quoted where
they may contain a comma; `\N` marks a null. Verified against the real
downloaded file (confirms the well-known OpenFlights schema):

| # | Column | Example (row 1) |
|---|---|---|
| 1 | Airport ID (OpenFlights internal, not BTS's) | `1` |
| 2 | Name | `Goroka Airport` |
| 3 | City | `Goroka` |
| 4 | Country | `Papua New Guinea` |
| 5 | IATA code | `GKA` |
| 6 | ICAO code | `AYGA` |
| 7 | Latitude (decimal degrees) | `-6.0816...` |
| 8 | Longitude (decimal degrees) | `145.392...` |
| 9 | Altitude (feet) | `5282` |
| 10 | Timezone offset (hours from UTC) | `10` |
| 11 | DST type | `U` |
| 12 | Tz database timezone name | `Pacific/Port_Moresby` |
| 13 | Type | `airport` |
| 14 | Source | `OurAirports` |

Column 5 (IATA) is the join key to S1's `Origin`/`Dest`, per section 3 of
the brief. Columns 7 and 8 feed the haversine distance calculation in
`airport_station_map`.

## S4: BTS lookup tables (carriers, airports, cancellation codes)

**Blocked.** See `docs/DECISIONS.md`, item B1. The classic
`Download_Lookup.asp?Lookup=...` endpoints all redirect to the site
homepage instead of serving the file. Needs a human to check in a real
browser before this is resolved.

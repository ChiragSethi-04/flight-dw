"""Pure transformation functions for Phase 4 cleaning and conforming.

Every function here is pure (same input, same output, no database or
file access) so each one can be unit tested directly, per the brief's
own request for tests covering 2400, 0000, cancelled rows, -9999, and
causes that do not sum.

These implement the rules from brief sections 3 and 4, and the open
decisions resolved in docs/DECISIONS.md:

- 2400 maps to hour 0 / HHMM value 0. fact_flight never builds a full
  timestamp, so the date is never rolled forward (open decision 4).
- Delay cause fields: NULL for cancelled flights, 0 for non-cancelled
  flights with an arrival delay under 15 minutes, cast straight through
  otherwise (brief section 4, problem 3).
- NOAA values: tenths to real units, -9999 to NULL (brief section 4,
  problem 6).
- is_outlier_delay uses a 180-minute cutoff, the same cutoff
  docs/profiling/summary.md already used to report outlier share in
  Phase 2 (110,121 of 7,001,619 rows, 1.57%).
- avg_wind_ms is NULL when the mapped station does not report AWND; no
  secondary station lookup (open decision 3, resolved in Phase 4
  planning).
"""
from typing import Optional

MIDNIGHT_RAW = "2400"
OUTLIER_DELAY_MINUTES = 180
NOAA_MISSING_VALUE = -9999


def parse_bts_decimal(raw: Optional[str]) -> Optional[int]:
    """BTS numeric fields arrive as text like '0.00', '15.00', or ''.
    Returns None for missing/empty, otherwise the integer value (BTS
    delay and time fields are always whole minutes/codes despite the
    '.00' formatting).
    """
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "":
        return None
    return int(float(raw))


def is_flag_set(raw: Optional[str]) -> bool:
    """BTS boolean-style fields are '1.00' / '0.00' text, not 1/0."""
    value = parse_bts_decimal(raw)
    return value == 1


def normalize_hhmm(raw: Optional[str]) -> Optional[int]:
    """Converts a raw BTS hhmm time string to an integer 0-2359.

    '0659' -> 659, '0000' -> 0, '2400' -> 0 (open decision 4: midnight
    is stored as 2400 in the source; mapped to 0 here, with the flight
    date left unchanged since this schema never builds a full
    timestamp that midnight's hour would need to roll into).
    """
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "":
        return None
    if raw == MIDNIGHT_RAW:
        return 0
    return int(raw)


def hour_of_day(hhmm: Optional[int]) -> Optional[int]:
    """Extracts the hour (0-23) from a normalized hhmm integer."""
    if hhmm is None:
        return None
    return hhmm // 100


DEPARTURE_BANDS = (
    (0, 6, "early morning"),   # 00:00-05:59
    (6, 12, "morning"),        # 06:00-11:59
    (12, 17, "afternoon"),     # 12:00-16:59
    (17, 21, "evening"),       # 17:00-20:59
    (21, 24, "night"),         # 21:00-23:59
)


def departure_band(hour: Optional[int]) -> str:
    if hour is None:
        return "Unknown"
    for start, end, name in DEPARTURE_BANDS:
        if start <= hour < end:
            return name
    return "Unknown"


def cause_minutes(raw: Optional[str], arr_delay_min: Optional[int], cancelled: bool) -> Optional[int]:
    """One of the five BTS delay-cause fields (CarrierDelay, WeatherDelay,
    NASDelay, SecurityDelay, LateAircraftDelay), cleaned per brief
    section 4 problem 3.

    - Cancelled flights: always None (BTS leaves these blank; kept NULL,
      never guessed).
    - Non-cancelled, arrival delay under 15 minutes: the brief's rule is
      0, regardless of what BTS actually put in the raw field (it is
      normally blank here too).
    - Non-cancelled, arrival delay >= 15 minutes: cast the raw value
      through as given. If it is blank here, that is a data anomaly
      (BTS is supposed to populate all five causes once a flight
      qualifies); returned as None rather than guessed as 0, so it is
      visible rather than silently hidden.
    """
    if cancelled:
        return None
    if arr_delay_min is not None and arr_delay_min < 15:
        return 0
    return parse_bts_decimal(raw)


def on_time_flag(arr_delay_min: Optional[int], cancelled: bool) -> Optional[bool]:
    """'Delayed' is fixed everywhere as arrival delay >= 15 minutes
    (CLAUDE.md locked decision). None for cancelled flights, where
    on-time does not apply.
    """
    if cancelled:
        return None
    if arr_delay_min is None:
        return None
    return arr_delay_min < 15


def is_outlier_delay(arr_delay_min: Optional[int]) -> Optional[bool]:
    if arr_delay_min is None:
        return None
    return arr_delay_min > OUTLIER_DELAY_MINUTES


def delay_class(arr_delay_min: Optional[int], cancelled: bool, diverted: bool) -> str:
    """The dim_flight_status junk dimension's delay_class component.
    Cancelled takes priority over diverted (a flight cannot be both in
    a way that matters operationally; BTS marks at most one). The
    boundaries mirror on_time_flag (15 minutes) and is_outlier_delay's
    180-minute severity read, with one band in between for an ordinary
    delay.
    """
    if cancelled:
        return "cancelled"
    if diverted:
        return "diverted"
    if arr_delay_min is None:
        return "Unknown"
    if arr_delay_min < 15:
        return "on_time"
    if arr_delay_min <= 180:
        return "minor_delay"
    return "major_delay"


def noaa_value(raw) -> Optional[float]:
    """Converts a raw NOAA tenths-of-a-unit value to real units
    (tenths of mm to mm, tenths of a degree C to degrees C, tenths of
    m/s to m/s, all the same divide-by-10 operation), and the sentinel
    -9999 to None. Accepts either a string or a number.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
        raw = float(raw)
    if raw == NOAA_MISSING_VALUE:
        return None
    return raw / 10.0


DISTANCE_BANDS = (
    (0, 250, "0-250"),
    (250, 500, "250-500"),
    (500, 1000, "500-1000"),
    (1000, 1500, "1000-1500"),
    (1500, 2500, "1500-2500"),
    (2500, float("inf"), "2500+"),
)


def distance_band(miles: Optional[float]) -> str:
    if miles is None:
        return "Unknown"
    for start, end, name in DISTANCE_BANDS:
        if start <= miles < end:
            return name
    return "Unknown"


def precip_band(precip_mm: Optional[float]) -> str:
    if precip_mm is None:
        return "Unknown"
    if precip_mm <= 0:
        return "none"
    if precip_mm <= 2.5:
        return "light"
    if precip_mm <= 10:
        return "moderate"
    if precip_mm <= 25:
        return "heavy"
    return "extreme"


def snow_band(snowfall_mm: Optional[float]) -> str:
    if snowfall_mm is None:
        return "Unknown"
    if snowfall_mm <= 0:
        return "none"
    if snowfall_mm <= 10:
        return "light"
    if snowfall_mm <= 50:
        return "moderate"
    return "heavy"


def wind_band(avg_wind_ms: Optional[float]) -> str:
    if avg_wind_ms is None:
        return "Unknown"
    if avg_wind_ms <= 3:
        return "calm"
    if avg_wind_ms <= 6:
        return "light"
    if avg_wind_ms <= 10:
        return "moderate"
    return "strong"


def temp_band(tmin_c: Optional[float]) -> str:
    """Banded on the day's minimum temperature, since freezing
    conditions (the main weather-driven operational risk this band is
    meant to capture) are about the coldest point in the day, not the
    warmest.
    """
    if tmin_c is None:
        return "Unknown"
    if tmin_c < 0:
        return "below freezing"
    if tmin_c <= 10:
        return "cold"
    if tmin_c <= 20:
        return "mild"
    if tmin_c <= 30:
        return "warm"
    return "hot"

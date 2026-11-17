"""Unit tests for etl/clean.py's pure transformation functions.

Covers the specific edge cases the brief names: 2400, 0000, cancelled
rows, -9999, and causes that do not sum.
"""
from etl.clean import (
    cause_minutes,
    delay_class,
    departure_band,
    distance_band,
    hour_of_day,
    is_flag_set,
    is_outlier_delay,
    noaa_value,
    normalize_hhmm,
    on_time_flag,
    parse_bts_decimal,
    precip_band,
    snow_band,
    temp_band,
    wind_band,
)


# --- normalize_hhmm / hour_of_day: the 2400 and 0000 edge cases -----------

def test_normalize_hhmm_regular_time():
    assert normalize_hhmm("0659") == 659
    assert normalize_hhmm("2359") == 2359


def test_normalize_hhmm_midnight_as_0000():
    assert normalize_hhmm("0000") == 0


def test_normalize_hhmm_midnight_as_2400():
    assert normalize_hhmm("2400") == 0


def test_normalize_hhmm_empty_is_none():
    assert normalize_hhmm("") is None
    assert normalize_hhmm(None) is None


def test_hour_of_day_from_2400():
    assert hour_of_day(normalize_hhmm("2400")) == 0


def test_hour_of_day_regular():
    assert hour_of_day(1430) == 14


def test_hour_of_day_none_is_none():
    assert hour_of_day(None) is None


def test_departure_band_boundaries():
    assert departure_band(0) == "early morning"
    assert departure_band(5) == "early morning"
    assert departure_band(6) == "morning"
    assert departure_band(11) == "morning"
    assert departure_band(12) == "afternoon"
    assert departure_band(16) == "afternoon"
    assert departure_band(17) == "evening"
    assert departure_band(20) == "evening"
    assert departure_band(21) == "night"
    assert departure_band(23) == "night"


def test_departure_band_none_is_unknown():
    assert departure_band(None) == "Unknown"


# --- parse_bts_decimal / is_flag_set ---------------------------------------

def test_parse_bts_decimal_normal():
    assert parse_bts_decimal("15.00") == 15
    assert parse_bts_decimal("0.00") == 0


def test_parse_bts_decimal_empty_is_none():
    assert parse_bts_decimal("") is None
    assert parse_bts_decimal(None) is None


def test_is_flag_set():
    assert is_flag_set("1.00") is True
    assert is_flag_set("0.00") is False
    assert is_flag_set("") is False


# --- cause_minutes: cancelled rows, the <15 rule, and the anomaly case ----

def test_cause_minutes_cancelled_is_always_none():
    assert cause_minutes("45.00", arr_delay_min=200, cancelled=True) is None
    assert cause_minutes("", arr_delay_min=None, cancelled=True) is None


def test_cause_minutes_non_cancelled_under_15_is_zero():
    assert cause_minutes("", arr_delay_min=0, cancelled=False) == 0
    assert cause_minutes("", arr_delay_min=14, cancelled=False) == 0


def test_cause_minutes_non_cancelled_15_or_over_casts_through():
    assert cause_minutes("30.00", arr_delay_min=45, cancelled=False) == 30


def test_cause_minutes_anomaly_blank_cause_with_real_delay_is_none_not_guessed():
    # A flight with a real >=15 minute delay should have all five causes
    # populated by BTS. If one is blank anyway, that is a data anomaly;
    # it must not be silently guessed as 0.
    assert cause_minutes("", arr_delay_min=45, cancelled=False) is None


# --- on_time_flag / is_outlier_delay ---------------------------------------

def test_on_time_flag_cancelled_is_none():
    assert on_time_flag(200, cancelled=True) is None


def test_on_time_flag_threshold():
    assert on_time_flag(14, cancelled=False) is True
    assert on_time_flag(15, cancelled=False) is False


def test_on_time_flag_missing_delay_is_none():
    assert on_time_flag(None, cancelled=False) is None


def test_is_outlier_delay_threshold():
    assert is_outlier_delay(180) is False
    assert is_outlier_delay(181) is True


def test_is_outlier_delay_none_is_none():
    assert is_outlier_delay(None) is None


def test_delay_class_cancelled_takes_priority():
    assert delay_class(None, cancelled=True, diverted=True) == "cancelled"


def test_delay_class_diverted():
    assert delay_class(30, cancelled=False, diverted=True) == "diverted"


def test_delay_class_bands():
    assert delay_class(0, cancelled=False, diverted=False) == "on_time"
    assert delay_class(14, cancelled=False, diverted=False) == "on_time"
    assert delay_class(15, cancelled=False, diverted=False) == "minor_delay"
    assert delay_class(180, cancelled=False, diverted=False) == "minor_delay"
    assert delay_class(181, cancelled=False, diverted=False) == "major_delay"


def test_delay_class_missing_delay_is_unknown():
    assert delay_class(None, cancelled=False, diverted=False) == "Unknown"


# --- noaa_value: the -9999 sentinel and the tenths conversion -------------

def test_noaa_value_converts_tenths():
    assert noaa_value(150) == 15.0
    assert noaa_value("150") == 15.0


def test_noaa_value_minus_9999_is_none():
    assert noaa_value(-9999) is None
    assert noaa_value("-9999") is None


def test_noaa_value_none_is_none():
    assert noaa_value(None) is None
    assert noaa_value("") is None


def test_noaa_value_zero_is_zero_not_none():
    assert noaa_value(0) == 0.0


# --- banding functions ------------------------------------------------------

def test_distance_band():
    assert distance_band(100) == "0-250"
    assert distance_band(250) == "250-500"
    assert distance_band(3000) == "2500+"
    assert distance_band(None) == "Unknown"


def test_precip_band():
    assert precip_band(0) == "none"
    assert precip_band(1) == "light"
    assert precip_band(5) == "moderate"
    assert precip_band(15) == "heavy"
    assert precip_band(30) == "extreme"
    assert precip_band(None) == "Unknown"


def test_snow_band():
    assert snow_band(0) == "none"
    assert snow_band(5) == "light"
    assert snow_band(20) == "moderate"
    assert snow_band(100) == "heavy"
    assert snow_band(None) == "Unknown"


def test_wind_band():
    assert wind_band(1) == "calm"
    assert wind_band(5) == "light"
    assert wind_band(8) == "moderate"
    assert wind_band(15) == "strong"
    assert wind_band(None) == "Unknown"


def test_temp_band():
    assert temp_band(-5) == "below freezing"
    assert temp_band(5) == "cold"
    assert temp_band(15) == "mild"
    assert temp_band(25) == "warm"
    assert temp_band(35) == "hot"
    assert temp_band(None) == "Unknown"

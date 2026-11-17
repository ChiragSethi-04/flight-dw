"""Tests the SCD Type 2 carrier lookup in etl/conform.py.

Open decision 6 (docs/DECISIONS.md): one calendar year of real 2025 BTS
data shows no carrier with more than one version, since there is no
evidence of a mid-year carrier name change in that single year and S4
(the source that would carry carrier history dates) is blocked. Per the
brief's own instruction, the logic is demonstrated here on a synthetic,
clearly labelled test case instead of claimed against real data.

SYNTHETIC DATA WARNING: the carrier code 'ZX' and the version history
below are made up for this test only. They are not in dim_carrier and
do not represent any real airline.
"""
from datetime import date

from etl.conform import resolve_carrier_key

SYNTHETIC_CARRIER_HISTORY = [
    {
        "carrier_key": 9001,
        "carrier_code": "ZX",
        "effective_from": date(2020, 1, 1),
        "effective_to": date(2024, 6, 30),
    },
    {
        "carrier_key": 9002,
        "carrier_code": "ZX",
        "effective_from": date(2024, 7, 1),
        "effective_to": None,
    },
]


def test_resolves_to_the_version_active_on_the_flight_date():
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "ZX", date(2022, 3, 15)) == 9001
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "ZX", date(2025, 1, 1)) == 9002


def test_resolves_correctly_right_at_the_version_boundary():
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "ZX", date(2024, 6, 30)) == 9001
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "ZX", date(2024, 7, 1)) == 9002


def test_unknown_carrier_code_resolves_to_none():
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "QQ", date(2022, 1, 1)) is None


def test_date_before_any_version_resolves_to_none():
    assert resolve_carrier_key(SYNTHETIC_CARRIER_HISTORY, "ZX", date(2019, 12, 31)) is None


def test_single_version_carrier_matches_the_2025_real_data_shape():
    # This is the shape every real 2025 carrier actually has: one
    # version, effective_to NULL, matching regardless of date.
    single_version = [
        {"carrier_key": 1, "carrier_code": "AA", "effective_from": date(2025, 1, 1), "effective_to": None}
    ]
    assert resolve_carrier_key(single_version, "AA", date(2025, 6, 15)) == 1
    assert resolve_carrier_key(single_version, "AA", date(2030, 1, 1)) == 1

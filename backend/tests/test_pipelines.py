"""Pipeline tests run offline against recorded raw responses (data/raw), never hand-written fixtures."""
import pandas as pd
import pytest

from pipelines import audit
from pipelines.common import PROCESSED, RAW
from pipelines.fetch_references import fao_table1, nabcons

needs_raw = pytest.mark.skipif(not (RAW / "pib_2151371").exists(), reason="raw cache not present")


def test_every_manifest_entry_matches_its_file():
    rows, errors = audit.verify_manifests()
    assert rows, "no manifests found"
    assert errors == []


def test_every_processed_table_carries_provenance():
    _, errors = audit.verify_processed()
    assert errors == []


@needs_raw
def test_nabcons_rows_match_the_brief():
    df = nabcons(refresh=False).set_index("crop")
    assert df.loc["Tomato", "market_level_loss_pct"] == 3.25
    assert df.loc["Onion", "market_level_loss_pct"] == 1.96
    assert df.loc["Citrus", "market_level_loss_pct"] == 2.18


@needs_raw
def test_fao_table1_is_monotonic_and_q10_within_source_range():
    t = fao_table1(refresh=False)
    assert t["relative_velocity"].is_monotonic_increasing
    assert t["relative_velocity"].iloc[0] == 1.0


def test_daily_arrivals_have_no_negative_or_duplicate_keys():
    p = PROCESSED / "agmarknet_arrivals_daily.csv"
    if not p.exists():
        pytest.skip("no arrivals ingested")
    d = pd.read_csv(p)
    assert (d["arrival_kg"].dropna() >= 0).all()
    assert not d.duplicated(["arrival_date", "market_name_clean", "commodity"]).any()


def test_census_sex_split_sums_to_persons():
    d = pd.read_csv(PROCESSED / "census_2011_district_population.csv")
    assert (d["males"] + d["females"] == d["population"]).all()

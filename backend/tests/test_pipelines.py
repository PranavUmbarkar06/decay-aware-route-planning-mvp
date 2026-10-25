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


def test_nodes_and_edges_csv_follow_the_9A_schema():
    from pipelines.build_graph import EDGE_COLS, NODE_COLS
    nodes = pd.read_csv(PROCESSED / "nodes.csv")
    edges = pd.read_csv(PROCESSED / "edges.csv", nrows=1000)
    spec_nodes = ["node_id", "node_type", "name", "name_source", "lat", "lon", "district", "osm_id",
                  "agmarknet_market_name", "geocode_method", "geocode_confidence", "snapped_graph_node",
                  "snap_distance_m", "capacity_kg", "capacity_source", "provenance", "source_manifest_id", "needs_review"]
    spec_edges = ["edge_id", "u", "v", "osm_way_id", "highway_class", "length_m", "maxspeed_kmh", "speed_kmh_used",
                  "speed_source", "free_flow_time_s", "oneway", "road_name", "provenance", "source_manifest_id"]
    assert list(nodes.columns)[:len(spec_nodes)] == spec_nodes and list(nodes.columns) == NODE_COLS
    assert list(edges.columns)[:len(spec_edges)] == spec_edges and list(edges.columns) == EDGE_COLS
    assert set(edges["speed_source"].str.replace(r"^mixed:.*", "mixed", regex=True)) <= {
        "osm_maxspeed", "class_default_ASSUMPTION", "mixed"}
    # demo nodes are fictional, labelled and never carry an OSM id
    demo = nodes[nodes["provenance"] == "SYNTHETIC_DEMO"]
    assert demo["name"].str.endswith("DEMO").all() and demo["osm_id"].isna().all()
    # capacity is never invented for real nodes
    real = nodes[nodes["provenance"] != "SYNTHETIC_DEMO"]
    assert real["capacity_kg"].isna().all()

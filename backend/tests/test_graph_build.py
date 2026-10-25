"""Graph-build unit tests (in memory; never overwrite data/processed)."""
import networkx as nx
import pandas as pd
import pytest

from pipelines import build_graph as bg


@pytest.mark.parametrize("raw,expected", [("50", 50.0), ("40 mph", 64.37376), ("60;80", 60.0),
                                          ("IN:urban", None), (None, None), ("signals", None)])
def test_parse_maxspeed(raw, expected):
    got = bg.parse_maxspeed(raw)
    assert got == pytest.approx(expected) if expected is not None else got is None


def test_speed_for_caps_and_labels():
    sp, src, ms = bg.speed_for("trunk", "100")
    assert src == "osm_maxspeed" and ms == 100 and sp <= 60   # truck cap from speeds.yaml
    sp, src, ms = bg.speed_for("primary", None)
    assert src == "class_default_ASSUMPTION" and ms is None


@pytest.mark.parametrize("oneway,junction,expected", [("yes", None, (True, False)), ("-1", None, (True, True)),
                                                       (None, "roundabout", (True, False)), ("no", "roundabout", (False, False)),
                                                       (None, None, (False, False))])
def test_oneway_semantics(oneway, junction, expected):
    assert bg.is_oneway(oneway, junction) == expected


@pytest.mark.parametrize("name,town", [("APMC Hingna", "Hingna"), ("Chandrapur(Ganjwad)", "Chandrapur"),
                                       ("Sindi (Selu)", "Sindi"),
                                       ("Hinganghat Infrastructure Pvt Ltd, Hinganghat, Dist Wardha", "Hinganghat"),
                                       ("M/S Kalpana Agri Commodities Marketing, Nagpur", "Nagpur")])
def test_market_town_token(name, town):
    assert bg.market_town_token(name)[0] == town


def test_graph_from_ways_respects_oneway():
    ways = pd.DataFrame([
        {"way_id": 1, "highway": "primary", "maxspeed": None, "oneway": "yes", "junction": None, "name": "A",
         "node_ids": [1, 2], "lons": [79.0, 79.01], "lats": [21.0, 21.0]},
        {"way_id": 2, "highway": "secondary", "maxspeed": "40", "oneway": None, "junction": None, "name": "B",
         "node_ids": [2, 3], "lons": [79.01, 79.02], "lats": [21.0, 21.0]},
    ])
    G = bg.graph_from_ways(ways)
    assert G.has_edge(1, 2) and not G.has_edge(2, 1)
    assert G.has_edge(2, 3) and G.has_edge(3, 2)
    d = next(iter(G[2][3].values()))
    assert d["speed_source"] == "osm_maxspeed" and d["length"] == pytest.approx(1038, rel=0.01)


def test_synthetic_fallback_is_labelled_and_connected():
    stats = bg.BuildStats()
    G, mid = bg.build_synthetic(stats)
    assert stats.synthetic and mid.startswith("synthetic")
    assert nx.is_strongly_connected(G)
    edges = bg.edges_frame(G, mid, "SYNTHETIC_DEMO")
    assert set(edges["provenance"]) == {"SYNTHETIC_DEMO"}
    assert (edges["length_m"] > 0).all() and not edges["edge_id"].duplicated().any()


def test_stable_ids_are_deterministic():
    assert bg.stable_id("N", "AssemblyMandi", "agmarknet:155") == bg.stable_id("N", "AssemblyMandi", "agmarknet:155")
    assert bg.stable_id("N", "a", "b") != bg.stable_id("N", "a", "c")


@pytest.mark.parametrize("a,b", [("Savner", "Saoner"), ("Varora", "Warora"), ("Pavani", "Pauni"),
                                 ("Brahmpuri", "Bramhapuri"), ("Savali", "Saoli")])
def test_transliteration_skeleton_matches_known_variants(a, b):
    assert bg.skeleton(a) == bg.skeleton(b)


def test_skeleton_does_not_merge_different_towns():
    assert bg.skeleton("Nagpur") != bg.skeleton("Narkhed")

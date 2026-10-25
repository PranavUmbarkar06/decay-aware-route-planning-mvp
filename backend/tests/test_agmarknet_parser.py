"""Parser tests use the first rows of a real owner-downloaded export (recorded, not hand-written)."""
from pathlib import Path

import pytest

from pipelines.fetch_agmarknet import HEADER, UNIT_TO_KG, parse_export

FIX = Path(__file__).parent / "fixtures"


def test_real_export_header_and_numbers():
    df = parse_export(FIX / "agmarknet_export_tomato_head.csv")
    assert list(df.columns) == HEADER
    assert len(df) == 4
    # thousands separators parsed: "1,600.00" -> 1600.0
    assert df["Max Price"].max() == 1600.0
    assert set(df["Arrival Unit"]) == {"Metric Tonnes"}
    assert UNIT_TO_KG["metric tonnes"] == 1000.0


def test_unexpected_format_is_rejected_not_guessed():
    with pytest.raises(ValueError):
        parse_export(FIX / "not_an_agmarknet_export.csv")

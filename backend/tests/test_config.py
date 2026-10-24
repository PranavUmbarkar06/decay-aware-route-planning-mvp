import pytest
import yaml
from app.core import config as cfg
from app.core.provenance import Provenance, weakest
from pydantic import ValidationError


def test_all_configs_validate():
    assert cfg.app_config().product_name
    assert cfg.commodities_config().q10.range == (2.0, 3.0)
    assert cfg.thresholds().traffic_light.red_below_h < cfg.thresholds().traffic_light.green_at_or_above_h
    assert len(cfg.geography().current.districts) == 6
    assert cfg.speeds().provenance == "ASSUMPTION"


def test_unknown_key_fails_fast():
    raw = yaml.safe_load((cfg.CONFIG_DIR / "config.yaml").read_text(encoding="utf-8"))
    raw["surprise_key"] = 1
    with pytest.raises(ValidationError):
        cfg.AppConfig.model_validate(raw)


def test_traffic_light_rejects_overlap():
    with pytest.raises(ValidationError):
        cfg.TrafficLight(provenance="ASSUMPTION", needs_confirmation_with_operators=True,
                         red_below_h=72, green_at_or_above_h=24)


def test_weakest_provenance():
    assert weakest(Provenance.REAL_FETCHED) == Provenance.REAL_DERIVED
    assert weakest(Provenance.REAL_FETCHED, Provenance.ASSUMPTION) == Provenance.ASSUMPTION
    assert weakest(Provenance.USER_ENTERED, Provenance.SYNTHETIC_DEMO) == Provenance.SYNTHETIC_DEMO

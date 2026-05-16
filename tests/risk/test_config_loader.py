"""Tests for core/risk/config_loader.py — YAML loading + pydantic validation."""

import tempfile
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.risk.config_loader import RiskConfig, load_risk_config
from core.risk.types import Regime

DEFAULT_YAML = """
max_risk_per_trade_pct: 0.0025
max_leverage_by_regime:
  TREND_UP: 3
  TREND_DOWN: 3
  RANGE_LOW_VOL: 2
  RANGE_HIGH_VOL: 2
  CRISIS: 1
  UNKNOWN: 1
max_total_exposure_pct: 2.0
max_correlated_exposure_pct: 1.0
daily_dd_reduce_size: 0.02
daily_dd_halt: 0.03
daily_dd_close_all: 0.05
weekly_dd_emergency: 0.08
halt_cooldown_hours: 4
close_all_cooldown_hours: 24
margin_ratio_warning: 0.50
margin_ratio_force_reduce: 0.70
min_stop_to_liquidation_ratio: 2.0
"""


def _write_temp_yaml(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestRiskConfigModel:
    def test_default_values(self) -> None:
        config = RiskConfig()
        assert config.max_risk_per_trade_pct == 0.0025
        assert config.max_total_exposure_pct == 2.0
        assert config.max_correlated_exposure_pct == 1.0
        assert config.daily_dd_reduce_size == 0.02
        assert config.daily_dd_halt == 0.03
        assert config.daily_dd_close_all == 0.05
        assert config.weekly_dd_emergency == 0.08
        assert config.halt_cooldown_hours == 4
        assert config.close_all_cooldown_hours == 24
        assert config.margin_ratio_warning == 0.50
        assert config.margin_ratio_force_reduce == 0.70
        assert config.min_stop_to_liquidation_ratio == 2.0

    def test_default_leverage_by_regime(self) -> None:
        config = RiskConfig()
        assert config.max_leverage_by_regime[Regime.TREND_UP] == 3
        assert config.max_leverage_by_regime[Regime.TREND_DOWN] == 3
        assert config.max_leverage_by_regime[Regime.RANGE_LOW_VOL] == 2
        assert config.max_leverage_by_regime[Regime.RANGE_HIGH_VOL] == 2
        assert config.max_leverage_by_regime[Regime.CRISIS] == 1
        assert config.max_leverage_by_regime[Regime.UNKNOWN] == 1

    def test_all_regimes_have_leverage_defined(self) -> None:
        config = RiskConfig()
        for regime in Regime:
            assert regime in config.max_leverage_by_regime, f"Missing leverage for regime {regime}"

    def test_config_is_frozen(self) -> None:
        config = RiskConfig()
        with pytest.raises(ValidationError):
            config.max_risk_per_trade_pct = 0.01  # type: ignore[misc]

    def test_invalid_max_risk_per_trade_pct_negative(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(max_risk_per_trade_pct=-0.01)

    def test_invalid_max_risk_per_trade_pct_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(max_risk_per_trade_pct=0.02)

    def test_invalid_drawdown_order(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(
                daily_dd_reduce_size=0.05,
                daily_dd_halt=0.03,
            )

    def test_margin_ratio_warning_gt_force_reduce(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(
                margin_ratio_warning=0.80,
                margin_ratio_force_reduce=0.60,
            )

    def test_invalid_halt_cooldown_negative(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(halt_cooldown_hours=0)

    def test_from_dict(self) -> None:
        config = RiskConfig.from_dict({"max_risk_per_trade_pct": 0.005})
        assert config.max_risk_per_trade_pct == 0.005
        assert config.max_total_exposure_pct == 2.0  # default

    def test_from_dict_partial_override(self) -> None:
        config = RiskConfig.from_dict(
            {
                "max_risk_per_trade_pct": 0.003,
                "halt_cooldown_hours": 8,
                "max_leverage_by_regime": {
                    "TREND_UP": 5,
                },
            }
        )
        assert config.max_risk_per_trade_pct == 0.003
        assert config.halt_cooldown_hours == 8
        assert config.max_leverage_by_regime[Regime.TREND_UP] == 5
        assert config.max_leverage_by_regime[Regime.UNKNOWN] == 1  # default

    # ---- adversarial: config loader hardening ----

    def test_from_dict_does_not_mutate_input(self) -> None:
        data: dict = {
            "max_risk_per_trade_pct": 0.004,
            "max_leverage_by_regime": {"TREND_UP": 3},
        }
        original = deepcopy(data)
        RiskConfig.from_dict(data)
        assert data == original, "from_dict must not mutate the input dictionary"

    def test_leverage_above_cap_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Leverage for TREND_UP must be in"):
            RiskConfig.from_dict({"max_leverage_by_regime": {"TREND_UP": 50}})

    def test_leverage_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Leverage for TREND_UP must be in"):
            RiskConfig.from_dict({"max_leverage_by_regime": {"TREND_UP": 0}})

    def test_weekly_dd_must_exceed_daily_close_all(self) -> None:
        with pytest.raises(ValidationError, match="weekly_dd_emergency must exceed"):
            RiskConfig(
                daily_dd_close_all=0.05,
                weekly_dd_emergency=0.04,
            )

    def test_unknown_regime_key_clear_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown regime key"):
            RiskConfig.from_dict({"max_leverage_by_regime": {"BULL_MARKET": 3}})

    def test_all_regimes_present_validator_exercised(self) -> None:
        """Exercise the config_loader.py:102 branch — missing regime entries.
        Construct RiskConfig directly (bypassing from_dict defaults) so the
        missing-regime validator fires."""
        with pytest.raises(ValidationError, match="Missing max_leverage_by_regime entries"):
            RiskConfig(
                max_leverage_by_regime={
                    Regime.TREND_UP: 3,
                    Regime.TREND_DOWN: 3,
                    Regime.RANGE_LOW_VOL: 2,
                    Regime.RANGE_HIGH_VOL: 2,
                    # CRISIS intentionally missing
                    Regime.UNKNOWN: 1,
                }
            )


class TestLoadRiskConfig:
    def test_load_default_yaml(self) -> None:
        path = _write_temp_yaml(DEFAULT_YAML)
        try:
            config = load_risk_config(str(path))
            assert config.max_risk_per_trade_pct == 0.0025
            assert config.max_leverage_by_regime[Regime.TREND_UP] == 3
            assert config.daily_dd_close_all == 0.05
        finally:
            path.unlink(missing_ok=True)

    def test_load_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_risk_config("nonexistent/config.yaml")

    def test_load_invalid_yaml_syntax(self) -> None:
        path = _write_temp_yaml("max_risk_per_trade_pct: 0.0025\n  bad_indent: true")
        try:
            with pytest.raises(yaml.YAMLError):
                load_risk_config(str(path))
        finally:
            path.unlink(missing_ok=True)

    def test_load_missing_required_fields(self) -> None:
        path = _write_temp_yaml("max_risk_per_trade_pct: 0.0025\n")
        try:
            config = load_risk_config(str(path))
            assert config.max_risk_per_trade_pct == 0.0025
        finally:
            path.unlink(missing_ok=True)

    def test_load_partial_leverage_regime(self) -> None:
        yaml_content = """
max_risk_per_trade_pct: 0.0025
max_leverage_by_regime:
  TREND_UP: 5
"""
        path = _write_temp_yaml(yaml_content)
        try:
            config = load_risk_config(str(path))
            assert config.max_leverage_by_regime[Regime.TREND_UP] == 5
            assert config.max_leverage_by_regime[Regime.CRISIS] == 1
        finally:
            path.unlink(missing_ok=True)

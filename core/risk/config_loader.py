# core/risk/config_loader.py
"""Load and validate config/risk.yaml via pydantic.

Produces an immutable ``RiskConfig`` instance consumed by all risk modules.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.risk.types import Regime

_DEFAULT_LEVERAGE: dict[Regime, int] = {
    Regime.TREND_UP: 3,
    Regime.TREND_DOWN: 3,
    Regime.RANGE_LOW_VOL: 2,
    Regime.RANGE_HIGH_VOL: 2,
    Regime.CRISIS: 1,
    Regime.UNKNOWN: 1,
}

_LEVERAGE_MIN = 1
_LEVERAGE_MAX = 5


class RiskConfig(BaseModel):
    """Immutable risk configuration validated from YAML.

    All defaults match docs/03-risk-manager-spec.md.  Fields are frozen
    after construction per AD-010 (no runtime overrides).
    """

    model_config = ConfigDict(frozen=True)

    max_risk_per_trade_pct: float = Field(
        default=0.0025, gt=0, le=0.01, description="Max risk per trade (Règle 1)"
    )
    max_leverage_by_regime: dict[Regime, int] = Field(
        default_factory=lambda: _DEFAULT_LEVERAGE.copy(),
        description="Dynamic leverage cap by market regime (Règle 3)",
    )
    max_total_exposure_pct: float = Field(
        default=2.0, gt=0, le=5.0, description="Max total exposure as fraction of balance (Règle 4)"
    )
    max_correlated_exposure_pct: float = Field(
        default=1.0, gt=0, le=2.0, description="Max exposure per correlation group (Règle 4)"
    )

    daily_dd_reduce_size: float = Field(
        default=0.02, gt=0, le=0.10, description="Daily DD threshold for REDUCED_SIZE (Règle 5)"
    )
    daily_dd_halt: float = Field(
        default=0.03, gt=0, le=0.10, description="Daily DD threshold for HALT_NEW_TRADES (Règle 5)"
    )
    daily_dd_close_all: float = Field(
        default=0.05, gt=0, le=0.10, description="Daily DD threshold for CLOSE_ALL (Règle 5)"
    )
    weekly_dd_emergency: float = Field(
        default=0.08, gt=0, le=0.20, description="Weekly DD threshold for EMERGENCY (Règle 5)"
    )
    halt_cooldown_hours: int = Field(default=4, ge=1, description="Cooldown for HALT level")
    close_all_cooldown_hours: int = Field(
        default=24, ge=1, description="Cooldown for CLOSE_ALL level"
    )

    margin_ratio_warning: float = Field(
        default=0.50, gt=0, le=1.0, description="Margin ratio warning threshold (Règle 6)"
    )
    margin_ratio_force_reduce: float = Field(
        default=0.70, gt=0, le=1.0, description="Margin ratio force-reduce threshold (Règle 6)"
    )

    min_stop_to_liquidation_ratio: float = Field(
        default=2.0, gt=0, description="Minimum ratio of stop distance to liquidation distance"
    )

    @model_validator(mode="after")
    def _validate_drawdown_order(self) -> RiskConfig:
        if not (self.daily_dd_reduce_size < self.daily_dd_halt < self.daily_dd_close_all):
            raise ValueError(
                "Drawdown thresholds must be strictly increasing: "
                f"reduce={self.daily_dd_reduce_size} halt={self.daily_dd_halt} "
                f"close_all={self.daily_dd_close_all}"
            )
        if not (self.daily_dd_close_all < self.weekly_dd_emergency):
            raise ValueError(
                "weekly_dd_emergency must exceed daily_dd_close_all: "
                f"close_all={self.daily_dd_close_all} "
                f"emergency={self.weekly_dd_emergency}"
            )
        return self

    @model_validator(mode="after")
    def _validate_margin_ratio_order(self) -> RiskConfig:
        if self.margin_ratio_warning >= self.margin_ratio_force_reduce:
            raise ValueError(
                "margin_ratio_warning must be strictly less than margin_ratio_force_reduce"
            )
        return self

    @model_validator(mode="after")
    def _validate_all_regimes_present(self) -> RiskConfig:
        missing = set(Regime) - set(self.max_leverage_by_regime.keys())
        if missing:
            raise ValueError(f"Missing max_leverage_by_regime entries for: {missing}")
        return self

    @model_validator(mode="after")
    def _validate_leverage_bounds(self) -> RiskConfig:
        """Hard safety guard: every regime's leverage must be in the allowed range."""
        for regime, lev in self.max_leverage_by_regime.items():
            if not (_LEVERAGE_MIN <= lev <= _LEVERAGE_MAX):
                raise ValueError(
                    f"Leverage for {regime.value} must be in "
                    f"[{_LEVERAGE_MIN}, {_LEVERAGE_MAX}], got {lev}"
                )
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskConfig:
        """Build a RiskConfig from a raw dictionary, applying defaults for missing keys.

        The input dictionary is never mutated — a deep copy is used internally.
        Leverage bounds are enforced by the model validator ``_validate_leverage_bounds``.
        """
        data = deepcopy(data)
        if "max_leverage_by_regime" in data:
            merged_leverage = _DEFAULT_LEVERAGE.copy()
            for key, value in data["max_leverage_by_regime"].items():
                try:
                    regime = Regime(key)
                except ValueError as exc:
                    raise ValueError(
                        f"Unknown regime key: {key!r}. Valid keys: {[r.value for r in Regime]}"
                    ) from exc
                merged_leverage[regime] = int(value)
            data["max_leverage_by_regime"] = merged_leverage
        return cls(**data)


def load_risk_config(path: str = "config/risk.yaml") -> RiskConfig:
    """Load and validate risk configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A frozen, validated ``RiskConfig`` instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the YAML values fail validation.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Risk config not found: {path}")

    with open(file_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return RiskConfig.from_dict(raw)

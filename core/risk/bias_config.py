# core/risk/bias_config.py
"""Load and validate config/bias.yaml via pydantic.

Produces an immutable ``BiasConfig`` instance — the sole canonical source
for bias composite weights (AD-022).  All hard-coded weight values in
documentation are superseded by this model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_WEIGHT_SUM_TOLERANCE = 1e-9


class BiasWeights(BaseModel):
    """Immutable bias composite weights.  Must sum to 1.0."""

    model_config = ConfigDict(frozen=True)

    structural: float = Field(
        default=0.50, gt=0, lt=1, description="Weight for structural bias (trend 1H + external 4H)"
    )
    llm_macro: float = Field(
        default=0.20, gt=0, lt=1, description="Weight for LLM macro context (DeepSeek V4)"
    )
    on_chain: float = Field(
        default=0.15,
        gt=0,
        lt=1,
        description="Weight for on-chain data (netflow + stablecoins + delta)",
    )
    funding: float = Field(
        default=0.15, gt=0, lt=1, description="Weight for funding rate adjustment"
    )

    @model_validator(mode="after")
    def _validate_weights_sum_to_one(self) -> BiasWeights:
        total = self.structural + self.llm_macro + self.on_chain + self.funding
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"Bias weights must sum to 1.0 (±{_WEIGHT_SUM_TOLERANCE}), got {total}"
            )
        return self


class BiasConfig(BaseModel):
    """Top-level bias configuration frozen after load."""

    model_config = ConfigDict(frozen=True)

    weights: BiasWeights = Field(default_factory=BiasWeights)


def load_bias_config(path: str = "config/bias.yaml") -> BiasConfig:
    """Load and validate bias configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A frozen, validated ``BiasConfig`` instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the values fail validation.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Bias config not found: {path}")

    with open(file_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return BiasConfig(**raw)

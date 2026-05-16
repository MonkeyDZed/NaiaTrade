"""Tests for core/risk/bias_config.py — canonical bias weights."""

import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.risk.bias_config import BiasConfig, BiasWeights, load_bias_config

DEFAULT_BIAS_YAML = """
weights:
  structural: 0.50
  llm_macro: 0.20
  on_chain: 0.15
  funding: 0.15
"""


def _write_temp_yaml(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestBiasWeights:
    def test_default_weights(self) -> None:
        w = BiasWeights()
        assert w.structural == 0.50
        assert w.llm_macro == 0.20
        assert w.on_chain == 0.15
        assert w.funding == 0.15

    def test_default_weights_sum_to_one(self) -> None:
        w = BiasWeights()
        total = w.structural + w.llm_macro + w.on_chain + w.funding
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match="must sum to 1.0"):
            BiasWeights(structural=0.60, llm_macro=0.20, on_chain=0.15, funding=0.15)

    def test_weights_are_frozen(self) -> None:
        w = BiasWeights()
        with pytest.raises(ValidationError):
            w.structural = 0.60  # type: ignore[misc]

    def test_weight_greater_than_zero(self) -> None:
        with pytest.raises(ValidationError):
            BiasWeights(structural=0.0, llm_macro=0.30, on_chain=0.30, funding=0.40)

    def test_weight_less_than_one(self) -> None:
        with pytest.raises(ValidationError):
            BiasWeights(structural=1.0, llm_macro=0.50, on_chain=0.10, funding=0.10)


class TestBiasConfig:
    def test_default_config(self) -> None:
        config = BiasConfig()
        assert config.weights.structural == 0.50
        assert config.weights.llm_macro == 0.20
        assert config.weights.on_chain == 0.15
        assert config.weights.funding == 0.15

    def test_config_is_frozen(self) -> None:
        config = BiasConfig()
        with pytest.raises(ValidationError):
            config.weights = BiasWeights()  # type: ignore[misc]


class TestLoadBiasConfig:
    def test_load_default_yaml(self) -> None:
        path = _write_temp_yaml(DEFAULT_BIAS_YAML)
        try:
            config = load_bias_config(str(path))
            w = config.weights
            assert w.structural == 0.50
            assert w.llm_macro == 0.20
            assert w.on_chain == 0.15
            assert w.funding == 0.15
        finally:
            path.unlink(missing_ok=True)

    def test_load_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_bias_config("nonexistent/bias.yaml")

    def test_load_invalid_yaml_syntax(self) -> None:
        path = _write_temp_yaml("weights:\n  structural: 0.50\n    bad_nesting: true\n")
        try:
            with pytest.raises(yaml.YAMLError):
                load_bias_config(str(path))
        finally:
            path.unlink(missing_ok=True)

    def test_load_invalid_weights_rejected(self) -> None:
        yaml_content = (
            "weights:\n  structural: 0.80\n  llm_macro: 0.10\n  on_chain: 0.10\n  funding: 0.10"
        )
        path = _write_temp_yaml(yaml_content)
        try:
            with pytest.raises(ValidationError, match="must sum to 1.0"):
                load_bias_config(str(path))
        finally:
            path.unlink(missing_ok=True)

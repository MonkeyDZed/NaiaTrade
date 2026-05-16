"""Tests for core/risk/types.py — enums and frozen dataclasses."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID

import pytest

from core.risk.types import (
    AssessmentAction,
    CorrelationGroup,
    KillSwitchLevel,
    Regime,
    RiskAssessment,
    Side,
    TradeIntent,
    ValidationResult,
)


class TestSideEnum:
    def test_side_values(self) -> None:
        assert Side.LONG == "LONG"
        assert Side.SHORT == "SHORT"

    def test_side_from_string(self) -> None:
        assert Side("LONG") == Side.LONG
        assert Side("SHORT") == Side.SHORT

    def test_side_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            Side("BOTH")


class TestRegimeEnum:
    def test_regime_values(self) -> None:
        assert Regime.TREND_UP == "TREND_UP"
        assert Regime.TREND_DOWN == "TREND_DOWN"
        assert Regime.RANGE_LOW_VOL == "RANGE_LOW_VOL"
        assert Regime.RANGE_HIGH_VOL == "RANGE_HIGH_VOL"
        assert Regime.CRISIS == "CRISIS"
        assert Regime.UNKNOWN == "UNKNOWN"

    def test_regime_from_string(self) -> None:
        assert Regime("TREND_UP") == Regime.TREND_UP
        assert Regime("CRISIS") == Regime.CRISIS

    def test_regime_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            Regime("BULL_MARKET")


class TestKillSwitchLevelEnum:
    def test_kill_switch_values(self) -> None:
        assert KillSwitchLevel.NORMAL == "NORMAL"
        assert KillSwitchLevel.REDUCED_SIZE == "REDUCED"
        assert KillSwitchLevel.HALT_NEW_TRADES == "HALT"
        assert KillSwitchLevel.CLOSE_ALL == "CLOSE_ALL"
        assert KillSwitchLevel.EMERGENCY == "EMERGENCY"

    def test_kill_switch_ordering(self) -> None:
        levels = list(KillSwitchLevel)
        assert levels[0] == KillSwitchLevel.NORMAL
        assert levels[-1] == KillSwitchLevel.EMERGENCY

    def test_kill_switch_comparison(self) -> None:
        assert KillSwitchLevel.NORMAL < KillSwitchLevel.REDUCED_SIZE
        assert KillSwitchLevel.REDUCED_SIZE < KillSwitchLevel.HALT_NEW_TRADES
        assert KillSwitchLevel.HALT_NEW_TRADES < KillSwitchLevel.CLOSE_ALL
        assert KillSwitchLevel.CLOSE_ALL < KillSwitchLevel.EMERGENCY

    def test_kill_switch_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            KillSwitchLevel("INVALID")


class TestAssessmentActionEnum:
    def test_assessment_action_values(self) -> None:
        assert AssessmentAction.APPROVED == "APPROVED"
        assert AssessmentAction.REJECTED == "REJECTED"
        assert AssessmentAction.REDUCED == "REDUCED"

    def test_assessment_action_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            AssessmentAction("PENDING")


class TestCorrelationGroupEnum:
    def test_correlation_group_values(self) -> None:
        assert CorrelationGroup.BTC_CLUSTER == "btc_cluster"
        assert CorrelationGroup.ALT_L1 == "alt_l1"
        assert CorrelationGroup.MEME == "meme"
        assert CorrelationGroup.DEFI == "defi"

    def test_correlation_group_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            CorrelationGroup("nft")


class TestTradeIntent:
    def test_trade_intent_creation_long(self) -> None:
        intent = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        )
        assert isinstance(intent.id, UUID)
        assert intent.symbol == "BTCUSDT"
        assert intent.side == Side.LONG
        assert intent.entry_price == 50000.0
        assert intent.stop_loss == 49500.0
        assert intent.size == 0.1
        assert intent.leverage == 2
        assert intent.regime == Regime.TREND_UP
        assert intent.capital == 10000.0
        assert intent.take_profit is None

    def test_trade_intent_creation_short_with_tp(self) -> None:
        intent = TradeIntent(
            symbol="ETHUSDT",
            side=Side.SHORT,
            entry_price=3000.0,
            stop_loss=3050.0,
            size=0.5,
            leverage=1,
            regime=Regime.CRISIS,
            capital=5000.0,
            total_balance=5000.0,
            used_margin=1500.0,
            take_profit=2900.0,
        )
        assert intent.side == Side.SHORT
        assert intent.entry_price == 3000.0
        assert intent.stop_loss == 3050.0
        assert intent.take_profit == 2900.0
        assert intent.regime == Regime.CRISIS
        assert intent.leverage == 1

    def test_trade_intent_immutable(self) -> None:
        intent = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=1,
            regime=Regime.UNKNOWN,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=0.0,
        )
        with pytest.raises(FrozenInstanceError):
            intent.size = 0.2  # type: ignore[misc]

    def test_trade_intent_default_id_unique(self) -> None:
        intent1 = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=1,
            regime=Regime.UNKNOWN,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=0.0,
        )
        intent2 = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=1,
            regime=Regime.UNKNOWN,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=0.0,
        )
        assert intent1.id != intent2.id

    def test_trade_intent_risk_per_unit_long(self) -> None:
        intent = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        )
        assert intent.risk_per_unit == 500.0

    def test_trade_intent_risk_per_unit_short(self) -> None:
        intent = TradeIntent(
            symbol="ETHUSDT",
            side=Side.SHORT,
            entry_price=3000.0,
            stop_loss=3100.0,
            size=1.0,
            leverage=2,
            regime=Regime.TREND_DOWN,
            capital=5000.0,
            total_balance=5000.0,
            used_margin=750.0,
        )
        assert intent.risk_per_unit == 100.0

    def test_trade_intent_notional_value(self) -> None:
        intent = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        )
        assert intent.notional == 5000.0

    # ---- adversarial: structural validation at construction ----

    def test_trade_intent_rejects_stop_equals_entry(self) -> None:
        with pytest.raises(ValueError, match="stop_loss must not equal entry_price"):
            TradeIntent(
                symbol="BTCUSDT",
                side=Side.LONG,
                entry_price=50000.0,
                stop_loss=50000.0,
                size=0.1,
                leverage=2,
                regime=Regime.TREND_UP,
                capital=10000.0,
                total_balance=10000.0,
                used_margin=2500.0,
            )

    def test_trade_intent_rejects_long_stop_above_entry(self) -> None:
        with pytest.raises(ValueError, match="LONG requires stop_loss < entry_price"):
            TradeIntent(
                symbol="BTCUSDT",
                side=Side.LONG,
                entry_price=50000.0,
                stop_loss=51000.0,
                size=0.1,
                leverage=2,
                regime=Regime.TREND_UP,
                capital=10000.0,
                total_balance=10000.0,
                used_margin=2500.0,
            )

    def test_trade_intent_rejects_short_stop_below_entry(self) -> None:
        with pytest.raises(ValueError, match="SHORT requires stop_loss > entry_price"):
            TradeIntent(
                symbol="ETHUSDT",
                side=Side.SHORT,
                entry_price=3000.0,
                stop_loss=2900.0,
                size=0.5,
                leverage=2,
                regime=Regime.TREND_DOWN,
                capital=5000.0,
                total_balance=5000.0,
                used_margin=750.0,
            )

    def test_trade_intent_rejects_non_positive_price(self) -> None:
        with pytest.raises(ValueError, match="entry_price must be > 0"):
            TradeIntent(
                symbol="BTCUSDT",
                side=Side.LONG,
                entry_price=0.0,
                stop_loss=49000.0,
                size=0.1,
                leverage=2,
                regime=Regime.TREND_UP,
                capital=10000.0,
                total_balance=10000.0,
                used_margin=2500.0,
            )

    def test_trade_intent_rejects_zero_size(self) -> None:
        with pytest.raises(ValueError, match="size must be > 0"):
            TradeIntent(
                symbol="BTCUSDT",
                side=Side.LONG,
                entry_price=50000.0,
                stop_loss=49500.0,
                size=0.0,
                leverage=2,
                regime=Regime.TREND_UP,
                capital=10000.0,
                total_balance=10000.0,
                used_margin=2500.0,
            )

    def test_trade_intent_rejects_tp_wrong_side(self) -> None:
        with pytest.raises(ValueError, match="LONG requires take_profit > entry_price"):
            TradeIntent(
                symbol="BTCUSDT",
                side=Side.LONG,
                entry_price=50000.0,
                stop_loss=49500.0,
                size=0.1,
                leverage=2,
                regime=Regime.TREND_UP,
                capital=10000.0,
                total_balance=10000.0,
                used_margin=2500.0,
                take_profit=49000.0,
            )


class TestValidationResult:
    def test_validation_result_approved(self) -> None:
        result = ValidationResult(approved=True)
        assert result.approved is True
        assert result.reason is None

    def test_validation_result_rejected_with_reason(self) -> None:
        result = ValidationResult(approved=False, reason="stop_loss_distance_invalid")
        assert result.approved is False
        assert result.reason == "stop_loss_distance_invalid"

    def test_validation_result_immutable(self) -> None:
        result = ValidationResult(approved=True)
        with pytest.raises(FrozenInstanceError):
            result.approved = False  # type: ignore[misc]


class TestRiskAssessment:
    def test_risk_assessment_approved(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.APPROVED,
        )
        assert assessment.trade_intent_id == intent_id
        assert assessment.action == AssessmentAction.APPROVED
        assert assessment.reason is None
        assert assessment.adjusted_size is None
        assert isinstance(assessment.timestamp, datetime)

    def test_risk_assessment_rejected(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.REJECTED,
            reason="max_exposure_exceeded",
        )
        assert assessment.action == AssessmentAction.REJECTED
        assert assessment.reason == "max_exposure_exceeded"
        assert assessment.adjusted_size is None

    def test_risk_assessment_reduced(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.REDUCED,
            reason="kill_switch_reduced_size",
            adjusted_size=0.05,
        )
        assert assessment.action == AssessmentAction.REDUCED
        assert assessment.adjusted_size == 0.05

    def test_risk_assessment_immutable(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.APPROVED,
        )
        with pytest.raises(FrozenInstanceError):
            assessment.action = AssessmentAction.REJECTED  # type: ignore[misc]

    def test_risk_assessment_default_timestamp(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        before = datetime.now(timezone.utc)  # noqa: UP017
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.APPROVED,
        )
        after = datetime.now(timezone.utc)  # noqa: UP017
        assert before <= assessment.timestamp <= after

    def test_risk_assessment_timestamp_is_timezone_aware(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.APPROVED,
        )
        assert assessment.timestamp.tzinfo is not None

    def test_risk_assessment_timestamp_is_utc(self) -> None:
        intent_id = TradeIntent(
            symbol="BTCUSDT",
            side=Side.LONG,
            entry_price=50000.0,
            stop_loss=49500.0,
            size=0.1,
            leverage=2,
            regime=Regime.TREND_UP,
            capital=10000.0,
            total_balance=10000.0,
            used_margin=2500.0,
        ).id
        assessment = RiskAssessment(
            trade_intent_id=intent_id,
            action=AssessmentAction.APPROVED,
        )
        assert assessment.timestamp.tzinfo == timezone.utc  # noqa: UP017

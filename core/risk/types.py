# core/risk/types.py
"""Core types for the Risk Manager (Phase 1).

Defines enums and frozen dataclasses used across all risk modules.
Strict typing enforced via mypy (strict=true) and frozen instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]  # noqa: UP042,PLC0415
        """Compatibility shim for Python < 3.11."""

        __str__ = str.__str__


class Side(StrEnum):
    """Trade direction."""

    LONG = "LONG"
    SHORT = "SHORT"


class Regime(StrEnum):
    """Market regime classification from Layer 3 Regime Detector."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE_LOW_VOL = "RANGE_LOW_VOL"
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"


class KillSwitchLevel(StrEnum):
    """Kill Switch escalation levels (ordered, only escalates upward automatically)."""

    NORMAL = "NORMAL"
    REDUCED_SIZE = "REDUCED"
    HALT_NEW_TRADES = "HALT"
    CLOSE_ALL = "CLOSE_ALL"
    EMERGENCY = "EMERGENCY"

    def __lt__(self, other: KillSwitchLevel) -> bool:  # type: ignore[override]
        if not isinstance(other, KillSwitchLevel):
            return NotImplemented
        members = list(KillSwitchLevel)
        return members.index(self) < members.index(other)


class AssessmentAction(StrEnum):
    """Risk Manager decision on a TradeIntent."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"


class CorrelationGroup(StrEnum):
    """Static correlation groups for exposure calculation (Rule 4)."""

    BTC_CLUSTER = "btc_cluster"
    ALT_L1 = "alt_l1"
    MEME = "meme"
    DEFI = "defi"


@dataclass(frozen=True)
class TradeIntent:
    """Trade intent received from the Strategy Engine via Redis ``intent:new``.

    Contains all information needed for pre-trade risk validation and position sizing.
    """

    symbol: str
    side: Side
    entry_price: float
    stop_loss: float
    size: float
    leverage: int
    regime: Regime
    capital: float
    total_balance: float
    used_margin: float

    id: UUID = field(default_factory=uuid4)
    take_profit: float | None = None
    correlation_group: CorrelationGroup | None = None

    @property
    def risk_per_unit(self) -> float:
        """Absolute risk per contract: |entry_price - stop_loss|."""
        return abs(self.entry_price - self.stop_loss)

    @property
    def notional(self) -> float:
        """Notional value of the position: size * entry_price."""
        return self.size * self.entry_price


@dataclass(frozen=True)
class ValidationResult:
    """Result of a single pre-trade rule check (Règles 1-6)."""

    approved: bool
    reason: str | None = None


@dataclass(frozen=True)
class RiskAssessment:
    """Final assessment output published to Redis.

    Channels: ``intent:approved`` / ``intent:rejected`` / ``intent:reduced``.
    """

    trade_intent_id: UUID
    action: AssessmentAction
    reason: str | None = None
    adjusted_size: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # noqa: UP017

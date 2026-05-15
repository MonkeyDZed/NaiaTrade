# NaiaTrade — Project Context for AI Agents

## Project Identity
| Field | Value |
|-------|-------|
| **Name** | NaiaTrade (Naia Group) |
| **Type** | Automated ICT trading bot for Binance Futures |
| **Language** | Python 3.11+ (frozen dataclasses, strict typing) |
| **Repo** | https://github.com/MonkeyDZed/NaiaTrade |
| **Current Phase** | **Phase 1: Risk Manager** (2 weeks) |

---

## Stack & Tooling
```yaml
runtime:
  python: "3.11+"
  typing: "strict (mypy), frozen dataclasses, no Any without justification"
  style: "ruff + black, 4-space indent, docstrings Google-style"

infrastructure:
  exchange: "Binance Futures via CCXT (async)"
  database: "Postgres 15 (state + journal)"
  cache: "Redis 7 (pub/sub + Kill Switch state)"
  deployment: "Docker Compose (dev local → VPS Tokyo/Singapour)"

testing:
  framework: "pytest + pytest-asyncio"
  coverage: "≥90% for core/risk/"
  adversarial: "REQUIRED before merge (see docs/03-risk-manager-spec.md)"

llm:
  provider: "DeepSeek V4 standard"
  frequency: "1 call/hour/asset (H+5min)"
  role: "interpretive context ONLY (20% of bias_composite)"
  fallback: "TTL 2h → defensive_mode (no new trades)"
```

---

## Quick-Start Commands (for Agents)
```bash
# Dev environment setup
cp .env.example .env && docker compose up -d postgres redis

# Run tests for a module
pytest tests/risk/test_manager.py -v --cov=core.risk

# Type check + lint
mypy core/risk/ && ruff check core/risk/ && ruff format core/risk/

# Run a single adversarial test
pytest tests/risk/test_adversarial.py::test_kelly_cap_overrides_ict_size -v

# Download test data (Phase 2 prep)
python scripts/download_historical.py --symbol BTCUSDT --timeframe 1H --months 1

# Start replay mode (Phase 2.5)
python scripts/replay.py --symbol BTCUSDT --timeframe 1H --start 2026-02-01 --end 2026-03-01 --mode detectors
```

---

## Active Task List (Phase 1)
```markdown
### core/risk/ — Priority Order
- [ ] `types.py` — Side, Regime, KillSwitchLevel enums (frozen, typed)
- [ ] `config_loader.py` — Load + validate config/risk.yaml (pydantic)
- [ ] `position_sizing.py` — risk_amount / distance + Kelly cap
- [ ] `kill_switch.py` — 5-level escalator + persistence (Postgres+Redis)
- [ ] `rules.py` — 6 pre-trade rules (max_risk, mandatory_sl, leverage, exposure, dd, margin)
- [ ] `binance_filters.py` — stepSize, minNotional, tickSize application
- [ ] `liquidation.py` — liq price calc + 2× buffer check
- [ ] `manager.py` — orchestrator: validate → assess → approve/reject

### tests/risk/ — Mirror structure
- [ ] `test_types.py`, `test_config_loader.py`, ..., `test_manager.py`
- [ ] `test_adversarial.py` — 10 required adversarial scenarios (see spec)
```

---

## Absolute Rules (Non-Negotiable)
| Rule | Rationale |
|------|-----------|
| **Never modify `docs/*.md` without a documented commit** | Specs are source of truth; changes require ADR |
| **Risk Manager logic = git commit + redeploy ONLY** | No runtime overrides (AD-010) |
| **Tests FIRST, code second** | Adversarial tests prevent silent failures |
| **Strict typing, frozen dataclasses** | Prevents accidental mutation in async pipeline |
| **LLM = context ONLY, never decision** | AD-005: LLM chuchote, ne prend pas le volant |
| **1 logical change = 1 commit** | Atomic, reviewable, revertible (not rigid "1 file = 1 commit") |
| **No `print()`, use `logging` with structured JSON** | Grafana/Telegram integration requires parseable logs |

---

## Architecture Layers (Data Flow)
```
Layer 0: Execution Engine (CCXT WebSocket/REST → Binance)
Layer 1: Risk Manager + Strategy Engine (validate + score + lifecycle)
Layer 2: ICT Detectors (Swing, FVG, Sweep, AMD, SMT, Judas, Silver Bullet, Turtle Soup)
Layer 3: Regime Detector (Trend, Volatility, Session, Liquidity → GlobalMarketState)
Layer 4: LLM Analyst + On-Chain Collector (DeepSeek V4, Glassnode, DefiLlama, Binance Delta)
```

**Key Flow**: `Bar Close → GlobalMarketState.update() → Detectors → Signal Pool → Strategy Engine → Risk Manager → Execution`

---

## Bias Composite Formula (Source: docs/07-on-chain-integration.md)
```python
bias_composite = (
    0.50 × structural_bias +   # trend_state 1H + external 4H
    0.20 × llm_macro_bias +    # DeepSeek V4 interpretive context
    0.15 × on_chain_bias +     # netflow + stablecoins + cumulative delta
    0.15 × funding_adjustment  # Binance Funding Rate extreme detection
)
# Clamped to [-1.0, +1.0]; confidence scaled by alignment
```

---

## Environment Variables (`.env` Reference)
```env
# Postgres
POSTGRES_USER=naia_dev
POSTGRES_PASSWORD=***
POSTGRES_DB=naiatrade
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_PASSWORD=***
REDIS_HOST=localhost
REDIS_PORT=6379

# Binance (Testnet first!)
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

# LLM
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# On-Chain (free tiers)
GLASSNODE_API_KEY=
DEFILLAMA_API_KEY=
```

---

## Testing Conventions
```python
# File naming: test_<module>.py in tests/risk/
# Function naming: test_<scenario> (descriptive, no abbreviations)

# Adversarial test pattern:
def test_flash_crash_triggers_close_all():
    # Simulate -5% DD in <1h
    # Assert KillSwitch → CLOSE_ALL
    # Assert all open positions closed via mock CCXT
    # Assert state persisted to Postgres

# Mocking:
# - Use pytest-mock for CCXT, Redis, Postgres
# - LLM: mock response JSON per docs/04-llm-prompt-spec.md
# - Time: use freezegun for deterministic lifecycle testing

# Coverage:
# - Branch coverage ≥90% for core/risk/
# - All adversarial scenarios must pass before merge
```

---

## Anti-Patterns (What NOT to Do)
| Anti-Pattern | Why It's Bad | Correct Approach |
|--------------|--------------|-----------------|
| `if llm_bias > 0.5: place_order()` | LLM must never decide trades | LLM → bias_composite → scoring → Risk Manager → order |
| Mutable global state | Race conditions in async pipeline | Use frozen dataclasses + explicit state updates |
| `print("debug")` | Breaks Grafana/Telegram parsing | `logging.info("msg", extra={"structured": "json"})` |
| Hardcoded API keys | Security risk | Load from `os.getenv()` + `.env` (gitignored) |
| Skipping adversarial tests | Silent failures in live | Write test FIRST, then code to pass it |
| Over-engineering Phase 1 | Scope creep | Stick to 6 rules + Kill Switch + Kelly; no "nice-to-haves" |

---

## Key Postgres Tables (Phase 1)
```sql
-- Risk Manager writes to:
risk_events (id, timestamp, rule_violated, trade_intent_id, action_taken)
capital_snapshots (id, timestamp, total_balance, used_margin, daily_dd, weekly_dd)
kill_switch_state (id, timestamp, level, reason, cooldown_until)

-- Strategy Engine reads/writes:
signals_log (id, timestamp, symbol, type, score, state, lifecycle_transitions)
bias_history (id, timestamp, symbol, bias_label, bias_score, confidence, source)
```

---

## Redis Channels (Pub/Sub)
```python
# Risk Manager subscribes to:
"intent:new"          # New TradeIntent from Strategy Engine
"kill_switch:changed" # Kill Switch level update (broadcast)

# Risk Manager publishes to:
"intent:approved"     # RiskAssessment = APPROVED
"intent:rejected"     # RiskAssessment = REJECTED + reason
"intent:reduced"      # RiskAssessment = REDUCED + new size
"kill_switch:changed" # When level escalates
```

---

## When in Doubt — Decision Tree
```
1. Is this about Risk Manager logic?
   → Read docs/03-risk-manager-spec.md FIRST

2. Is this about typing / data structure?
   → Check core/risk/types.py + mypy config

3. Is this about async / concurrency?
   → Use asyncio.Lock for shared state; avoid global mutable

4. Is this about LLM integration?
   → LLM output → post-processor → bias_composite ONLY (docs/04-llm-prompt-spec.md)

5. Is this about Binance API?
   → Use CCXT async wrapper; handle rate limits + retries (core/execution/)

6. Still unsure?
   → Add a TODO comment with link to relevant doc section
   → Ask human reviewer BEFORE merging
```

---

## Output Format Expectations (for Agent Responses)
When generating code, ALWAYS:
1. **Specify the file path** at the top of the code block:
   ```python
   # core/risk/manager.py
   class RiskManager:
       ...
   ```
2. **Include imports** needed for the snippet to run standalone
3. **Add type hints** and docstrings (Google style)
4. **Mention which test(s)** this code enables or modifies
5. **Flag any breaking changes** to existing interfaces

Example:
```markdown
✅ Good:
```python
# core/risk/rules.py
def check_mandatory_stop_loss(intent: TradeIntent, config: RiskConfig) -> ValidationResult:
    """Rule 2: Stop-loss must be defined and within [0.1%, 20%] of entry."""
    sl_distance = abs(intent.entry_price - intent.stop_loss) / intent.entry_price
    if not (0.001 <= sl_distance <= 0.20):
        return ValidationResult(rejected=True, reason="stop_loss_distance_invalid")
    return ValidationResult(approved=True)
```
*Enables test: `tests/risk/test_rules.py::test_mandatory_stop_loss_distance_check`*

❌ Bad:
```python
def check_sl(intent, cfg):
    d = abs(intent.entry - intent.sl) / intent.entry
    if d < 0.001 or d > 0.2: return False
    return True
```
*No file path, no types, no docstring, no test reference*
```

---

## Phase Transition Checklist (Phase 1 → Phase 2)
Before moving to Data Pipeline:
```markdown
- [ ] All 10 adversarial tests pass locally
- [ ] mypy + ruff clean on core/risk/
- [ ] Risk Manager can place/reject orders on Binance Testnet
- [ ] Kill Switch state persists across container restarts
- [ ] Logging structured JSON → Grafana compatible
- [ ] config/risk.yaml documented + validated by pydantic
- [ ] Human reviewer sign-off on Phase 1 deliverables
```

---

> **Agent Mantra**: *"Read the spec → Write the test → Implement minimal code → Validate adversarially → Commit atomically."*

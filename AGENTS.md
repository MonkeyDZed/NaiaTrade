# NaiaTrade — Project Context for AI Agents

## Project Identity
- **Name**: NaiaTrade (Naia Group)
- **Type**: Automated ICT trading bot for Binance Futures
- **Language**: Python 3.11+
- **Repo**: https://github.com/MonkeyDZed/NaiaTrade

## Stack
- Python 3.11+, frozen dataclasses, strict typing (mypy)
- CCXT for exchange API
- Postgres 15 for operational state + analytical journal
- Redis 7 for pub/sub messaging + state cache
- Docker Compose for deployment
- VectorBT + custom layer for backtesting
- DeepSeek V4 for LLM analysis (1 call/hour)
- Grafana + Telegram for monitoring

## Current Phase
**Phase 1: Risk Manager** (estimated 2 weeks)

## Active Task
- [ ] `core/risk/types.py` — Side, Regime, KillSwitchLevel enums
- [ ] `core/risk/config_loader.py` — Load config/risk.yaml
- [ ] `core/risk/position_sizing.py` — risk_amount / distance formula
- [ ] `core/risk/kill_switch.py` — 5-level escalator
- [ ] `core/risk/rules.py` — 6 rules (max_risk, mandatory_sl, leverage, exposure, dd, margin)
- [ ] `core/risk/binance_filters.py` — stepSize, minNotional, tickSize
- [ ] `core/risk/liquidation.py` — liq price + buffer check
- [ ] `core/risk/manager.py` — orchestrator: validate → assess → approve/reject

## Absolute Rules
- NEVER modify `docs/01-ict-specs-v1.3.md` without a documented commit
- Risk Manager modifications = git commit + redeployment ONLY
- 1 module = 1 file = 1 commit. No "WIP" commits.
- Tests FIRST (adversarial), code second. pytest + mypy + ruff before merge.
- Typing: strict, frozen dataclasses. No `Any` without justification.
- No trade decision from LLM. LLM = interpretive context only (20% of bias composite).

## Architecture
```
Layer 0: Execution Engine (CCXT + WebSocket → Binance)
Layer 1: Risk Manager (6 rules, Kill Switch, Kelly) + Strategy Engine (Scoring, Lifecycle)
Layer 2: ICT Detectors (Swing, FVG, Sweep, AMD, SMT, Judas, Silver Bullet, Turtle Soup)
Layer 3: Regime Detector (Trend, Volatility, Session, Liquidity)
Layer 4: LLM Analyst (DeepSeek V4) + On-Chain Collector (Glassnode, DefiLlama, Binance Delta)
```

## Bias Composite
```
0.50 structural (trend_state 1H + external 4H)
0.20 LLM macro (DeepSeek V4)
0.15 on-chain (netflow + stablecoins + delta)
0.15 funding (Binance Funding Rate)
```

## Key Config Files
| File | Purpose |
|------|---------|
| `config/ict_v1.3.yaml` | Lifecycle, Interactions, Scoring Grids, Market State |
| `config/sltp_standards.yaml` | SL/TP rules per setup, calibration, dynamic management |
| `config/risk.yaml` | Risk Manager parameters (to be created Phase 1) |

## Docs (source of truth)
| Doc | Content |
|-----|---------|
| `docs/01-ict-specs-v1.3.md` | ICT system specification |
| `docs/02-architecture-decisions.md` | 21 ADRs |
| `docs/03-risk-manager-spec.md` | Risk Manager specification |
| `docs/04-llm-prompt-spec.md` | LLM prompt specification |
| `docs/05-data-flow-architecture.md` | Data flow architecture |
| `docs/06-implementation-roadmap.md` | Implementation roadmap |
| `docs/07-on-chain-integration.md` | On-chain integration spec |
| `docs/08-replay-mode-spec.md` | Replay mode specification |
| `docs/09-sltp-optimization.md` | SL/TP optimization spec |

## Pending Decisions
None — all decisions are finalized in the docs.

## Next Phase (after Phase 1)
Phase 2: Data Pipeline + Backtester (download 3yr OHLCV, VectorBT wrapper, walk-forward)

# NaiaTrade

NaiaTrade est un moteur de trading ICT (Inner Circle Trader) probabiliste sur Binance Futures, multi-TF, avec supervision LLM + enrichissement on-chain, validé via replay mode avant paper trading, et protégé par un Risk Manager ultra-conservateur.
---

## Vue d'ensemble

NaiaTrade implémente une stratégie ICT multi-timeframe avec scoring probabiliste, signal lifecycle, et Risk Manager ultra-conservateur. Le système est conçu pour fonctionner de manière autonome avec une supervision LLM (DeepSeek V4) qui fournit un contexte interprétatif sans jamais prendre de décision de trade.

| Caractéristique | Valeur |
|-----------------|--------|
| **Stratégie** | ICT (Inner Circle Trader) multi-TF |
| **Timeframes** | 15m / 1H / 4H (N=5 fractal Williams) |
| **Actifs Phase 1** | BTC, ETH, SOL, BNB, DOT |
| **Exchange** | Binance Futures |
| **Risk/trade** | 0.25% (ultra-conservateur) |
| **Levier max** | 3x (TREND), 2x (RANGE), 1x (CRISIS) |
| **Marge** | Isolated |
| **LLM** | DeepSeek V4 (interprétatif uniquement) |
| **Stack** | Python 3.11+, Docker, Postgres, Redis, CCXT |

---

## Architecture Globale

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              BINANCE (EXTERNE)                                │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌─────────────┐                  │
│  │ OHLCV WS │  │aggTrades │  │ Orders    │  │ Funding Rate │                  │
│  │ 1s tick  │  │  WS      │  │ REST API  │  │ REST API     │                  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └──────┬──────┘                  │
└───────┼──────────────┼─────────────┼───────────────┼─────────────────────────┘
        │              │             │               │
┌───────┴──────────────┴─────────────┴───────────────┴─────────────────────────┐
│                         LAYER 0 : EXECUTION ENGINE                             │
│                                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐    │
│  │ Live Feeds   │  │ Historical   │  │     Order Manager                │    │
│  │ WS→Redis     │  │ Downloader   │  │  OCO (entry+SL+TP)               │    │
│  └──────┬───────┘  └──────┬───────┘  │  Reconciliation toutes les 5min  │    │
│         │                 │          └──────────────┬───────────────────┘    │
└─────────┼─────────────────┼─────────────────────────┼────────────────────────┘
          │                 │                         │
          ▼                 ▼                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        POSTGRES + REDIS                                       │
│  Postgres : ohlcv_*, positions, orders, signals_log, risk_events,             │
│             bias_history, on_chain_snapshots, on_chain_bias_history           │
│  Redis Pub/Sub : bar_close:*, signal:*, intent:*, kill_switch:*               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
│ LAYER 3         │  │ LAYER 2             │  │ LAYER 4              │
│ REGIME DETECTOR │  │ ICT DETECTORS       │  │ LLM ANALYST          │
│ • Trend state   │  │ • Swing (15m/1H/4H) │  │ • DeepSeek V4        │
│ • Volatility    │  │ • FVG               │  │ • 1 appel/h          │
│ • Session (KZ)  │  │ • Sweep             │  │ • Macro + On-Chain   │
│ • Liquidity     │  │ • AMD               │  │ • Phrase factuelle   │
│                 │  │ • SMT Intra/Cross   │  │                      │
└────────┬────────┘  │ • Judas Swing       │  └──────────┬───────────┘
         │           │ • Silver Bullet     │             │
         │           │ • Turtle Soup       │             │
         │           │ • Displacement+OTE  │             │
         │           │ • BOS/CHoCH         │             │
         │           └──────────┬──────────┘             │
         └──────────────────────┼────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       LAYER 1 : STRATEGY ENGINE                               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                    SIGNAL POOL (in-memory + Redis)                    │    │
│  │   DETECTED → ACTIVE → REINFORCED → DECAYING → INVALIDATED            │    │
│  │   Scoring par setup (6 grilles)  │  Decay exponentiel                 │    │
│  │   Interactions (sweep+FVG...)    │  Seuils 45/60/80                   │    │
│  └──────────────────────────────────┬───────────────────────────────────┘    │
│                                     │                                         │
│                    BIAS COMPOSITE = 0.50 structural                           │
│                                   + 0.20 LLM macro                           │
│                                   + 0.15 on-chain                             │
│                                   + 0.15 funding                             │
│                                     │                                         │
│                           TradeIntent                                         │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1 : RISK MANAGER                                │
│                                                                               │
│  R1: Max risk 0.25% │ R2: Stop-loss OCO │ R3: Levier dynamique par régime    │
│  R4: Exposition max │ R5: Drawdown escalier │ R6: Margin ratio               │
│                                                                               │
│  KILL SWITCH : NORMAL → REDUCED → HALT → CLOSE_ALL → EMERGENCY               │
│  KELLY CAP : min(ICT_size, kelly_cap) — Recalcul tous les 50 trades          │
│                                                                               │
│                   APPROVED / REJECTED / REDUCED                                │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION ENGINE                                       │
│                     Ordre OCO → Binance Futures API                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline décisionnel (1 trade)

```
  BAR CLOSE (15m / 1H / 4H)
         │
         ├─► Regime Detector ──► Trend state + Volatility + Session + Liquidity
         │                              │
         │                       GLOBAL MARKET STATE
         │                              │
         ├─► ICT Detectors ─────────────┤
         │   • Swing (N=5 anti-repaint) │
         │   • FVG (≥0.15×ATR)         │
         │   • Sweep (anchored_to)      │
         │   • AMD (probabiliste)       │
         │   • SMT (delta + cross)      │
         │   • Judas / Silver Bullet     │
         │   • Displacement + OTE       │
         │                              │
         └─► SIGNAL POOL ◄──────────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
    Lifecycle Engine    Scoring Engine
    (5 états)            (6 grilles)
         │                     │
         └──────────┬──────────┘
                    │
              Score ≥ 45 ?
                    │
              ┌─────┴─────┐
              │ YES       │ NO → Skip
              ▼
         BIAS COMPOSITE
         50% structural (trend_state)
         20% LLM macro  (DeepSeek V4, 1h)
         15% on-chain   (Netflow + Stablecoins + Delta)
         15% funding    (Binance Funding Rate)
              │
              ▼
         TradeIntent {symbol, side, entry, stop, tp, score, tier, size}
              │
              ▼
         RISK MANAGER
         ├─ R1: risk ≤ 0.25% capital ?
         ├─ R2: stop-loss défini + valide ?
         ├─ R3: levier ≤ max_by_regime ?
         ├─ R4: exposition totale ≤ 200% ?
         ├─ R5: drawdown check escalier ?
         ├─ R6: margin_ratio ≤ warning ?
         └─ Kelly cap : min(ICT, kelly)
              │
         ┌────┴────┐
         │ APPROVED │ REJECTED / REDUCED
         └────┬────┘
              ▼
         EXECUTION ENGINE
         ├─ OCO (entry + stop-loss + take-profit)
         ├─ Filtres Binance (stepSize, minNotional)
         └─ Ordre placé sur Binance
              │
              ▼
         MONITORING (Grafana + Telegram)
```

---

## Signal Lifecycle (5 états)

```
  Bar 1    Bar 2    Bar 3    Bar 4    Bar 5    Bar 6    Bar 7    Bar 8    Bar 9
    │        │        │        │        │        │        │        │        │
    ▼        │        │        │        │        │        │        │        │
 DETECTED ──┘        │        │        │        │        │        │        │
 Score=40            │        │        │        │        │        │        │
                     ▼        │        │        │        │        │        │
                  ACTIVE ─────┘        │        │        │        │        │
                  Score=55             │        │        │        │        │
                  (≥45 → tradable)     ▼        │        │        │        │
                               REINFORCED ─────┘        │        │        │
                               Score=75  (+15 sweep+FVG)│        │        │
                               Decay reset              │        │        │
                                                        ▼        │        │
                                                    DECAYING ───┘        │
                                                    Score=48             │
                                                    (score baisse)       ▼
                                                                    INVALIDATED
                                                                    Score=38 (<40)
                                                                     OU FVG consumé
```

---

## Scoring par setup (6 grilles)

| Setup | Poids clés | Max | Minimal | Standard | Premium |
|-------|-----------|-----|---------|----------|---------|
| Liquidity Sweep | ext:35 bias:20 KZ:10 FVG:10 SMT:10 | 100 | 45 | 60 | 80 |
| Silver Bullet | FVG:30 bias:25 zone:20 judas:15 SMT:10 | 100 | - | 50 | 70 |
| AMD Distribution | amd:40 bias:25 sweep:20 FVG:15 | 100 | - | 55 | 75 |
| Turtle Soup | ext:35 bias:20 KZ:15 FVG:15 | 100 | - | 55 | 75 |
| Judas Swing | judas:35 bias:25 amd:20 FVG:20 | 100 | - | 55 | 80 |
| SMT Cross-Asset | smt:35 setup:30 bias:20 KZ:15 | 100 | - | 50 | 70 |

**Tiers** : MINIMAL (45-59) ×0.5 | STANDARD (60-79) ×1.0 | PREMIUM (80+) ×1.25-1.80

---

## Composite Bias

```
bias_composite = 0.50 × structural_bias (ICT trend state 1H + 4H)
               + 0.20 × LLM_macro_bias (DeepSeek V4 - contexte interprétatif)
               + 0.15 × on_chain_bias  (Netflow + Stablecoins + Delta)
               + 0.15 × funding_adjustment (Binance Funding Rate)
```

| Divergence | Comportement |
|------------|-------------|
| Tous alignés | confidence ×1.0 |
| On-Chain seul | confidence ×0.6, half size |
| On-Chain vs Structural | confidence ×0.7, prefer structural |
| On-Chain + LLM vs Structural | confidence ×0.5, skip recommandé |
| On-Chain fallback | poids redistribué |

---

## Risk Manager — Kill Switch

| Niveau | Seuil | Action | Cooldown |
|--------|-------|--------|----------|
| NORMAL | - | Fonctionnement standard | - |
| REDUCED_SIZE | Daily -2% | Taille ÷ 2 | - |
| HALT_NEW_TRADES | Daily -3% | Pas de nouvelle entrée | 4h |
| CLOSE_ALL | Daily -5% | Tout fermer | 24h |
| EMERGENCY | Weekly -8% | Arrêt total | Manuel |

**6 règles** : Max risk 0.25% | Stop-loss OCO obligatoire | Levier par régime | Exposition max 200% | Drawdown escalier | Margin ratio

---

## Kill Zones (UTC — calibrées données réelles crypto)

```
UTC  00  01  02  03  04  05  06  07  08  09  10  11  12  13  14  15  16  17  18  19  20  21  22  23
     │████ ASIAN ████│   │████ LONDON █████│   │████ NY AM ██████│   │█ NY PM █│   │
     │ MODERATE ×0.7  │   │ STRONG ×1.0     │   │VERY_STRONG ×1.15 │   │WEAK ×0.5│   │
     │                │   │ Judas 07-08:30  │   │Judas 13-14:30    │   │          │   │
     │                │   │                 │   │Silver Bullet     │   │          │   │
     │                │   │                 │   │  15:00-16:00     │   │          │   │
```

**Key Times (bonus scoring)** : 11:00 (+15%) · 13:00 (+15%) · 15:00 (+15%) · 16:00 (+10%) · 20:00 (+10%)

**Weekend** : 2× confluence requise, taille -30%, skip funding extrême

---

## Données On-Chain → Bias

```
Glassnode ──► Netflow 24h (BTC, ETH, SOL, BNB, DOT)
DefiLlama ──► Stablecoin Supply (USDT + USDC séparés)
Binance   ──► Cumulative Delta (aggTrades)
     │
     ▼
┌──────────────┐
│ JSON structuré │ → LLM → Phrase factuelle
└──────────────┘         "Netflow -3200 BTC, USDT +800M, delta bullish"
                                    │
                                    ▼
┌──────────────────────────────────────────────┐
│       POST-PROCESSOR (déterministe)           │
│  "netflow negative"     → +0.10              │
│  "USDT increased"       → +0.05              │
│  "delta bullish"        → +0.05              │
│  TOTAL                  → +0.15 (capped)     │
└──────────────────────────────────────────────┘
                       │
                 on_chain_bias → 15% du composite
```

---

## Docker Containers

```
docker-compose.yml
├── postgres:15         # Base de données
├── redis:7             # Cache + messaging
├── data_collector      # WebSocket + REST → Postgres/Redis
├── regime_detector     # Détection régime → Redis
├── ict_detector        # Swings, FVG, Sweeps, AMD, SMT → Signal Pool
├── llm_analyst         # DeepSeek V4 → bias_history
├── strategy_engine     # Scoring + Decay + TradeIntent → Redis
├── risk_manager        # 6 règles + Kelly + Kill Switch
├── execution_engine    # CCXT → Binance
├── monitor             # Alertes Telegram
└── grafana             # Dashboards
```

---

## Phases et Timeline

```
Semaine  1  2  3  4  5  6  7  8  9 10 11     ...     60j     3-6 mois
         ├──┼──┼──┼──┼──┼──┼──┼──┼──┼──┤              ├───────┼─────────
Phase 1  ██░░░░░░░░░░░░░░░░░░░░░░░░  Risk Manager
Phase 2  ░░████░░░░░░░░░░░░░░░░░░░░  Data Pipeline + Backtester
Ph 2.5   ░░░░██░░░░░░░░░░░░░░░░░░░░  Replay Mode (1-2j)
Phase 3  ░░░░░░████░░░░░░░░░░░░░░░░  ICT Detectors
Phase 4  ░░░░░░░░░░████░░░░░░░░░░░░  Strategy Engine
Phase 5  ░░░░░░░░░░░░░░██░░░░░░░░░░  LLM Analyst (macro)
Ph 5.5   ░░░░░░░░░░░░░░░░██░░░░░░░░  On-Chain Pipeline
Phase 6  ░░░░░░░░░░░░░░░░░░████░░░░  Intégration + Tests E2E
Phase 7  ░░░░░░░░░░░░░░░░░░░░░░████  Paper Trading (60j min)
Phase 8  ░░░░░░░░░░░░░░░░░░░░░░░░░░  Capital Réel (3-6 mois)
```

---

## Dépendances

```
Phase 1 (Risk Manager)
     │
┌────┴────┐
▼         ▼
Phase 2   Phase 2.5 (Replay Mode)
(Data)       │
     │       │
     └───┬───┘
         ▼
Phase 3 (ICT Detectors)
         │
    ┌────┴────┐
    ▼         ▼
Phase 4    Phase 5 (LLM Macro)
(Strategy)     │
    │          ▼
    │    Phase 5.5 (On-Chain)
    │          │
    └────┬─────┘
         ▼
Phase 6 (Intégration E2E)
         │
         ▼
Phase 7 (Paper 60j)
         │
         ▼
Phase 8 (Live Réel)
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Langage | Python 3.11+ |
| Typage | Strict (frozen dataclasses) |
| Base de données | Postgres 15 |
| Cache / Messaging | Redis 7 |
| Exchange API | CCXT |
| Backtester | VectorBT + custom layer |
| LLM | DeepSeek V4 |
| Monitoring | Grafana + Telegram |
| Déploiement | Docker Compose |
| OS Dev | WSL2 Ubuntu |
| VPS | Tokyo / Singapour (5-15ms → Binance) |

---

## Documentation

| Document | Contenu |
|----------|---------|
| [`docs/00-discussion-log.md`](docs/00-discussion-log.md) | Journal de discussion et décisions |
| [`docs/01-ict-specs-v1.3.md`](docs/01-ict-specs-v1.3.md) | Spécification ICT v1.3 — source unique de vérité |
| [`docs/02-architecture-decisions.md`](docs/02-architecture-decisions.md) | 21 ADRs (Architecture Decision Records) |
| [`docs/03-risk-manager-spec.md`](docs/03-risk-manager-spec.md) | Risk Manager — 6 règles, Kill Switch, Kelly |
| [`docs/04-llm-prompt-spec.md`](docs/04-llm-prompt-spec.md) | LLM Analyst — DeepSeek V4, prompts, erreurs |
| [`docs/05-data-flow-architecture.md`](docs/05-data-flow-architecture.md) | Data flow complet — WS → Redis → Trade |
| [`docs/06-implementation-roadmap.md`](docs/06-implementation-roadmap.md) | Roadmap 8 phases, dépendances, risques |
| [`docs/07-on-chain-integration.md`](docs/07-on-chain-integration.md) | On-Chain — Netflow, Stablecoins, Delta, Post-Processor |
| [`docs/08-replay-mode-spec.md`](docs/08-replay-mode-spec.md) | Replay Mode — bar-par-bar, 5 modes, Plotly |

---

## Critères de validation

| Métrique | Seuil |
|----------|-------|
| Sharpe ratio OOS | > 1.5 |
| Max drawdown | < 15% |
| Profit factor | > 1.5 |
| Win rate | 56-58% |
| Trades/mois | 15-25 |
| Paper trading | 60 jours minimum |
| Sharpe live vs backtest | ≥ 70% |

---

## Licence

Projet privé — Naia Group.

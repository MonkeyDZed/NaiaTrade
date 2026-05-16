# Data Flow Architecture — NaiaTrade

> Flux de données complet, de la bougie brute jusqu'à l'ordre Binance.

---

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────┐
│                    BINANCE (EXTERNE)                                 │
│                                                                      │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────────┐ │
│  │ WebSocket    │  │ REST API      │  │ REST API                  │ │
│  │ OHLCV 1s     │  │ OHLCV hist    │  │ Orders + Account          │ │
│  │ depth L2     │  │ aggTrades     │  │ Funding Rate              │ │
│  │ aggTrade     │  │ Funding hist  │  │ Open Interest             │ │
│  └──────┬───────┘  └───────┬───────┘  └───────────┬───────────────┘ │
└─────────┼──────────────────┼──────────────────────┼─────────────────┘
          │                  │                      │
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE (core/data/)                       │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │ Live Feeds  │  │ Historical   │  │ Account State             │  │
│  │ (WS→Redis)  │  │ Downloader   │  │ (REST→Postgres)           │  │
│  │ - OHLCV 15m │  │ - 3yr OHLCV  │  │ - positions               │  │
│  │ - OHLCV 1H  │  │ - aggTrades  │  │ - orders                  │  │
│  │ - OHLCV 4H  │  │ - Funding    │  │ - balances                │  │
│  │ - depth L2  │  │   history    │  │                           │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬───────────────┘  │
└─────────┼────────────────┼──────────────────────┼──────────────────┘
          │                │                      │
          ▼                ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    POSTGRES (source de vérité)                      │
│                                                                     │
│  Tables: ohlcv_15m, ohlcv_1h, ohlcv_4h, funding_rates,             │
│          positions, orders, capital_snapshots,                      │
│          signals_log, risk_events, bias_history, regime_history     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    REDIS (messaging temps réel)                     │
│                                                                     │
│  Channels:                                                          │
│  - bar_close:15m, bar_close:1h, bar_close:4h                       │
│  - signal:new, signal:decayed, signal:invalidated                   │
│  - intent:new, intent:approved, intent:rejected                     │
│  - order:placed, order:filled, order:cancelled                      │
│  - kill_switch:changed                                              │
│  - regime:changed                                                   │
│                                                                     │
│  State Keys: kill_switch:state, market:state                        │
└─────────────────────────────────────────────────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
│ REGIME DETECTOR │  │ ICT DETECTORS   │  │ LLM ANALYST          │
│ (sur bar_close) │  │ (sur bar_close) │  │ (toutes les heures)  │
│                 │  │                 │  │                      │
│ Input:          │  │ Input:          │  │ Input:               │
│ - OHLCV 1H/4H  │  │ - OHLCV 15m/1H  │  │ - Snapshot marché    │
│ - Funding 24h   │  │ - OHLCV 4H      │  │ - ICT structure      │
│ - Volume        │  │ Output:         │  │ - News / On-chain    │
│                 │  │ - Swings        │  │                      │
│ Output:         │  │ - FVGs          │  │ Output:              │
│ - regime_label  │  │ - Sweeps        │  │ - bias par actif     │
│ - volatility_   │  │ - AMD probs     │  │ - zones d'intérêt    │
│   state         │  │ - SMT signals   │  │ - momentum score     │
└────────┬────────┘  └────────┬────────┘  └──────────┬───────────┘
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GLOBAL MARKET STATE                               │
│                                                                     │
│  État unifié lu par tous les modules.                               │
│  Mis à jour on_each_bar_close (1H).                                 │
│  Components: trend, session, volatility, liquidity                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STRATEGY ENGINE                                   │
│                                                                     │
│  1. Lit Global Market State                                         │
│  2. Lit signaux ACTIVE + REINFORCED (depuis Signal Pool)            │
│  3. Calcule bias_composite (weights in config/bias.yaml — AD-022)   │
│  4. Applique Signal Scoring (grille par setup type)                 │
│  5. Applique Decay + Interactions                                   │
│  6. Si score >= minimal_threshold → génère TradeIntent              │
│                                                                     │
│  Signal Pool (en mémoire + Redis):                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ ID │ Type  │ Layer │ Score │ State     │ Bars │ Price │ Int │   │
│  │ s1 │ sweep │ ext   │ 65    │ ACTIVE    │ 2    │ 66200 │ -   │   │
│  │ s2 │ fvg   │ short │ 40    │ DECAYING  │ 5    │ 67200 │ s1  │   │
│  │ s3 │ smt   │ cross │ 30    │ INVALID   │ 8    │ 66800 │ -   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ TradeIntent
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RISK MANAGER (core/risk/)                        │
│                                                                     │
│  1. Lit KillSwitch state                                            │
│  2. Vérifie 6 règles pré-trade                                      │
│  3. Calcule position size + Kelly cap                               │
│  4. Applique filtres Binance (stepSize, minNotional...)             │
│  5. Vérifie distance liquidation                                    │
│  6. Génère RiskAssessment → APPROVED / REJECTED / REDUCED            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ RiskAssessment (si APPROVED)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EXECUTION ENGINE (core/execution/)               │
│                                                                     │
│  1. Transforme RiskAssessment → ordre CCXT                           │
│  2. Place OCO (entry + stop-loss + take-profit)                     │
│  3. Gère retries + rate limiting                                    │
│  4. Reconciliation périodique état local vs Binance                 │
│  5. Écrit ordres et positions dans Postgres                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Binance Futures API (testnet → paper → live)                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MONITORING (Grafana + Telegram)                  │
│                                                                     │
│  - P&L cumulé en temps réel                                        │
│  - Drawdown courant vs seuils                                       │
│  - Positions ouvertes avec P&L                                      │
│  - Derniers signaux et trades                                       │
│  - Alertes: DD seuil, Kill Switch, erreur API, divergence état     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Cadences

| Composant | Fréquence | Déclencheur |
|---|---|---|
| WebSocket OHLCV | Continu | Nouveau tick |
| Bar close (15m, 1H, 4H) | À chaque clôture | Bougie fermée |
| ICT Detectors | Sur bar_close 15m et 1H | Redis pub bar_close:* |
| LLM Analyst | Toutes les heures (H+5min) | Cron / scheduler |
| Strategy Engine | Sur nouveau signal + bar_close | Redis pub signal:new |
| Risk Manager | Sur TradeIntent reçu | Redis pub intent:new |
| Execution Engine | Sur RiskAssessment APPROVED | Redis pub intent:approved |
| Reconciliation | Toutes les 5 minutes | Cron / scheduler |
| Monitoring refresh | Toutes les 10 secondes | Grafana polling |

---

## Containers Docker

```
docker-compose.yml
├── postgres:15         # Base de données
├── redis:7             # Cache + messaging
├── data_collector      # WebSocket + REST → Postgres/Redis
├── regime_detector     # Détection régime → Redis
├── ict_detector        # Swings, FVG, Sweeps, AMD, SMT → Redis/Signal Pool
├── llm_analyst         # DeepSeek V4 → bias_history
├── strategy_engine     # Scoring + Decay + TradeIntent → Redis
├── risk_manager        # 6 règles + Kelly + Kill Switch
├── execution_engine    # CCXT → Binance
├── monitor             # Alertes Telegram
└── grafana             # Dashboards
```

---

## Signal Pool (in-memory + Redis backup)

Structure de données centrale pour le cycle de vie des signaux :

```python
@dataclass
class SignalInstance:
    id: str
    symbol: str
    type: SignalType         # SWEEP, FVG, SMT, AMD, SILVER_BULLET, JUDAS, TURTLE_SOUP
    layer: Layer              # MICRO, SHORT_TERM, EXTERNAL (pour sweeps)
    price_level: Decimal
    detection_bar_time: datetime
    bars_since_detection: int
    base_score: float
    current_score: float
    state: LifecycleState     # DETECTED, ACTIVE, REINFORCED, DECAYING, INVALIDATED
    linked_signals: list[str] # IDs des signaux liés (interactions)
    features: dict            # Métadonnées spécifiques au type de signal
```

---

## External APIs (données alternatives)

| Source | Données | Fréquence | Gratuit ? |
|---|---|---|---|
| alternative.me | Fear & Greed Index | 1h | Oui |
| CoinGecko | BTC Dominance | 1h | Oui (10-50 calls/min) |
| Glassnode | Exchange Netflow | 4h | Oui (free tier) |
| DefiLlama | Stablecoin Supply | 4h | Oui |
| CoinDesk RSS | News titres | 1h | Oui |
| LunarCrush | Social Volume | 1h | Oui (free tier) |

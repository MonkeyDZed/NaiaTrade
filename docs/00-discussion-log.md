# NaiaTrade - Journal de discussion et décisions

## Chronologie de la conception du système

---

### Phase 1 : Cadrage du projet (Claude)

- **Contexte initial** : Bot trading auto sur Binance, futures avec levier, spot aussi
- **Objectif** : Revenu complémentaire, capital 5000-10000 USDT cible, 200-500 USDT en phase test
- **Profil utilisateur** : Code + expérience trading. Trade manuel en ICT (Inner Circle Trader) sur 1m/5m/15m
- **Décision stack** : WSL2 Ubuntu, Docker, Postgres, Redis, Python, CCXT
- **Décision timeframe** : 15m et 1H (pas de scalping sub-minute)
- **Décision marge** : Isolated margin pour commencer
- **Décision risque** : Ultra-conservateur (0.25% risk/trade, levier max 3x) en phase validation

### Phase 2 : Architecture (Claude + OpenCode)

- **Architecture retenue** : 5 couches séparées en containers Docker
  - Layer 0 : Execution Engine (CCXT + WebSocket)
  - Layer 1 : Risk Manager (cœur du système, 6 règles)
  - Layer 2 : Strategy Engine (ICT signal generation)
  - Layer 3 : Regime Detector (déterministe, Python pur)
  - Layer 4 : LLM Analyst (supervision, contexte macro)
- **Communication** : Redis pub/sub + streams entre couches
- **Stockage** : Postgres pour état opérationnel + journal analytique
- **Monitoring** : Grafana + alertes Telegram

### Phase 3 : Formalisation ICT

#### v1.0 (single-TF)
- Layers N=3, N=5, N=9 sur le même timeframe
- Liquidity tagging par nesting (N=9 implique N=5 et N=3)
- 6 règles de Risk Management, Kill Switch avec hiérarchie

#### v1.1 (multi-TF)
- **Décision** : Passage multi-timeframe : 15m/N=5, 1H/N=5, 4H/N=5
- N=5 uniforme (standard ICT fractal Williams)
- Liquidity tagging refondu en `sweep_anchored_to`
- Ajout BOS/CHoCH avec machine d'état de tendance (UNDEFINED/UPTREND/DOWNTREND)
- Ajout swing freshness (staleness) avec max_age_bars
- Zones trading range half-open
- FVG_in_OTE : overlap / min(size1, size2) >= 0.5
- Pending swings exposés au LLM en read-only, interdits au Strategy Engine
- Defensive mode sur expiry LLM
- Trend state UNDEFINED bloque les trades directionnels

#### v1.2 (P0 additions)
- **AMD** : Cycle Accumulation-Manipulation-Distribution complet
- **SMT Divergence Intra-Asset** : Delta divergence (aggTrades) + volume divergence (fallback)
- **SMT Divergence Cross-Asset** : BTC vs ETH/SOL/BNB/DOT avec corrélation
- **Judas Swing** : Sweep en ouverture de Kill Zone (London et NY)
- **Silver Bullet** : Setup temporel 15:00-16:00 UTC (10:00-11:00 AM NY)
- **Kelly Fractional Sizing** : Cap dynamique sur taille, auto-disable setups négatifs
- **Funding Rate enrichi** : 3e source du bias composite
- **Bias composite** : 0.50 structural + 0.35 LLM + 0.15 funding
- **Key Times** : Horaires à probabilité élevée (pre-market, NYSE open/close, daily reset)

#### Corrections Kill Zones (données réelles crypto)
- **Timezone** : UTC (pas Africa/Algiers), conversion locale uniquement pour affichage
- **London** : 07:00-10:00 UTC (validité STRONG)
- **NY AM** : 13:00-16:00 UTC (validité VERY_STRONG, priorité HIGHEST, taille ×1.15)
- **NY PM** : 19:00-21:00 UTC (validité WEAK, désactivée sauf confluence forte ×0.5)
- **Asian** : 01:00-04:00 UTC (validité MODERATE, taille ×0.7)
- **Silver Bullet** : 15:00-16:00 UTC (corrigé, était décalé)
- **Judas Swing** : 07:00-08:30 et 13:00-14:30 UTC (tolérance 90 min)
- **Weekend mode** : 2× confluence, taille -30%, skip funding extrême
- **Volume filter** : volume_24h >= median_7j × 0.7
- **Sweep tolerance** : 90 min (crypto 24/7)

#### v1.3 (Scoring + Lifecycle)
- **Décision** : AND-stacking abandonné → scoring pondéré continu
- **Objectif** : Expectancy max (plus de trades, edge stable, 15-25 trades/mois)
- **Signal Lifecycle Engine** : 5 états (DETECTED → ACTIVE → REINFORCED → DECAYING → INVALIDATED)
- **Signal Interactions** : Réactivation sweep+FVG (+15pts), SMT+sweep (decay ×0.5), AMD+bias (lifetime ×2)
- **Scoring Grids** : Par type de setup (sweep, silver bullet, AMD, turtle soup, judas, SMT)
- **Seuils calibrés** : Minimal 45, Standard 60, Premium 80 (expectancy max)
- **Signal Decay** : Formule exponentielle, taux par type, invalidation à 40
- **Global Market State** : État unifié lu par tous les détecteurs
- **SMT Correlation** : Rolling Pearson 7j + filtre stabilité (min 0.5 corr, 0.6 stability)
- **LLM intégré au scoring** : Via bias_aligned_composite (50/35/15)
- **Kelly cap** : Confirmé comme hiérarchie (Kelly = upper bound, ICT = allocation d'alpha)

### Phase 4 : Décisions transversales

- **LLM** : DeepSeek V4 standard. Contexte interprétatif UNIQUEMENT (pas de décision de trade). Maj toutes les heures. Fallback 2h puis defensive mode.
- **Données** : Sources gratuites uniquement (CoinGecko, alternative.me, RSS feeds, Binance API)
- **Contrôle humain** : Total en phase backtest/paper. À durcir en live réel (commit freeze, pas d'override sans justification)
- **Anti-impulsivité** : Kill switches en code dur, modifiables uniquement par commit git
- **Paper trading** : 60 jours minimum sur Binance Futures Testnet avant capital réel
- **Critères validation** : Sharpe OOS > 1.5, DD < 15%, profit factor > 1.5
- **Capital test réel** : 200-500 USDT en phase C (après paper trading validé)

### Phase 5 : Stack technique confirmé

- **OS Dev** : WSL2 Ubuntu
- **Déploiement** : Docker Compose sur VPS Tokyo/Singapour (latence 5-15ms)
- **Base de données** : Postgres (état + journal), Redis (messaging temps réel)
- **Backtester** : VectorBT + custom avec slippage/frais/funding modélisés
- **Données** : CCXT, Parquet + Postgres, 3 ans d'historique minimum
- **Monitoring** : Grafana + alertes Telegram
- **Langage** : Python 3.11+, frozen dataclasses, typage strict

---

## Projet NaiaTrade

- **Nom** : NaiaTrade (partie de "Naia Group")
- **Actifs** : BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, DOT/USDT (phase 1)
- **Extension future** : XLM, XAUT, NEAR, ALGO, ATOM, KASPA, MATIC (phase 2+)

---

## Références
- ICT Concepts source : Inner Circle Trader methodology (Michael Huddleston)
- Multi-layer swings : Concept proposé par l'utilisateur (N=3/5/9 → 15m/1H/4H N=5)
- Kill Zones crypto data : Analyse orderbook Binance BTC/FDUSD (50,526 minutes)
- Expert reviews : Deux analyses externes intégrées dans les décisions v1.3

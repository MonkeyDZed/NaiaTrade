# Implementation Roadmap — NaiaTrade

> Plan d'implémentation phase par phase, avec dépendances et livrables.

---

## Vue d'ensemble

```
Phase 1 : Risk Manager ──────────────────┐
Phase 2 : Data Pipeline + Backtester ────┤
Phase 2.5 : Replay Mode ─────────────────┤
Phase 3 : ICT Detectors ─────────────────┤ Séquence
Phase 4 : Strategy Engine ───────────────┤ critique
Phase 5 : LLM Analyst + On-Chain ────────┤ (ordre
Phase 6 : Intégration + Tests ───────────┤ imposé)
Phase 7 : Paper Trading (60 jours) ──────┘
Phase 8 : Capital réel (3-6 mois)
```

---

## Phase 1 : Risk Manager (semaines 1-2)

**Dépendances** : Aucune (module indépendant)
**Objectif** : Module Risk Manager complet, testé unitairement

### Livrables

| Module | Fichier(s) | Tests |
|---|---|---|
| Types | `core/risk/types.py` | Validation post_init |
| Position Sizing | `core/risk/position_sizing.py` | 5 tests (normal, réduit, zéro, cap Kelly, filtres Binance) |
| Kill Switch | `core/risk/kill_switch.py` | 6 tests (escalade, cooldown, EMERGENCY reset, persistence, size_multiplier, requires_closure) |
| 6 Règles | `core/risk/rules.py` | 6 tests minimum (une par règle) |
| Risk Manager | `core/risk/manager.py` | 4 tests E2E |
| Binance Filters | `core/risk/binance_filters.py` | 3 tests (stepSize, minNotional, tickSize) |
| Liquidation Calc | `core/risk/liquidation.py` | 3 tests (LONG, SHORT, distance check) |
| Config Loader | `core/risk/config_loader.py` | 2 tests (YAML, env override) |

### Tests adversariaux requis

```
test_three_losses_trigger_reduced_size
test_flash_crash_triggers_close_all
test_kill_switch_survives_restart
test_correlated_positions_consolidated_exposure
test_order_without_stop_loss_rejected
test_leverage_dynamic_by_regime
test_margin_ratio_force_reduce
test_kelly_cap_overrides_ict_size
test_binance_filters_reject_invalid_orders
test_state_divergence_triggers_emergency
```

### Sortie Phase 1
Tu peux placer un ordre sur Binance testnet via ton code.
Le Risk Manager le valide ou le refuse selon les 6 règles + Kelly cap.
L'état est persisté en Postgres.

---

## Phase 2 : Data Pipeline + Backtester (semaines 3-4)

**Dépendances** : Phase 1 (Postgres structure)
**Objectif** : Backtester complet avec slippage, frais, funding modélisés

### Livrables

| Module | Description |
|---|---|
| Historical Downloader | 3 ans 15m/1H/4H BTC,ETH,SOL,BNB,DOT |
| Funding Rate History | 2 ans minimum, toutes les 8h |
| aggTrades History | Pour delta divergence (si besoin pour phase 1 backtest) |
| Parquet Storage | Fichiers compressés + métadonnées Postgres |
| Backtester Engine | VectorBT wrapper + custom layer |
| Walk-Forward Module | Fenêtre glissante 6 mois train / 2 mois test |
| Metrics Module | Sharpe, Sortino, Calmar, max DD, profit factor, expectancy |
| Reports Generator | HTML/Markdown avec graphiques |

### Modélisation obligatoire

- Frais maker (0.02%) vs taker (0.05%) selon type d'ordre
- Slippage modélisé (0.01-0.05% selon liquidité de l'actif)
- Funding rate historique appliqué toutes les 8h
- Délai 1 bougie entre signal et exécution
- Délai de confirmation swing (w=2 closes) avant utilisation du swing (AD-027)
- minNotional / stepSize Binance
- **Politique backtest** : VectorBT pour pré-screening de paramètres uniquement. Le replay stateful (Phase 2.5) est la seule vérité go/no-go (AD-027).

### Sortie Phase 2
Une stratégie minimale (MA crossover) peut être backtestée sur 2 ans.
Rapport complet avec toutes les métriques.

---

## Phase 2.5 : Replay Mode (1-2 jours)

**Dépendances** : Phase 2 (Data Pipeline)
**Objectif** : Validation visuelle + debug des détecteurs ICT sans attendre le temps réel

### Livrables

| Module | Description |
|---|---|
| Replay Engine | Boucle bar-par-bar, 5 modes (detectors, full, compare, what-if, multi-TF) |
| Historical Loader | Chargement Parquet/Postgres/CCXT, compatible format live |
| Plotly Renderer | Swings, FVG, Kill Zones, trades tracés en temps simulé |
| Logger + Report | CSV signaux + trades, rapport JSON automatique |
| Golden Dataset | Jeu de référence pour tests de non-régression |
| On-Chain Injection | Snapshots on-chain historiques injectables dans le replay |

### Modes de replay

```
detectors   : Signaux bruts uniquement (debug visuel)
full        : Pipeline complet jusqu'au TradeIntent fictif
compare     : A/B test de deux configurations côte à côte
what-if     : Test de paramètres isolés (--threshold 45 vs 60)
multi-TF    : 15m + 1H + 4H simultanés
```

### Sortie Phase 2.5
Tu peux voir tes signaux ICT tracés sur graphique en 30 minutes (3 mois de données).
Validation visuelle immédiate, bien plus rapide que le paper trading.
Spécification complète : [08-replay-mode-spec.md](08-replay-mode-spec.md)

---

## Phase 3 : ICT Detectors (semaines 5-6)

**Dépendances** : Phase 2 (OHLCV disponible)
**Objectif** : Tous les détecteurs ICT fonctionnels

### Livrables

| Module | Description | Tests |
|---|---|---|
| Swing Detector | Multi-TF 15m/1H/4H, N=5, anti-repaint | 5 tests |
| FVG Detector | Détection + classification + expiry | 4 tests |
| Sweep Detector | Liquidity sweep + sweep_anchored_to | 4 tests |
| AMD Detector | P(acc/man/dist) probabiliste | 4 tests |
| SMT Detector | Intra-asset (delta) + Cross-asset (BTC vs ETH) | 4 tests |
| Judas Swing | Kill Zone open sweeps | 3 tests |
| Silver Bullet | 15:00-16:00 UTC FVG | 3 tests |
| Turtle Soup | Fausse cassure + confirmation | 3 tests |
| Displacement + OTE | Jambe directionnelle + fib zone | 3 tests |
| Trading Range | External swings + zones | 3 tests |
| BOS/CHoCH | Machine état de tendance | 5 tests |
| Kill Zones Scheduler | UTC + weekend mode | 4 tests |
| Global Market State | État unifié mis à jour on bar_close | 3 tests |

### Validation visuelle
- Swings tracés sur graphiques OHLCV (15m, 1H, 4H)
- FVG marqués avec leur statut (active/aged/consumed)
- AMD phases superposées au prix
- Kill Zones affichées en bandes colorées

### Sortie Phase 3
Tous les patterns ICT sont détectés et visualisables.
Les signaux bruts alimentent le Signal Pool.

---

## Phase 4 : Strategy Engine (semaines 7-8)

**Dépendances** : Phase 3 (détecteurs ICT)
**Objectif** : Signal Scoring + Lifecycle + TradeIntent génération

### Livrables

| Module | Description |
|---|---|
| Signal Pool | Registre in-memory + Redis backup des signaux |
| Lifecycle Engine | 5 états (DETECTED→ACTIVE→REINFORCED→DECAYING→INVALIDATED) |
| Scoring Grids | 6 grilles de scoring par setup type |
| Decay Engine | Formule exponentielle, taux par type |
| Interaction Rules | Réactivation sweep+FVG, SMT+sweep, AMD+bias |
| Bias Composite | 0.50 structural + 0.20 LLM + 0.15 on-chain + 0.15 funding |
| TradeIntent Generator | Score → tier → TradeIntent avec stop/TP ICT |
| Kelly Calculator | Rolling Kelly par setup, auto-disable |

### Sortie Phase 4
Le Strategy Engine reçoit des signaux bruts, les score, les fait vivre/mourir,
et génère des TradeIntent. Backtest complet de stratégie ICT possible.
Le bias composite est prêt à recevoir les 4 composants (structural, LLM, on-chain, funding).

---

## Phase 5 : LLM Analyst + On-Chain Integration (semaines 9-10)

**Dépendances** : Phases 3+4 (contexte ICT disponible)
**Objectif** : Intégration DeepSeek V4 (macro) + pipeline on-chain (netflow, stablecoins, delta)

### Livrables LLM Macro

| Module | Description |
|---|---|
| Context Builder | Agrège données ICT + marché pour le prompt LLM |
| API Client | DeepSeek V4 avec retry + timeout |
| Response Parser | JSON parsing avec fallback et validation |
| Bias History | Stockage Postgres des biais |
| Composite Integrator | Injection du bias LLM dans le composite (20%) |
| Defensive Mode | Fallback TTL → pas de trades |

### Livrables SL/TP (structurels)

| Module | Description |
|---|---|
| SL/TP Calculator | Calcul SL, TP1, TP2 par setup selon règles ICT (`config/sltp_standards.yaml`) |
| TradeIntent Generator | Entry + SL + TP1 + TP2 → TradeIntent avec taille calibrée |
| RM Validator | Vérification distance SL (0.1%-20%), buffer liq (2×), OCO atomique |

### Livrables On-Chain (nouveau)

| Module | Fichier(s) | Description |
|---|---|---|
| On-Chain Collector | `core/onchain/collector.py` | Glassnode (netflow), DefiLlama (stablecoins USDT/USDC), Binance (aggTrades delta) |
| Post-Processor | `core/onchain/post_processor.py` | 9 règles de parsing déterministes — phrase LLM → deltas numériques |
| On-Chain Bias | `core/onchain/bias.py` | Calcul du 15% on-chain dans le composite |
| Stockage | Tables `on_chain_snapshots`, `on_chain_bias_history` | Postgres |

### Post-Processing (déterministe)

| Motif LLM | Delta |
|---|---|
| Netflow sorties (outflow) | +0.10 / -0.10 |
| Stablecoin minting (>500M/24h) | +0.05 / -0.05 |
| Delta divergence bullish/bearish | +0.05 / -0.05 |
| Confluence max (3 signaux) | ±0.15 |
| Données insuffisantes / neutre | 0.00 |

### Sortie Phase 5
Le LLM alimente le bias_composite (20% macro + 15% on-chain).
Le système peut tourner avec ou sans LLM (fallback structural+funding).
Le module on-chain est entièrement backtestable via le replay mode (Phase 2.5).
Spécification complète : [07-on-chain-integration.md](07-on-chain-integration.md)

---

## Phase 6 : Intégration + Tests E2E + Optimisation SL/TP (semaines 11-13)

**Dépendances** : Phases 1-5
**Objectif** : Système complet intégré, testé de bout en bout, SL/TP optimisés par walk-forward

### Étapes

1. **Docker Compose** : Tous les containers
2. **Redis messaging** : Vérification de tous les channels
3. **Postgres migrations** : Toutes les tables créées
4. **Tests E2E** : Signal → Score → Intent → Risk → Order
5. **Tests de robustesse** :
   - Coupure WebSocket → reconnection
   - API Binance down → graceful degradation
   - Kill Switch déclenché → tous les modules respectent
   - Restart complet → état restauré
6. **Backtest ICT complet** sur 2 ans, walk-forward
7. **Monitoring setup** : Grafana + Telegram

### Livrables SL/TP (calibration + dynamique)

| Module | Description |
|---|---|
| Walk-Forward Calibrator | Grid search ATR multipliers ±30%, fenêtre 6/2 mois, métrique profit factor |
| Partiel + Breakeven | Close 50% à TP1, SL → entry, sortie anticipée si DECAYING |
| Trailing SL | Activé seulement si score PREMIUM (≥ 80), suit swings LTF 15m |
| Bias Invalidation | Close complet si bias_composite change de signe |
| Replay Calibration CLI | `scripts/replay_calibrate.py` — grid search paramétrique |

### Critères de calibration
- Profit factor OOS amélioré vs baseline structurelle
- Win rate ≥ 50% sur toutes les fenêtres
- Stabilité : écart-type multipliers < 0.15 × médiane
- Multipliers dans [0.7×, 1.3×] du standard ICT

### Critères de passage
- Sharpe OOS > 1.5
- Max DD < 15%
- Profit factor > 1.5
- Cohérence sur 3+ paires
- Stabilité sur plusieurs régimes

### Sortie Phase 6
Système complet prêt pour le paper trading.

---

## Phase 7 : Paper Trading (30 jours minimum)

**Dépendances** : Phase 6 validée + Phase 2.5 Replay Mode validé sur 8-10 actifs

> ⚠️ **Condition** : La réduction de 60 → 30 jours est conditionnée à un Replay Mode
> validé sur au moins 8 actifs (5 Phase 1 + 3 supplémentaires). Sans Replay Mode
> validé, la durée reste 60 jours minimum (AD-017).

**Objectif** : Validation infrastructure — latence, rejets d'ordres, déconnexions WebSocket

### Configuration
- Capital testnet : 10,000 USDT
- Isolated margin
- Levier max 3x
- Risk/trade 0.25%

### Monitoring quotidien
- Logs de tous les trades
- Divergences backtest vs live
- Slippage réel vs modélisé
- Latence mesurée
- Incidents et edge cases

### Critères de passage
- Sharpe live >= 60% du Sharpe backtest
- Zéro incident critique (30 derniers jours)
- Tous les régimes de marché traversés
- DD réel <= DD backtest
- Slippage/frais réels cohérents avec modèle

---

## Phase 8 : Capital Réel (3-6 mois après Phase 7)

**Dépendances** : Phase 7 validée
**Objectif** : Découverte des derniers edge cases

### Configuration
- Capital : 200-500 USDT (minimum Binance)
- Mêmes paramètres que paper trading
- Objectif : zéro profit espéré, 100% apprentissage

### Scaling progressif
- Jamais doubler le capital d'un coup
- Augmentation mensuelle si Sharpe stable
- Max 20% d'augmentation par mois
- Rollback si DD > 15%

---

## Récapitulatif des durées

| Phase | Contenu | Durée |
|---|---|---|
| Phase 1 | Risk Manager | 2 semaines |
| Phase 2 | Data Pipeline + Backtester | 2 semaines |
| Phase 2.5 | Replay Mode (8-10 actifs) | 1-2 semaines |
| Phase 3 | ICT Detectors | 2 semaines |
| Phase 4 | Strategy Engine (scoring + lifecycle) | 2 semaines |
| Phase 5 | LLM Analyst + On-Chain + SL/TP structurels | 3 semaines |
| Phase 6 | Intégration + Tests E2E + Calibration SL/TP | 3 semaines |
| Phase 7 | Paper Trading (conditionnel) | 1 mois (30j si Replay validé) |
| Phase 8 | Capital Réel | 3-6 mois |

**Total développement** : ~14 semaines (Phases 1-6)
**Total validation** : ~1.5-6 mois (Phases 7-8, selon Replay Mode)
**Total projet** : ~4-8 mois avant scaling réel

---

## Dépendances entre phases

```
Phase 1 ──────┐
              ├──► Phase 2 ──► Phase 2.5 ──► Phase 3 ──► Phase 4 ──┐
              │                                                      ├──► Phase 6 ──► Phase 7 ──► Phase 8
              └─────────────────────────────────────────► Phase 5 ──┘
                                                              │
                                                        On-Chain Module
```

Les Phases 1-2-2.5-3-4 sont séquentielles.
La Phase 5 (LLM + On-Chain) peut être développée en parallèle des Phases 3-4.
La Phase 6 est le point d'intégration.
Le Replay Mode (Phase 2.5) sert à valider visuellement chaque détecteur dès sa création.

---

## Risques projet

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Overfitting backtest | Élevé | Critique | Walk-forward obligatoire, OOS validation |
| LLM hallucinations | Moyen | Moyen | Poids limité (20% macro + 15% on-chain déterministe), fallback structural |
| Bugs silencieux Risk Manager | Faible | Critique | Tests adversariaux exhaustifs Phase 1 |
| Latence Algérie → Binance | Certain | Faible | 15m-4H timeframe, pas de sub-minute |
| Paper trading non représentatif | Moyen | Élevé | 30 jours minimum (conditionné au Replay Mode validé), validation multi-régime |
| Impulsivité humaine | Moyen | Élevé | Kill Switch codé dur, commit freeze |
| API Binance downtime | Faible | Faible | Retry exponentiel, defensive mode |
| Changement réglementaire | Faible | Critique | Monitoring légal Algérie, fonds P2P uniquement |

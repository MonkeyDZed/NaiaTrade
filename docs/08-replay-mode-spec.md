# Replay Mode — Spécification v1.0

> Simulation bar-par-bar sur données historiques.
> Permet de tester tous les modules NaiaTrade sans attendre le temps réel.
> Phase 2.5 du roadmap. MVP en 1-2 jours.

---

## Vue d'ensemble

Le Replay Mode est le chaînon entre le backtest vectorisé (Phase 2) et le paper trading (Phase 7). Il exécute l'intégralité du pipeline NaiaTrade — détecteurs ICT, Signal Lifecycle, Strategy Engine — sur des données historiques, **barre par barre**, en simulant le passage du temps.

```
Backtest vectorisé  ──►  Replay Mode  ──►  Paper Trading  ──►  Live
(rapide, agrégé)        (debug, visuel)    (testnet réel)      (capital réel)
```

---

## 1. Objectifs

| Objectif | Description |
|----------|-------------|
| **Validation visuelle** | Voir les swings, FVG, sweeps tracés sur les graphiques en temps simulé |
| **Debug des détecteurs** | Exécuter pas à pas, inspecter les états intermédiaires |
| **Test du Signal Lifecycle** | Observer DETECTED → ACTIVE → REINFORCED → DECAYING → INVALIDATED |
| **A/B test des paramètres** | Comparer deux configurations de scoring sans redéployer |
| **Test on-chain** | Injecter des snapshots on-chain historiques dans le replay |
| **Régression** | Vérifier qu'un changement ne casse pas les signaux passés |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     REPLAY ENGINE                                │
│                                                                 │
│  ┌─────────────────┐                                            │
│  │ Historical Loader│  ← Parquet / Postgres (3 mois à 3 ans)    │
│  └────────┬────────┘                                            │
│           │ DataFrame (timestamp, open, high, low, close, vol)  │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  REPLAY LOOP (bar-by-bar)                   ││
│  │                                                             ││
│  │  for bar in df:                                             ││
│  │    1. Inject bar → Global Market State                      ││
│  │    2. Exécuter ICT Detectors (swing, FVG, sweep, AMD...)    ││
│  │    3. Exécuter SMT / Judas / Silver Bullet                  ││
│  │    4. Mettre à jour Signal Pool                             ││
│  │    5. Exécuter Lifecycle Engine (decay, interactions)       ││
│  │    6. Optionnel : Strategy Engine → TradeIntent fictif       ││
│  │    7. Optionnel : Risk Manager → RiskAssessment fictif       ││
│  │    8. Logger / export état courant                           ││
│  │                                                             ││
│  │  Speed: 1x (temps réel) à 10000x (instantané)               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ CSV Logger      │  │ Plotly Renderer  │  │ Report Generator│ │
│  │ (signaux/états) │  │ (graphiques)     │  │ (métriques)     │ │
│  └─────────────────┘  └──────────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Modes de replay

### 3.1 Replay Standard (détecteurs seuls)

Exécute uniquement les détecteurs ICT. Pas de Strategy Engine ni Risk Manager.

```bash
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-02-01 --end 2026-05-01 \
  --mode detectors
```

**Sorties** : Signaux bruts dans un CSV, graphique Plotly avec swings/FVG.

### 3.2 Replay Complet (full pipeline)

Exécute tous les modules jusqu'au TradeIntent fictif.

```bash
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-02-01 --end 2026-05-01 \
  --mode full
```

**Sorties** : Signaux, TradeIntents, RiskAssessments, métriques de performance.

### 3.3 Replay Comparatif (A/B test)

Compare deux configurations côte à côte.

```bash
python scripts/replay_compare.py --symbol BTCUSDT \
  --start 2026-02-01 --end 2026-05-01 \
  --config_a scoring_v1.3.yaml \
  --config_b scoring_experimental.yaml
```

**Sorties** : Tableau comparatif des métriques, graphiques superposés.

### 3.4 Replay What-If (paramètres)

Teste l'impact d'un changement de paramètre.

```bash
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-02-01 --end 2026-05-01 \
  --minimal_threshold 40 --standard_threshold 55 --premium_threshold 75 \
  --decay_rate_sweep 0.15 --decay_rate_fvg 0.10
```

### 3.5 Replay Multi-TF

Exécute les 3 timeframes simultanément (15m, 1H, 4H).

```bash
python scripts/replay.py --symbol BTCUSDT \
  --timeframe 15m,1H,4H \
  --start 2026-02-01 --end 2026-05-01 \
  --mode full
```

---

## 4. Chargement des données historiques

### 4.1 Sources

| Source | Format | Période minimale | Téléchargement |
|--------|--------|-----------------|----------------|
| Fichiers Parquet | `.parquet` | 3 ans | Phase 2 (Data Pipeline) |
| Postgres | Table `ohlcv_15m`, `ohlcv_1h`, `ohlcv_4h` | 3 ans | Phase 2 |
| CCXT direct | Appel API Binance | 1000 bougies max | Fallback / test rapide |

### 4.2 API du Historical Loader

```python
# core/data/historical_loader.py

def load_ohlcv(
    symbol: str,
    timeframe: str,         # "15m", "1H", "4H"
    start: datetime,
    end: datetime,
    source: str = "parquet"  # "parquet", "postgres", "ccxt"
) -> pd.DataFrame:
    """
    Retourne un DataFrame avec les colonnes :
    timestamp, open, high, low, close, volume
    
    Compatible avec le format utilisé par les WebSocket en live.
    """
    ...
```

### 4.3 Téléchargement rapide (CCXT)

```bash
# Télécharger 3 mois de BTC 1H pour test rapide
python scripts/download_historical.py --symbol BTCUSDT --timeframe 1H \
  --months 3 --output data/btc_1h_3m.parquet
```

---

## 5. Boucle de replay

### 5.1 Structure minimale

```python
# scripts/replay.py

import argparse
from datetime import datetime
from core.data.historical_loader import load_ohlcv
from core.market.global_state import GlobalMarketState
from core.ict.detectors import (
    SwingDetector, FVGDector, SweepDetector, AMDDetector,
    SMTDetector, JudasSwingDetector, SilverBulletDetector,
    TurtleSoupDetector, DisplacementOTEDetector, BOSChoCHDetector
)
from core.strategy.signal_pool import SignalPool
from core.strategy.lifecycle import LifecycleEngine
from core.strategy.scoring import ScoringEngine
from core.strategy.bias_composite import BiasComposite
from core.replay.logger import ReplayLogger
from core.replay.renderer import ReplayRenderer


def replay(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    mode: str = "detectors",
    speed: float = 0.0,       # 0 = instantané, 1 = temps réel
    config: dict = None
):
    # 1. Charger les données
    df = load_ohlcv(symbol, timeframe, start, end)
    
    # 2. Initialiser les modules
    global_state = GlobalMarketState(symbol, historical_mode=True)
    signal_pool = SignalPool()
    
    detectors = init_detectors(timeframe, config)
    lifecycle = LifecycleEngine(signal_pool, config)
    scoring = ScoringEngine(config) if mode == "full" else None
    bias = BiasComposite(config) if mode == "full" else None
    
    logger = ReplayLogger(symbol, timeframe, start, end)
    renderer = ReplayRenderer(interactive=True)  # Plotly
    
    # 3. Boucle barre par barre
    bars_since_start = 0
    for idx, bar in df.iterrows():
        current_time = bar["timestamp"]
        bars_since_start += 1
        
        # Phase 1 : Injecter la barre
        global_state.on_bar_close(bar, historical_mode=True)
        
        # Phase 2 : Exécuter tous les détecteurs
        for detector in detectors.values():
            detector.process_bar(bar, global_state)
        
        # Phase 3 : Mettre à jour le Signal Pool
        new_signals = collect_signals(detectors, current_time)
        signal_pool.add_batch(new_signals)
        
        # Phase 4 : Lifecycle (decay + interactions)
        lifecycle.update(current_time, signal_pool, global_state)
        
        # Phase 5 : Strategy Engine (si mode full)
        trade_intents = []
        if mode == "full":
            for signal in signal_pool.get_tradable():
                score = scoring.calculate(signal, global_state)
                if score >= config["minimal_threshold"]:
                    intent = scoring.generate_intent(signal, score, bias)
                    trade_intents.append(intent)
        
        # Phase 6 : Logger
        logger.log_bar(current_time, {
            "swings": detectors["swing"].get_state(),
            "fvgs": detectors["fvg"].get_state(),
            "signals_active": signal_pool.count_active(),
            "trade_intents": len(trade_intents)
        })
        
        # Phase 7 : Rendu (optionnel)
        if speed <= 10:
            renderer.update(df, detectors, signal_pool, current_time)
    
    # 4. Rapport final
    logger.generate_report()
```

### 5.2 Gestion du temps simulé

```python
# Vitesse de replay
SPEED_PRESETS = {
    "instant": 0,        # Pas de pause, le plus rapide
    "fast": 100,         # 100x temps réel
    "medium": 10,        # 10x
    "realtime": 1,       # 1x (temps réel simulé)
    "slow": 0.5          # 0.5x (ralenti, pour debug)
}

# Pour 1H timeframe :
#   instant : 3 mois = ~3 secondes
#   fast     : 3 mois = ~4 minutes
#   medium   : 3 mois = ~36 minutes
#   realtime  : 3 mois = 3 mois (2160 heures)
```

---

## 6. Module Global Market State (mode replay)

Le `GlobalMarketState` doit fonctionner en mode historique, sans dépendances Redis/Binance :

```python
# core/market/global_state.py

class GlobalMarketState:
    def __init__(self, symbol: str, historical_mode: bool = False):
        self.symbol = symbol
        self.historical_mode = historical_mode
        
        # Composants (identiques au mode live)
        self.trend = TrendState()
        self.session = SessionState()
        self.volatility = VolatilityState()
        self.liquidity = LiquidityState()
    
    def on_bar_close(self, bar: dict, **kwargs):
        """Mise à jour sur clôture de bougie. Point d'entrée unique."""
        
        if self.historical_mode:
            # Pas de lecture Redis, tout est calculé ou injecté
            self._update_trend(bar)
            self._update_session_historical(bar)
            self._update_volatility(bar)
            self._update_liquidity(bar)
        else:
            # Mode live normal (Redis pub/sub)
            self._update_from_redis()
    
    def _update_session_historical(self, bar: dict):
        """En mode replay, la Kill Zone et le weekend sont calculés
        à partir du timestamp de la barre historique."""
        ts = bar["timestamp"]
        self.session.active_kz = get_kill_zone(ts)
        self.session.is_weekend = ts.weekday() >= 5
        self.session.key_time_prox = get_key_time_proximity(ts)
        self.session.vol_ratio = bar.get("volume", 0) / self.vol_median_7d
```

---

## 7. Visualisation (Plotly)

### 7.1 Graphique principal

```python
# core/replay/renderer.py

import plotly.graph_objects as go

class ReplayRenderer:
    def __init__(self, interactive: bool = True):
        self.interactive = interactive
        self.fig = None
    
    def update(self, df, detectors, signal_pool, current_time):
        """Met à jour le graphique avec la bougie courante."""
        
        if self.fig is None:
            self._init_figure(df)
        
        # Bougies
        self.fig.data[0].x = df["timestamp"]
        self.fig.data[0].open = df["open"]
        self.fig.data[0].high = df["high"]
        self.fig.data[0].low = df["low"]
        self.fig.data[0].close = df["close"]
        
        # Swings (markers)
        for swing in detectors["swing"].confirmed:
            self.fig.add_trace(go.Scatter(
                x=[swing["time"]],
                y=[swing["level"]],
                mode="markers",
                marker=dict(
                    symbol="triangle-up" if swing["type"] == "high" else "triangle-down",
                    size=12,
                    color="blue" if swing["layer"] == "external" else
                          "orange" if swing["layer"] == "short_term" else "gray"
                ),
                name=f"Swing {swing['layer']}"
            ))
        
        # FVG (rectangles)
        for fvg in detectors["fvg"].active:
            self.fig.add_shape(
                type="rect",
                x0=fvg["time"], x1=fvg["expiry"],
                y0=fvg["low"], y1=fvg["high"],
                fillcolor="rgba(0,255,0,0.2)" if fvg["type"] == "up" else "rgba(255,0,0,0.2)",
                line=dict(width=0)
            )
        
        # Kill Zones (bandes colorées)
        for kz_name, (kz_start, kz_end) in get_kill_zones_for_chart(df).items():
            color = {"LONDON": "blue", "NY_AM": "gold", "NY_PM": "gray"}.get(kz_name, "white")
            # Ajouter des bandes verticales pour la journée en cours
        
        # Ligne verticale pour la bougie courante
        self.fig.add_vline(x=current_time, line_color="purple", line_width=1)
        
        if self.interactive:
            self.fig.show()
    
    def _init_figure(self, df):
        self.fig = go.Figure(data=[go.Candlestick(
            x=df["timestamp"],
            open=df["open"], high=df["high"],
            low=df["low"], close=df["close"],
            name="Price"
        )])
        
        self.fig.update_layout(
            title="NaiaTrade Replay",
            xaxis_title="Time",
            yaxis_title="Price",
            template="plotly_dark",
            height=800
        )
```

### 7.2 Graphiques secondaires (optionnels)

| Graphique | Description |
|-----------|-------------|
| Volume + Volume Profile | Barres de volume + zones HVN/LVN |
| AMD Phases | Superposition des phases Accumulation/Manipulation/Distribution |
| Signal Timeline | Barres colorées par état de signal (ACTIVE/DECAYING/INVALIDATED) |
| Bias Composite | Courbe du bias dans le temps (structural/LLM/funding/on-chain) |
| Trade Markers | Flèches entrée/sortie sur les trades fictifs |

---

## 8. Logger et export

### 8.1 CSV de signaux

```csv
timestamp,symbol,signal_type,layer,price_level,state,score,bars_active
2026-02-15T14:00:00Z,BTCUSDT,sweep,external,66200,ACTIVE,65,2
2026-02-15T14:00:00Z,BTCUSDT,fvg,short_term,67200,DETECTED,40,0
2026-02-15T15:00:00Z,BTCUSDT,sweep,external,66200,REINFORCED,80,3
```

### 8.2 CSV de trades fictifs (mode full)

```csv
entry_time,symbol,direction,entry_price,stop_loss,take_profit,score,tier,size_notional
2026-02-15T16:00:00Z,BTCUSDT,LONG,66300,65800,67400,80,PREMIUM,1250
```

### 8.3 Rapport automatique (JSON)

```json
{
  "config": {
    "symbol": "BTCUSDT",
    "timeframe": "1H",
    "start": "2026-02-01",
    "end": "2026-05-01",
    "mode": "full",
    "speed": "instant"
  },
  "summary": {
    "total_bars": 2160,
    "signals_detected": 187,
    "signals_traded": 38,
    "win_rate": 0.57,
    "profit_factor": 1.42,
    "max_drawdown_pct": 12.3,
    "sharpe_ratio": 1.68
  },
  "by_setup": {
    "sweep": {"signals": 45, "trades": 12, "win_rate": 0.58},
    "silver_bullet": {"signals": 22, "trades": 8, "win_rate": 0.62},
    "amd": {"signals": 15, "trades": 5, "win_rate": 0.60}
  },
  "by_tier": {
    "MINIMAL": {"trades": 10, "win_rate": 0.40},
    "STANDARD": {"trades": 18, "win_rate": 0.55},
    "PREMIUM": {"trades": 10, "win_rate": 0.70}
  }
}
```

---

## 9. Replay avec données on-chain

### 9.1 Injection de snapshots on-chain

Le replay mode peut injecter des snapshots on-chain historiques pour tester le pipeline complet (Phase 5.5).

```python
# scripts/replay.py --mode full --with_onchain

# Charger les snapshots on-chain historiques
onchain_snapshots = load_onchain_snapshots(symbol, start, end)

for bar in df.iterrows():
    current_time = bar["timestamp"]
    
    # Injecter le snapshot on-chain correspondant à cette heure
    snapshot = onchain_snapshots.get(current_time.floor("1h"))
    if snapshot:
        global_state.inject_onchain(snapshot)
    
    # ... reste du replay
```

### 9.2 Test du Post-Processor on-chain

```bash
# Replay avec on-chain : test complet du pipeline
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-02-01 --end 2026-05-01 \
  --mode full --with_onchain \
  --config scoring_v1.3_onchain.yaml
```

---

## 10. Interface CLI

```bash
# Usage de base
python scripts/replay.py --symbol <SYMBOL> --timeframe <TF> \
  --start <YYYY-MM-DD> --end <YYYY-MM-DD> [OPTIONS]

# Options
--mode          detectors|full         Mode replay (défaut: detectors)
--speed         FLOAT                 Vitesse (0=instant, 1=realtime, défaut: 0)
--visualize     BOOL                  Activer Plotly (défaut: True en mode detectors)
--output        DIR                   Dossier de sortie pour CSV/rapport
--config        FILE.yaml             Configuration scoring personnalisée
--with_onchain  BOOL                  Injecter snapshots on-chain (défaut: False)
--with_llm      BOOL                  Appeler le LLM à chaque heure (défaut: False)

# Exemples
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-02-01 --end 2026-05-01

python scripts/replay.py --symbol ETHUSDT --timeframe 15m,1H,4H \
  --start 2026-03-01 --end 2026-05-01 --mode full --speed 100

python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-01-01 --end 2026-05-01 --mode full \
  --config scoring_v1.3.yaml --output reports/btc_v1.3/

# Comparaison A/B
python scripts/replay_compare.py --symbol BTCUSDT \
  --start 2026-02-01 --end 2026-05-01 \
  --config_a scoring_v1.2.yaml \
  --config_b scoring_v1.3.yaml
```

---

## 11. Configuration YAML

```yaml
# config/replay.yaml

replay:
  # Données par défaut
  default_symbol: "BTCUSDT"
  default_timeframe: "1H"
  default_start: "2026-02-01"
  default_end: "2026-05-01"
  default_speed: 0           # instantané
  
  # Dossiers
  data_dir: "data/"
  output_dir: "reports/replay/"
  
  # Visualisation
  visualize: true
  plotly_template: "plotly_dark"
  show_kill_zones: true
  show_fvg: true
  show_swings: true
  show_signals: true
  
  # Limites de slippage simulé
  slippage_pct: 0.03         # 0.03% slippage simulé
  latency_ms_min: 50         # Latence réseau simulée min
  latency_ms_max: 300        # Latence réseau simulée max
  
  # Filtres Binance simulés
  simulate_binance_filters: true
  min_notional: 5.0
  
  # On-chain (si --with_onchain)
  onchain_snapshot_dir: "data/onchain/"
  onchain_validate: true
  
  # Rapport
  generate_report: true
  report_format: "json"       # json, html, md
  export_signals_csv: true
  export_trades_csv: true
```

---

## 12. Fichiers du module

```
core/replay/
├── __init__.py
├── engine.py              # Boucle de replay principale
├── logger.py              # CSV + rapport
├── renderer.py            # Plotly visualization
└── config.py              # Chargement config YAML

scripts/
├── replay.py              # CLI replay standard
├── replay_compare.py      # CLI A/B comparison
└── download_historical.py # Téléchargement rapide CCXT
```

---

## 13. Limites du replay mode

| Limite | Impact | Mitigation |
|--------|--------|------------|
| Pas de latence réseau réelle | Les signaux semblent plus propres | Ajouter délai aléatoire 50-300ms dans la boucle |
| Pas de slippage réel | P&L fictif optimiste | Appliquer slippage modélisé (0.02-0.05%) |
| Pas de rejets d'ordres Binance | Tous les Intent passent | Simuler les filtres Binance (minNotional, stepSize) |
| Pas de déconnexions WebSocket | Robustesse non testée | → Phase 7 (Paper Trading) pour ça |
| Pas de funding rate variable | P&L overnight simulé | Appliquer funding rate historique depuis les données |
| Données historiques = pas de black swans | Edge cases non découverts | Compléter avec paper trading réel |
| LLM appelé sur données passées | Peut "voir le futur" via les données | Le LLM ne reçoit que les données jusqu'à la barre courante |

---

## 14. Tests

### 14.1 Tests unitaires

```
test_historical_loader_returns_dataframe
test_historical_loader_timeframe_filter
test_global_state_historical_mode
test_global_state_session_historical
test_replay_loop_iterates_all_bars
test_replay_loop_speed_instant
test_replay_loop_speed_realtime
test_logger_creates_csv
test_logger_generates_report
test_config_loader_yaml
```

### 14.2 Tests d'intégration

```
test_replay_detectors_mode_on_3_months_btc
test_replay_full_mode_generates_trade_intents
test_replay_with_onchain_snapshots
test_replay_compare_generates_diff_report
test_replay_multi_tf_synchronization
test_replay_visualization_renders_without_error
```

### 14.3 Tests de non-régression

```
test_signals_v1_3_match_reference    ← golden dataset
test_trade_count_within_expected_range
test_signal_lifecycle_transitions_valid
```

---

## 15. Golden Dataset (jeu de référence)

Pour les tests de non-régression, un jeu de données de référence est créé :

```bash
# Générer le golden dataset une seule fois
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-01-01 --end 2026-03-31 \
  --mode full --output tests/golden/

# Ce dossier contient :
# tests/golden/
#   ├── signals.csv        # Tous les signaux détectés
#   ├── trades.csv         # Tous les trades fictifs
#   ├── report.json        # Métriques de référence
#   └── config.yaml        # Configuration utilisée

# Vérification de non-régression
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-01-01 --end 2026-03-31 \
  --mode full --golden tests/golden/ --tolerance 0.05
```

Si les métriques divergent de plus de 5% du golden dataset → le test échoue.

---

## Changelog

**v1.0** (2026-05-15)
- [NEW] Replay Mode spécification complète (Phase 2.5)
- [NEW] 5 modes : detectors, full, compare, what-if, multi-TF
- [NEW] Historical Loader compatible Parquet/Postgres/CCXT
- [NEW] GlobalMarketState en mode historique (sans Redis/Binance)
- [NEW] Visualisation Plotly avec swings, FVG, Kill Zones
- [NEW] Logger CSV + rapport JSON
- [NEW] Replay avec injection de snapshots on-chain
- [NEW] Interface CLI complète (argparse)
- [NEW] Configuration YAML centralisée
- [NEW] Golden dataset pour tests de non-régression
- [NEW] Slippage et latence simulés

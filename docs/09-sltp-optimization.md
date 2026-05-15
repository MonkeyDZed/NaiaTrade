# SL/TP Optimization — Spécification v1.0

> Architecture hybride : cadre ICT structurel + calibration statistique walk-forward.
> Objectif : maximiser le profit factor sous contrainte win rate ≥ 50%.
> Les niveaux de SL et TP dérivent de la structure du marché, pas d'un ratio R:R fixe.

---

## Vue d'ensemble

Ce document définit la stratégie complète de placement et d'optimisation des Stop Loss (SL) et Take Profit (TP) pour chaque setup ICT. Il remplace les définitions partielles et éparses de `01-ict-specs-v1.3.md` par une table exhaustive et formalise le processus de calibration statistique.

**Philosophie** : *"Trade the structure, not the math."*

---

## 1. Table SL/TP exhaustive par setup ICT

### 1.1 Judas Swing

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Au-delà du range sweepé + `0.3 × ATR` | `01-ict-specs` §9 |
| **TP1** (50% position) | Boundary opposée du range sweepé | Règle structurelle |
| **TP2** (50% position) | External swing opposé (4H) + FVG adjacent | Règle structurelle |
| **Entry** | Après close de confirmation dans la direction du sweep | `01-ict-specs` §9 |
| **Sizing** | Standard ×1.25, avec AMD ×1.5 | `01-ict-specs` §9 |

### 1.2 AMD Distribution

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Boundary opposée du range de manipulation | `01-ict-specs` §5 |
| **TP1** (50% position) | FVG adjacent formé dans la direction de distribution | Règle structurelle |
| **TP2** (50% position) | Prochain niveau de liquidité identifiable (swing 4H ou FVG HTF) | Règle structurelle |
| **Entry** | P_dist > 0.65 ET P_man pic dans les 3 dernières bougies | `01-ict-specs` §5 |
| **Sizing** | Standard ×1.25 | `01-ict-specs` §5 |

### 1.3 Turtle Soup

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Buffer ATR selon layer : micro `0.2×`, short `0.4×`, external `0.7×` ATR | `01-ict-specs` §13 |
| **TP1** (50% position) | Zone de manipulation initiale (côté opposé) | Règle structurelle |
| **TP2** (50% position) | Liquidité adverse au-delà de la zone de manipulation | Règle structurelle |
| **Entry** | Fausse cassure + rejet + confirmation barre suivante | `01-ict-specs` §13 |
| **Sizing** | Layer : micro ×0.5, short ×1.0, external ×1.5 | `01-ict-specs` §13 |

### 1.4 Unicorn Model

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Swing external (4H) + `0.7 × ATR` | `01-ict-specs` §15 |
| **TP1** (50% position) | FVG premium + OTE overlap zone | Règle structurelle |
| **TP2** (50% position) | Liquidité adverse opposée (external swing + FVG HTF) | Règle structurelle |
| **Entry** | 5 conditions obligatoires remplies | `01-ict-specs` §15 |
| **Sizing** | Base ×1.5, max ×1.8 | `01-ict-specs` §15 |

### 1.5 Silver Bullet

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Swing le plus proche dans le sens opposé au trade + `0.3 × ATR` | Règle structurelle |
| **TP1** (50% position) | FVG formé dans la fenêtre Silver Bullet (comblement) | Règle structurelle |
| **TP2** (50% position) | Swing externe opposé (4H) ou FVG HTF adjacent | Règle structurelle |
| **Entry** | Premier retest du FVG dans la fenêtre 15:00-16:00 UTC | `01-ict-specs` §10 |
| **Sizing** | Base ×1.0, +0.15 par boost, max ×1.45 | `01-ict-specs` §10 |

### 1.6 Sweep / FVG Standard

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Au-delà du swing ou FVG qui sert de référence au setup + `0.2 × ATR` | `01-ict-specs` §8 |
| **TP1** (50% position) | FVG adjacent ou OTE zone | Règle structurelle |
| **TP2** (50% position) | Swing externe opposé (4H) ou equal highs/lows | Règle structurelle |
| **Entry** | Sweep confirmé avec close de l'autre côté + direction alignée HTF | `01-ict-specs` §8 |
| **Sizing** | Layer : micro ×0.5, short ×1.0, external ×1.5 | `01-ict-specs` §8 |

### 1.7 SMT Cross-Asset

| Paramètre | Règle | Référence |
|-----------|-------|-----------|
| **SL** | Au-delà du swing qui a généré la divergence SMT + `0.2 × ATR` | Règle structurelle |
| **TP1** (50% position) | FVG adjacent à la divergence | Règle structurelle |
| **TP2** (50% position) | External swing opposé (4H) | Règle structurelle |
| **Entry** | SMT confirmé + biais aligné + Kill Zone active | `01-ict-specs` §12 |
| **Sizing** | Standard selon scoring SMT | `01-ict-specs` §18 |

---

## 2. Validation Risk Manager (Règle 2)

Avant exécution, le Risk Manager applique 3 contrôles sur le SL calculé :

| Contrôle | Valeur | Conséquence si échec |
|----------|--------|---------------------|
| **Distance minimale** | `entry - SL` > 0.1% du prix | `REJECTED` — stop trop proche, stop-out sur slippage |
| **Distance maximale** | `entry - SL` < 20% du prix | `REJECTED` — stop trop loin, sizing inefficace |
| **Buffer liquidation** | `distance(Entry, SL) ≥ 2 × distance(Entry, Liq)` | `REJECTED` — risque de cascade de liquidation |
| **OCO atomique** | Entry + SL placés ensemble | Si Binance refuse le SL → entrée annulée |

Ces contrôles sont **codés en dur** (`03-risk-manager-spec.md` §Règle 2). Modification = commit git + redéploiement.

---

## 3. Calibration statistique — Multipliers ATR

### 3.1 Principe

Les niveaux SL/TP structurels sont affinés par des **multipliers ATR calibrés statistiquement** via backtest walk-forward. L'objectif est d'ajuster le paramètre ATR (par exemple `0.3 × ATR` → `0.25 × ATR` à `0.39 × ATR`) pour maximiser le profit factor.

### 3.2 Contrainte de calibration

| Paramètre | Valeur |
|-----------|--------|
| **Plage de recherche** | ±30% du standard ICT |
| **Métrique optimisée** | Profit factor |
| **Contrainte** | Win rate ≥ 50% |
| **Méthode** | Walk-forward (6 mois train / 2 mois test), fenêtre glissante |
| **Recalibration** | Tous les 3 mois minimum (marchés crypto non-stationnaires) |

Exemple : si le SL standard Turtle Soup micro = `0.2 × ATR`, la recherche explore `[0.14, 0.26]`.

### 3.3 Procédure walk-forward

```
Dataset : 24 mois de données historiques

Fenêtre 1 : Train [M1-M6]  → Test [M7-M8]   → multiplier optimal
Fenêtre 2 : Train [M3-M8]  → Test [M9-M10]  → multiplier optimal
Fenêtre 3 : Train [M5-M10] → Test [M11-M12] → multiplier optimal
...
Fenêtre N : Train [M17-M22] → Test [M23-M24] → multiplier optimal

Multiplier final = médiane des multipliers optimaux sur toutes les fenêtres
Écart-type des multipliers → mesure de stabilité (doit être < 0.15 × médiane)
```

### 3.4 Granularité de calibration

Les multipliers sont calibrés indépendamment pour :

| Dimension | Valeurs |
|-----------|---------|
| **Setup** | Judas, AMD, Turtle Soup, Unicorn, Silver Bullet, Sweep/FVG, SMT |
| **Timeframe** | 15m, 1H, 4H |
| **Actif** | BTC, ETH, SOL, BNB, DOT (Phase 1) |
| **Paramètre** | SL buffer ATR, TP1 distance, TP2 distance |

### 3.5 Sortie de calibration

```yaml
# Exemple de sortie après calibration
calibrated_params:
  turtle_soup:
    micro:
      sl_buffer_atr: 0.18     # Standard: 0.20, calibré: -10%
    short:
      sl_buffer_atr: 0.42     # Standard: 0.40, calibré: +5%
    external:
      sl_buffer_atr: 0.68     # Standard: 0.70, calibré: -3%
  judas_swing:
    sl_buffer_atr: 0.33       # Standard: 0.30, calibré: +10%
  silver_bullet:
    sl_buffer_atr: 0.28       # Standard: 0.30, calibré: -7%
```

---

## 4. Gestion dynamique du TP

Progression en 3 phases, alignée sur la roadmap.

### 4.1 Phase 4 — Niveaux initiaux fixes (MVP)

```
Entrée → SL fixe + TP1 fixe + TP2 fixe
Ordre OCO à 3 branches (entry limit, stop market, take profit market)
Aucune gestion post-entrée
```

**Avantage** : simplicité, backtestable, zéro surprise.

### 4.2 Phase 5.5 — Gestion partielle + breakeven

```
Quand prix atteint TP1 :
  → Fermeture 50% de la position
  → SL déplacé au prix d'entrée (breakeven) pour les 50% restants

Quand signal passe à DECAYING (score < 45) :
  → Sortie anticipée de la position restante

Quand signal passe à INVALIDATED (score < 40) :
  → Sortie immédiate, TP2 annulé
```

### 4.3 Phase 6 — Trailing SL conditionnel

```
Activé UNIQUEMENT si score PREMIUM (≥ 80) :
  → SL suit les swings LTF (15m) avec buffer 0.2 × ATR
  → Le SL ne recule jamais (monotone)
  → Désactivé si le signal passe sous STANDARD (< 60)

Si bias_composite inverse de signe :
  → Fermeture complète avant TP2
```

---

## 5. Fichier de configuration centralisé

```yaml
# config/sltp_standards.yaml
# Source unique de vérité pour les règles SL/TP.
# Modifié UNIQUEMENT via commit git documenté.

judas_swing:
  sl:
    rule: "beyond_swept_range"
    atr_multiplier: 0.3
    calibrated: null          # Rempli après Phase 6
  tp1:
    rule: "opposite_range_boundary"
    close_pct: 0.50
  tp2:
    rule: "external_swing_opposite_4h"
    with_fvg: true
  sizing_multiplier: 1.25
  sizing_with_amd: 1.5

amd_distribution:
  sl:
    rule: "opposite_range_boundary"
    atr_multiplier: 0.0        # Pas de buffer ATR additionnel
    calibrated: null
  tp1:
    rule: "adjacent_fvg"
    close_pct: 0.50
  tp2:
    rule: "next_liquidity_level"
  sizing_multiplier: 1.25

turtle_soup:
  sl:
    rule: "buffer_atr_by_layer"
    atr_multiplier: [0.2, 0.4, 0.7]   # [micro, short, external]
    calibrated: null
  tp1:
    rule: "opposite_manipulation_zone"
    close_pct: 0.50
  tp2:
    rule: "external_swing_opposite"
  sizing_multiplier: [0.5, 1.0, 1.5]  # [micro, short, external]

unicorn_model:
  sl:
    rule: "external_swing"
    atr_multiplier: 0.7
    calibrated: null
  tp1:
    rule: "fvg_premium_ote_overlap"
    close_pct: 0.50
  tp2:
    rule: "opposite_liquidity"
  sizing_multiplier: 1.5
  sizing_max: 1.8

silver_bullet:
  sl:
    rule: "nearest_opposite_swing"
    atr_multiplier: 0.3
    calibrated: null
  tp1:
    rule: "fvg_in_window"
    close_pct: 0.50
  tp2:
    rule: "external_swing_opposite_4h"
  sizing_multiplier: 1.0
  sizing_boost_per_boost: 0.15
  sizing_max: 1.45

sweep_fvg_standard:
  sl:
    rule: "beyond_reference_swing_or_fvg"
    atr_multiplier: 0.2
    calibrated: null
  tp1:
    rule: "adjacent_fvg_or_ote"
    close_pct: 0.50
  tp2:
    rule: "external_swing_opposite_4h"
  sizing_multiplier: [0.5, 1.0, 1.5]  # [micro, short, external]

smt_cross_asset:
  sl:
    rule: "beyond_smt_divergence_swing"
    atr_multiplier: 0.2
    calibrated: null
  tp1:
    rule: "adjacent_fvg"
    close_pct: 0.50
  tp2:
    rule: "external_swing_opposite_4h"
  sizing_multiplier: 1.0

# Paramètres globaux de calibration
calibration:
  atr_range_pct: 0.30           # ±30% max
  walk_forward_train_months: 6
  walk_forward_test_months: 2
  min_total_months: 24
  recalibration_interval_months: 3
  stability_threshold: 0.15     # Écart-type / médiane < 0.15

# Gestion dynamique
dynamic_management:
  phase_4_fixed: true
  phase_5_5_partial:
    enabled: true
    tp1_close_pct: 0.50
    breakeven_on_tp1: true
    early_exit_on_decaying: true
  phase_6_trailing:
    enabled: false               # Activé après Phase 6
    premium_only: true           # Score ≥ 80 requis
    trail_on_ltf_swings: true    # Basé sur swings 15m
    trail_buffer_atr: 0.2
    deactivate_below_standard: true  # Désactivé si score < 60

# Sortie sur changement de bias
bias_invalidation:
  close_on_bias_flip: true      # Si bias_composite change de signe
  close_on_llm_defensive: true  # Si LLM passe en mode défensif
```

---

## 6. Plan de validation en 5 étapes

### Étape 1 — Baseline structurelle (Phase 4)

```
Action   : Replay Mode sur 3 mois de données, 5 actifs Phase 1
Config   : SL/TP structurels purs (config/sltp_standards.yaml)
Métriques : Profit factor, win rate, max DD, Sharpe
Sortie   : Rapport baseline → benchmark de référence
```

### Étape 2 — Calibration walk-forward (Phase 6)

```
Action   : Walk-forward 24 mois, fenêtre 6/2 mois
Config   : Grid search ATR multipliers ±30%, 5 actifs × 3 TF × 7 setups
Métrique : Profit factor max sous contrainte win rate ≥ 50%
Sortie   : config/sltp_standards.yaml avec paramètres calibrés
```

### Étape 3 — Validation gestion dynamique (Phase 5.5 → Phase 6)

```
Action   : Replay Mode comparatif : fixed vs partial+breakeven
Config   : SL/TP calibrés + gestion dynamique activée
Métrique : Delta profit factor avec vs sans gestion dynamique
Sortie   : Rapport comparatif → décision go/no-go
```

### Étape 4 — Validation multi-actifs élargie (Phase 6)

```
Action   : Replay Mode sur 8-10 actifs, 6 mois de données
Config   : Paramètres calibrés finaux + gestion dynamique
Métrique : Cohérence inter-actifs, pas de dégradation sur petits altcoins
Sortie   : Validation cross-asset → feu vert Phase 7
```

### Étape 5 — Validation Paper Trading (Phase 7)

```
Action   : 30 jours sur Binance Futures Testnet (5 actifs Phase 1)
Config   : Identique à l'Étape 4, déployé sur VPS
Métrique : Sharpe live ≥ 60% du Sharpe Replay, zéro incident critique
Sortie   : Validation infrastructure → feu vert Phase 8 (capital réel)
```

---

## 7. Tests requis

### 7.1 Tests structurels

```
test_sl_judas_swing_calculation
test_sl_amd_distribution_calculation
test_sl_turtle_soup_by_layer
test_sl_unicorn_model_calculation
test_sl_silver_bullet_calculation
test_sl_sweep_fvg_standard
test_sl_smt_cross_asset
test_tp1_calculation_all_setups
test_tp2_calculation_all_setups
test_sltp_oos_boundary_validation
```

### 7.2 Tests Risk Manager (SL/TP validation)

```
test_sl_below_min_distance_rejected
test_sl_above_max_distance_rejected
test_sl_liquidation_buffer_violated
test_oco_order_sl_rejected_cancels_entry
```

### 7.3 Tests de calibration

```
test_atr_multiplier_within_30pct_range
test_walk_forward_produces_stable_multipliers
test_calibrated_parameters_improve_profit_factor
test_win_rate_constraint_respected
test_recalibration_triggered_after_3_months
```

### 7.4 Tests de gestion dynamique

```
test_partial_close_at_tp1
test_sl_moved_to_breakeven_after_tp1
test_early_exit_on_decaying_signal
test_trailing_sl_activated_premium_only
test_trailing_sl_deactivated_below_standard
test_full_close_on_bias_flip
```

---

## 8. Intégration avec le Replay Mode

Le Replay Mode (`08-replay-mode-spec.md`) est l'outil central de validation SL/TP :

```bash
# Étape 1 : Baseline structurelle
python scripts/replay.py --symbol BTCUSDT --timeframe 1H \
  --start 2026-01-01 --end 2026-04-01 \
  --mode full --config config/sltp_standards.yaml

# Étape 2 : Calibration (grid search ATR)
python scripts/replay_calibrate.py --symbol BTCUSDT --timeframe 1H \
  --start 2025-01-01 --end 2026-04-01 \
  --setup turtle_soup --param sl_buffer_atr \
  --range 0.14 0.26 --metric profit_factor --constraint win_rate:50

# Étape 3 : Comparatif gestion dynamique
python scripts/replay_compare.py --symbol BTCUSDT \
  --start 2026-01-01 --end 2026-04-01 \
  --config_a config/sltp_fixed.yaml \
  --config_b config/sltp_dynamic.yaml
```

---

## Changelog

**v1.0** (2026-05-15)
- [NEW] Table SL/TP exhaustive pour les 7 setups ICT
- [NEW] Méthodologie de calibration walk-forward avec contrainte ±30% ATR
- [NEW] Progression 3 phases : fixe → partiel+breakeven → trailing conditionnel
- [NEW] Fichier centralisé `config/sltp_standards.yaml`
- [NEW] Plan de validation en 5 étapes
- [NEW] Tests structurels, calibration, et gestion dynamique
- [NEW] Intégration explicite avec le Replay Mode

# ICT Trading System — Specification v1.3

> Source unique de vérité pour l'implémentation. Toute modification doit être documentée dans le changelog.

---

## Vue d'ensemble

Ce système implémente une stratégie ICT (Inner Circle Trader) multi-timeframe avec :
- **Détection de patterns** : Liquidity Sweeps, FVG, SMT Divergence, AMD, Silver Bullet, Judas Swing, Turtle Soup
- **Scoring probabiliste** : Score continu par setup type avec pondération, decay exponentiel, et interactions
- **Signal Lifecycle** : 5 états (detected → active → reinforced → decaying → invalidated)
- **Risk Management** : 6 règles en dur, Kill Switch hiérarchique, Kelly cap fractionnel
- **LLM intégré** : Contexte interprétatif uniquement, 35% du bias composite

---

## 1. Hiérarchie des Swings (Multi-Timeframe)

```
Layer       Timeframe    N    Confirmation    Max Age       Rôle
Micro       15m          5    30 min          5h (20 bars)  Inducement, entrée précise
Short-term  1H           5    2h              12h (12 bars) BOS/CHoCH, bias intra-session
External    4H           5    8h              24h (6 bars)  Liquidity pools, targets HTF
```

**Détection** : `high[i] == max(high[i-w : i+w+1])` où w = N//2 = 2.
**Anti-repaint** : swing confirmé seulement après w bougies supplémentaires clôturées.
**Tie-breaking** : plus récent (index max).
**États** : `pending` (LLM read-only) → `confirmed` → `invalidated`.

---

## 2. Kill Zones (UTC, calibrées données réelles crypto)

| KZ | UTC | Locale (Algérie) | Validité | Taille |
|---|---|---|---|---|
| Asian | 01:00-04:00 | 02:00-05:00 | MODERATE | ×0.7 |
| London | 07:00-10:00 | 08:00-11:00 | STRONG | ×1.0 |
| NY AM | 13:00-16:00 | 14:00-17:00 | VERY_STRONG | ×1.15 |
| NY PM | 19:00-21:00 | 20:00-22:00 | WEAK | ×0.5 (sauf confluence) |

**Ajustements crypto** :
- Signal generation SEULEMENT pendant KZ (sauf sorties toujours autorisées)
- Sweep tolerance : 90 min (vs 60 en Forex)
- Volume filter : volume_24h >= median_7j × 0.7
- Weekend : 2× confluence requise, taille -30%, skip funding extrême
- NY PM : désactivée par défaut, réactivée uniquement si confluence FVG+SMT OU AMD confirmé

---

## 3. Key Times (pondération temporelle)

| Heure UTC | Label | Impact | Bonus |
|---|---|---|---|
| 11:00 | Peak liquidity (triple overlap) | Liquidity surge | +15% |
| 13:00 | NY AM Kill Zone open | Volatility spike | +15% |
| 15:00 | Silver Bullet open (10AM NY) | High prob setup | +15% |
| 16:00 | NYSE close | Macro flow | +10% |
| 20:00 | Daily candle reset | Levels react | +10% |

Signaux dans les ±15 min d'un Key Time → bonus de pondération sur le scoring.

---

## 4. BOS / CHoCH (Machine d'état de tendance)

Tracké sur le layer **short-term (1H/N=5)**.

**États** : `UNDEFINED` → `UPTREND` → `DOWNTREND`

**Transitions** :
- UNDEFINED → UPTREND : deux HH consécutifs confirmés
- UNDEFINED → DOWNTREND : deux LL consécutifs confirmés
- UPTREND → UPTREND (BOS) : close > dernier SWING_HIGH 1H
- DOWNTREND → DOWNTREND (BOS) : close < dernier SWING_LOW 1H
- UPTREND → DOWNTREND (CHoCH) : close < dernier SWING_LOW 1H
- DOWNTREND → UPTREND (CHoCH) : close > dernier SWING_HIGH 1H

**Structural bias** : UPTREND → BULLISH (+1.0), DOWNTREND → BEARISH (-1.0), UNDEFINED → RANGE (0.0).
UNDEFINED = pas de trade directionnel autorisé.

---

## 5. AMD (Accumulation - Manipulation - Distribution)

Cycle fondamental ICT détecté sur **1H** via probabilités progressives (pas booléen).

**Phases** :
- **Accumulation** : range 4+ bougies, ATR_range < 0.5 × ATR(14), P_acc += 0.3
- **Manipulation** : sweep d'un bord du range pendant KZ, P_man += 0.4
- **Distribution** : close hors range + FVG dans la direction, P_dist += 0.5

**Decay** : toutes les probabilités × 0.9 par bougie sans événement.
**Trigger trade** : P_dist > 0.65 ET P_man a atteint un pic dans les 3 dernières bougies.
**Confirmed AMD** → size_multiplier ×1.25, stop sur opposite range boundary.

---

## 6. Daily Bias (Composite LLM + Structure + Funding + On-Chain)

> **Canonical weights**: See `config/bias.yaml` (AD-022). The values below are superseded.

```
bias_composite = 0.50 × structural_bias + 0.20 × LLM_bias + 0.15 × on_chain_bias + 0.15 × funding_adjustment
```

- **LLM** : DeepSeek V4 standard, update 60 min, fallback TTL 120 min, defensive_mode après
- **Structural** : dérivé de trend_state (1H) + external_bias (4H)
- **Funding** : extrême > 0.1% consécutif → -0.15, extrême < -0.05% → +0.15, divergence funding-prix

**Divergence handling** :
- Both agree → confidence ×1.0
- LLM only → confidence ×0.7, justification requise
- Structural only → confidence ×0.7
- Opposite → confidence ×0.3, prefer skip (override humain possible)

---

## 7. Fair Value Gap (FVG)

**Détection** : `low[i+1] > high[i-1]` (up) / `high[i+1] < low[i-1]` (down)

**Validité** : taille >= 0.15 × ATR(14). < 0.15 → bruit, ignoré.
**Strong** : >= 0.30 × ATR, durée de vie prolongée (10 barres vs 3 standard).
**Layer classification** : proximité avec swings (±0.5 × ATR), premium si 2+ layers.
**FVG_in_OTE** : overlap / min(fvg_size, ote_size) >= 0.5.

---

## 8. Liquidity Sweep

**Conditions** :
- Intrabar low <= swing_low (long) / high >= swing_high (short)
- Close de l'autre côté du swing
- Swing confirmed (pas pending)
- Si micro layer : direction alignée avec layer supérieur

**Disqualifications** : swing stale, pending, invalidated.

**Sizing par layer ancré** :
- Micro (15m) → ×0.5, candidat unicorn : non
- Short (1H) → ×1.0, candidat unicorn : non
- External (4H) → ×1.5, candidat unicorn : oui

---

## 9. Judas Swing

Sweep spécifique en ouverture de Kill Zone (tolérance 90 min).

**London Judas** (07:00-08:30 UTC) : sweep du range asiatique, aligné biais HTF.
**NY Judas** (13:00-14:30 UTC) : sweep du range London, aligné biais HTF.

Sizing : standard ×1.25, avec AMD ×1.5. Stop au-delà du range sweepé + 0.3 × ATR.

---

## 10. Silver Bullet

Setup temporel : **15:00-16:00 UTC** (10:00-11:00 AM NY).

**Conditions obligatoires** :
- HTF bias (4H) défini, 1H bias aligné
- FVG formé dans la fenêtre Silver Bullet
- FVG direction = direction du biais HTF
- FVG >= 0.10 × ATR (seuil réduit pour fenêtre courte)

**Boosts optionnels** : FVG dans zone correcte, Judas preceding, SMT cross-asset.
**Entry** : premier retest du FVG, timeout 60 min.
**Sizing** : base ×1.0, +0.15 par boost, max ×1.45.

---

## 11. Displacement Leg + OTE

**Displacement** : jambe directionnelle de N bougies consécutives, body_ratio >= 0.5.

| Type | Min Bars | Min Amplitude | Timeframe | Rôle |
|---|---|---|---|---|
| Micro | 3 | 0.3 × ATR | 15m | Scalp |
| Local | 4 | 0.6 × ATR | 1H | Standard |
| Major | 5 | 1.0 × ATR | 4H | Swing |

**OTE** : Fibonacci 61.8% - 79% depuis start → end du displacement.
Sélection : major > local > micro, plus récent, OTE doit chevaucher prix actuel.

---

## 12. SMT Divergence

**Intra-Asset** : Delta divergence (aggTrades) ou Volume divergence (fallback).
Divergence au niveau d'un swing ICT → bonus Unicorn.

**Cross-Asset** : BTC vs ETH/SOL/BNB/DOT au même niveau de swing (±2 bougies).
Corrélation : rolling Pearson 7j, min 0.5, stabilité min 0.6 (sinon 0 pts).

---

## 13. Turtle Soup

Fausse cassure avec rejet et confirmation barre suivante.
Sizing par layer : micro ×0.5, short ×1.0, external ×1.5.
Stop buffer ATR : 0.2 / 0.4 / 0.7 selon layer.

---

## 14. Trading Range & Premium/Discount

**Source** : swings external (4H/N=5).
**Zones** : discount [0, 0.305), equilibrium [0.305, 0.705), premium [0.705, 1].
**Entry rule** : bullish → discount only, bearish → premium only, range → no directional.
**Invalidation** : swing 4H confirmé + 2 closes hors range.

---

## 15. Unicorn Model

Setup de confluence maximale. **5 conditions obligatoires + 3 bonus**.

**Mandatory** :
1. LLM + structural bias alignés
2. Kill Zone active
3. Sweep anchored to external (4H) swing
4. Price in correct zone (LONG → discount, SHORT → premium)
5. OTE overlaps FVG (overlap ≥ 50%)

**Bonus** : FVG premium (+0.10), displacement major (+0.10), SMT cross-asset (+0.10).
**Sizing** : base ×1.5, max ×1.8. Stop sur swing external + 0.7 × ATR.

---

## 16. Signal Lifecycle Engine

5 états :

```
DETECTED → ACTIVE → REINFORCED → DECAYING → INVALIDATED
```

- **DETECTED** : Pattern identifié, score initial = somme des poids. Non tradable.
- **ACTIVE** : Score >= minimal_threshold, tradable. Decay actif.
- **REINFORCED** : Interaction rule déclenchée → bonus score + decay timer reset.
- **DECAYING** : Score en baisse mais encore >= invalidation (40).
- **INVALIDATED** : Score < 40 OU prix a consommé le signal. Retiré du pool.

**Seuil d'invalidation** : 40 (unique, tous types de signaux).

---

## 17. Signal Interactions

Règles de réactivation entre signaux (±0.3 × ATR de tolérance) :

| Interaction | Effet |
|---|---|
| Sweep + FVG | Sweep : +15pts, decay reset. FVG inchangé. |
| SMT + Sweep | Sweep : decay rate ×0.5. SMT : +10pts. |
| AMD + Bias | Tous signaux dans le range : lifetime ×2. |
| FVG consumé | FVG → INVALIDATED (traversé par le prix). |
| Sweep invalidé | Prix traverse le swing en sens opposé → INVALIDATED. |

---

## 18. Signal Scoring + Decay

Remplace `trade_intent.tiers` (AND-stack). **Calibré pour expectancy max.**

### Scoring Grids

| Setup | Poids clés | Max | Minimal | Standard | Premium |
|---|---|---|---|---|---|
| Liquidity Sweep | external:35, bias:20, KZ:10, FVG:10, SMT:10, delta:5 | 100 | 45 | 60 | 80 |
| Silver Bullet | FVG:30, bias:25, zone:20, judas:15, SMT:10 | 100 | - | 50 | 70 |
| AMD Distribution | amd:40, bias:25, sweep:20, FVG:15 | 100 | - | 55 | 75 |
| Turtle Soup | external:35, bias:20, KZ:15, FVG:15 | 100 | - | 55 | 75 |
| Judas Swing | judas:35, bias:25, amd:20, FVG:20 | 100 | - | 55 | 80 |
| SMT Cross-Asset | smt:35, setup:30, bias:20, KZ:15 | 100 | - | 50 | 70 |

### Decay

```
score_decayed = score_initial × exp(-rate × bars_since_detection)
```

| Signal | Decay Rate |
|---|---|
| Sweep | 0.20 |
| FVG | 0.15 |
| SMT | 0.25 |
| AMD | 0.10 |
| Delta | 0.20 |

### Tier Assignment

| Score | Tier | Size Multiplier |
|---|---|---|
| < 45 | NO_TRADE | - |
| 45-59 | MINIMAL | ×0.5 |
| 60-79 | STANDARD | ×1.0 |
| >= 80 | PREMIUM | ×1.25-1.80 |

---

## 19. Global Market State

État unifié du marché, mis à jour `on_each_bar_close`. Tous les détecteurs **lisent**, aucun ne **recalcule**.

| Composant | Source | Refresh | Champs |
|---|---|---|---|
| **Trend** | trend_state (section 6) | on 1H close | state, bias_label, bias_score, last_choch |
| **Session** | kill_zones + crypto_adaptations | on each bar | active_kz, key_time_prox, is_weekend, vol_ratio |
| **Volatility** | OHLCV calc | on 1H close | atr_pct_1H/4H, regime, vol_vs_avg_7d |
| **Liquidity** | swings + AMD | on each bar | phase, range_boundaries, nearest_swings, freshness |

---

## 20. Kelly Fractional Sizing

**Formule** : `Kelly% = W - ((1-W) / R)` où W = win rate, R = avg_win / avg_loss.

**Fraction utilisée** : 1/4 Kelly (ultra-conservateur).
**Cap** : `max_risk_per_trade = min(ICT_size, kelly_cap)`.
**Si Kelly <= 0** : pas de trade (espérance négative).
**Recalcul** : tous les 50 trades (min 30 pour validité).
**Cold-start** (AD-026) : tant que `n_trades < 30`, pas de cap Kelly — le risque par trade est fixé à `max_risk_per_trade_pct` (0.25%).
**Per-setup auto-disable** : Kelly <= 0 pendant 50 trades → setup désactivé.
**Ré-activation** (AD-026) : un setup désactivé peut être ré-armé après shadow-trading sur N trades avec expectancy > 0 sur fenêtre OOS. Aucun setup n'est désactivé définitivement sans chemin de retour.

---

## 21. Stop Loss & Take Profit par Setup

> Spécification complète : [09-sltp-optimization.md](09-sltp-optimization.md)

| Setup | SL | TP1 (50% close) | TP2 (runner) |
|-------|----|-----------------|--------------|
| **Judas Swing** | Au-delà du range sweepé + `0.3 × ATR` | Boundary opposée du range | External swing opposé (4H) + FVG |
| **AMD Distribution** | Boundary opposée du range | FVG adjacent | Prochain niveau de liquidité (swing 4H) |
| **Turtle Soup** | Buffer ATR : 0.2 / 0.4 / 0.7 (micro/short/external) | Zone de manipulation opposée | External swing opposé |
| **Unicorn Model** | Swing external + `0.7 × ATR` | FVG premium + OTE overlap | Liquidité adverse opposée |
| **Silver Bullet** | Swing opposé le plus proche + `0.3 × ATR` | FVG dans la fenêtre 15:00-16:00 | External swing opposé (4H) |
| **Sweep / FVG Standard** | Au-delà du swing/FVG de référence + `0.2 × ATR` | FVG adjacent ou OTE | External swing opposé ou equal highs/lows |
| **SMT Cross-Asset** | Au-delà du swing de divergence + `0.2 × ATR` | FVG adjacent | External swing opposé (4H) |

**Gestion dynamique** :
- TP1 atteint → close 50% position + SL → breakeven
- Signal DECAYING (score < 45) → sortie anticipée
- Signal INVALIDATED (score < 40) → sortie immédiate
- Score PREMIUM (≥ 80) → trailing SL conditionnel sur swings LTF

**Validation Risk Manager** (règle 2) :
- distance(entry, SL) ∈ [0.1%, 20%] du prix
- distance(entry, SL) ≥ 2 × distance(entry, liquidation)
- OCO atomique — impossible sur Binance Futures, remplacé par transaction compensatoire (voir AD-023).

---

## 22. ATR Multipliers Calibration

Calibration statistique walk-forward des buffers ATR, plafonnée ±30% du standard ICT.

| Paramètre | Valeur |
|-----------|--------|
| Méthode | Walk-forward 6 mois train / 2 mois test |
| Plage | ±30% du standard ICT |
| Métrique | Profit factor max sous contrainte win rate ≥ 50% |
| Granularité | Par setup, timeframe, et actif |
| Recalibration | Tous les 3 mois minimum |
| Stabilité | Écart-type / médiane < 0.15 |

Fichier source unique : `config/sltp_standards.yaml`

---

## 23. Risk Manager (6 règles)

Les règles sont codées en dur. Modification = commit git + redéploiement.

1. **Max risk per trade** : 0.25% du capital (ultra-conservateur)
2. **Stop-loss obligatoire** : défini avant l'ordre, OCO (validé par §21)
3. **Levier dynamique** : selon régime (TREND: 3x, RANGE: 2x, CRISIS: 1x)
4. **Exposition max** : totale 200%, corrélée 100% du capital
5. **Drawdown en escalier** : -2% réduit taille, -3% halt 4h, -5% close all 24h, -8% semaine EMERGENCY
6. **Margin ratio** : warning 50%, force reduce 70%

---

## 24. LLM Analyst

- **Provider** : DeepSeek V4 standard
- **Fréquence** : 1 appel / heure
- **Fallback** : dernier contexte valide réutilisé max 2h
- **Après TTL** : defensive_mode (pas de nouveaux trades)
- **Rôle** : contexte interprétatif UNIQUEMENT. Poids exact défini dans `config/bias.yaml` (AD-022).
- **Ne déclenche jamais un trade** directement.
- **Données envoyées** : OHLCV multi-TF, swings détectés (pending inclus), FVG, funding, volumes, news titres, données on-chain

---

## 23. Actifs (Phase 1)

BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, DOT/USDT.

---

## Changelog

**v1.3** (2026-05-15)
- [BREAKING] AND-stack → Scoring pondéré par setup type
- [NEW] Signal Lifecycle Engine (5 états)
- [NEW] Signal Interactions (réactivation sweep+FVG, SMT+sweep, AMD+bias)
- [NEW] Global Market State (unifié)
- [NEW] Scoring Grids par setup type (6 grilles)
- [NEW] Seuils calibrés pour expectancy max (45/60/80)
- [NEW] SL/TP par setup (§21) — table exhaustive 7 setups + gestion dynamique
- [NEW] ATR Multipliers Calibration (§22) — walk-forward ±30%
- [FIX] Kill Zones calibrées données réelles crypto (UTC)
- [FIX] Silver Bullet et Judas Swing corrigés en UTC
- [FIX] SMT corrélation : Pearson rolling 7j + stabilité
- [FIX] AMD : probabiliste (P_acc/man/dist), pas booléen
- [UPD] Weekend mode, volume filter, sweep tolerance 90min
- [UPD] LLM intégré dans bias_composite via scoring
- [UPD] Kelly confirmé comme cap hiérarchique
- [UPD] LLM bias composite : 35% → 20% macro (15% on-chain séparé)

**v1.2** (2026-05-15)
- [NEW] AMD, SMT Intra/Cross, Judas Swing, Silver Bullet
- [NEW] Kelly Fractional Sizing, Funding Rate enrichi
- [NEW] Key Times, bias composite (50/35/15)

**v1.1** (2026-05-15)
- [BREAKING] single-TF → multi-TF (15m/N=5, 1H/N=5, 4H/N=5)
- [BREAKING] Liquidity tagging → sweep_anchored_to
- [NEW] BOS/CHoCH machine d'état, swing freshness
- [FIX] Zones half-open, FVG_in_OTE, pending swings

**v1.0** (2026-05-15)
- Version initiale, base Phase 1

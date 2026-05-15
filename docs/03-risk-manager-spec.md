# Risk Manager — Spécification

> Module critique n°1 du système. Codé en premier, testé unitairement avant tout le reste.
> 6 règles codées en dur. Modification = commit git + redéploiement.

---

## Architecture

```
TradeIntent (Strategy Engine)
    ↓
┌───────────────────────────────────────────────┐
│              RISK MANAGER                     │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │ 1. Pre-Trade Checks (6 règles)          │ │
│  │    └─ règle 1: max_risk_per_trade       │ │
│  │    └─ règle 2: mandatory_stop_loss      │ │
│  │    └─ règle 3: max_leverage_by_regime   │ │
│  │    └─ règle 4: max_exposure             │ │
│  │    └─ règle 5: drawdown_check           │ │
│  │    └─ règle 6: margin_ratio             │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │ 2. Position Sizing                      │ │
│  │    size = (capital × risk%) / distance   │ │
│  │    + Kelly cap                          │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │ 3. Kill Switch                          │ │
│  │    NORMAL / REDUCED_SIZE / HALT /       │ │
│  │    CLOSE_ALL / EMERGENCY                │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │ 4. Reconciliation                       │ │
│  │    État local vs état Binance           │ │
│  └─────────────────────────────────────────┘ │
└───────────────────────────────┬───────────────┘
                                ↓
                    RiskAssessment (APPROVED/REJECTED/REDUCED)
                                ↓
                    Execution Engine (CCXT → Binance)
```

---

## Types fondamentaux

```python
class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE_LOW_VOL = "RANGE_LOW_VOL"
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"

class KillSwitchLevel(str, Enum):
    NORMAL = "NORMAL"            # Fonctionnement normal
    REDUCED_SIZE = "REDUCED"     # -2% daily : taille /2
    HALT_NEW_TRADES = "HALT"     # -3% daily : pas de nouveau trade
    CLOSE_ALL = "CLOSE_ALL"      # -5% daily : tout fermer, 24h cooldown
    EMERGENCY = "EMERGENCY"      # -8% weekly : arrêt total, humain requis
```

---

## Règle 1 : Max Risk Per Trade

**Principe** : Le risque est calculé AVANT l'entrée. On part du capital qu'on accepte de perdre, pas du capital disponible.

```
risk_amount = capital × max_risk_per_trade_pct
size = risk_amount / abs(entry_price - stop_loss)
```

**Valeur** : `max_risk_per_trade_pct = 0.0025` (0.25% ultra-conservateur)

**Check** : `sizing.risk_amount <= account.total_balance × 0.0025`

---

## Règle 2 : Mandatory Stop-Loss

- Stop-loss défini avant l'ordre (pas d'exception)
- Distance entry-stop > 0.1% du prix (stop trop proche = stop-out sur slippage)
- Distance entry-stop < 20% du prix (stop trop loin = stratégie suspecte)
- Ordre envoyé en OCO (entry + stop atomiques)
- Si Binance refuse le stop → l'ordre d'entrée est annulé

---

## Règle 3 : Levier Dynamique par Régime

| Régime | Levier max |
|---|---|
| TREND_UP | 3x |
| TREND_DOWN | 3x |
| RANGE_LOW_VOL | 2x |
| RANGE_HIGH_VOL | 2x |
| CRISIS | 1x |
| UNKNOWN | 1x |

**Note** : Le levier est la CONSÉQUENCE du sizing, pas son point de départ.

---

## Règle 4 : Exposition Max

**Exposition totale** : `total_notional / total_balance <= 2.0` (200% max)
**Exposition corrélée** : Positions sur actifs du même groupe <= 100% du capital.

**Groupes de corrélation** (fallback statique, Phase 2 → rolling) :
- `btc_cluster` : BTC, ETH, BNB (corr ~0.85)
- `alt_l1` : SOL, AVAX, ADA, DOT, NEAR
- `meme` : DOGE, SHIB, PEPE
- `defi` : UNI, AAVE, MKR, CRV

**Règle** : Même direction sur même groupe → exposition cumulée. Direction opposée → compensation partielle.

---

## Règle 5 : Drawdown en Escalier

| Seuil | Action | Cooldown |
|---|---|---|
| Daily -2% | REDUCED_SIZE (taille /2) | - |
| Daily -3% | HALT_NEW_TRADES | 4h |
| Daily -5% | CLOSE_ALL | 24h |
| Weekly -8% | EMERGENCY | Manuel |

**Escalade seulement** : le niveau peut monter automatiquement, descendre uniquement via cooldown ou intervention humaine.

---

## Règle 6 : Margin Ratio

```
margin_ratio = used_margin / total_balance
```

| Seuil | Action |
|---|---|
| > 50% | WARNING (pas de nouveaux trades) |
| > 70% | FORCE_REDUCE (fermeture partielle des positions) |

---

## Kill Switch

Niveaux hiérarchiques (ordre croissant) :
1. NORMAL → fonctionnement standard
2. REDUCED_SIZE → nouveaux trades avec size_multiplier ×0.5
3. HALT_NEW_TRADES → pas de nouvelles entrées, sorties autorisées
4. CLOSE_ALL → toutes les positions fermées, halt 24h
5. EMERGENCY → arrêt total, reprise MANUELLE uniquement

**Règles de transition** :
- Tout composant peut MONTER le niveau
- EMERGENCY → reset MANUEL obligatoire
- Niveaux inférieurs → auto-recovery après cooldown
- Persisté en Postgres + Redis pour survie au redémarrage

---

## Position Sizing

```
Formule fondamentale (unique) :
    risk_amount = capital × max_risk_per_trade_pct × size_multiplier
    size = risk_amount / risk_per_unit
    notional = size × entry_price
    required_margin = notional / actual_leverage
```

**Filtres Binance** appliqués APRÈS le calcul :
- Arrondi au stepSize (lot size)
- Vérification minNotional
- Vérification minQty
- Rejet si la taille filtrée est 0

**Kelly Cap** :
```
kelly_risk_pct = (W - (1-W)/R) × 0.25  # 1/4 Kelly
max_risk = total_balance × kelly_risk_pct
final_risk = min(ict_calculated_risk, kelly_max_risk)
```

---

## Binance Filters

| Filtre | Application |
|---|---|
| `stepSize` | Arrondi DOWN de la quantité |
| `minQty` | Rejet si quantité < minQty |
| `minNotional` | Rejet si quantity × price < minNotional |
| `tickSize` | Arrondi du prix stop/limit |
| `pricePrecision` | Arrondi du prix d'entrée |

Récupérés via `exchange.load_markets()` au démarrage, recheckés après maintenance.

---

## Liquidation Distance Check

```
Pour une position isolated :
    liq_price_long = entry_price × (1 - 1/leverage + maintenance_margin)
    liq_short = entry_price × (1 + 1/leverage - maintenance_margin)
    
    Vérification : distance(stop_loss, liq_price) >= min_stop_to_liq × distance(entry, liq_price)
```

`min_stop_to_liq_ratio = 2.0` → le stop doit être au moins 2× plus proche du prix d'entrée que la liquidation. Protège contre les cascades de liquidation.

---

## Configuration

```yaml
risk_config:
  # Règle 1
  max_risk_per_trade_pct: 0.0025        # 0.25%
  
  # Règle 3
  max_leverage_by_regime:
    TREND_UP: 3
    TREND_DOWN: 3
    RANGE_LOW_VOL: 2
    RANGE_HIGH_VOL: 2
    CRISIS: 1
    UNKNOWN: 1
  
  # Règle 4
  max_total_exposure_pct: 2.0           # 200%
  max_correlated_exposure_pct: 1.0      # 100%
  
  # Règle 5
  daily_dd_reduce_size: 0.02            # -2%
  daily_dd_halt: 0.03                   # -3%
  daily_dd_close_all: 0.05              # -5%
  weekly_dd_emergency: 0.08             # -8%
  halt_cooldown_hours: 4
  close_all_cooldown_hours: 24
  
  # Règle 6
  margin_ratio_warning: 0.50            # 50%
  margin_ratio_force_reduce: 0.70       # 70%
  
  # Liquidation
  min_stop_to_liquidation_ratio: 2.0
```

---

## Module responsable de la persistence

- **Postgres** : état des positions, ordres, capital_snapshots (source de vérité)
- **Redis** : Kill Switch state (accès rapide entre containers)
- **Postgres** : signals_log, risk_events (journal analytique asynchrone)

---

## Tests requis (minimum)

1. Test que 3 pertes consécutives à -0.25% déclenchent REDUCED_SIZE
2. Test qu'un flash crash simulé déclenche CLOSE_ALL
3. Test que le Kill Switch survit à un redémarrage (restore depuis Postgres)
4. Test que 2 positions BTC+ETH sont comptées comme corrélées (exposition consolidée)
5. Test qu'un ordre sans stop-loss est rejeté avant toute règle
6. Test que le levier dynamique est respecté par régime
7. Test que margin_ratio > 70% force la réduction
8. Test que Kelly cap limite la taille même si ICT veut plus
9. Test que les filtres Binance (stepSize, minNotional) sont appliqués
10. Test que la divergence état local/Binance déclenche EMERGENCY

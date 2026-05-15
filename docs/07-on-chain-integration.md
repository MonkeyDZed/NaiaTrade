# On-Chain Integration — Spécification v1.0

> Module d'enrichissement du biais composite via données on-chain.
> Le LLM produit une phrase factuelle, un module déterministe la convertit en deltas numériques.
> Poids du module dans le composite : 15%.

---

## Vue d'ensemble

Ce module ajoute une couche d'intelligence on-chain au système NaiaTrade :

- **3 sources de données** : Exchange Netflow, Stablecoin Supply, Cumulative Delta
- **Pipeline en 3 étapes** : Collecte → LLM (phrase factuelle) → Post-Processing (deltas numériques)
- **Déterministe après le LLM** : le parsing de la phrase est basé sur des règles explicites
- **Rôle** : 15% du bias composite. Le LLM macro/ICT garde 20%.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  ON-CHAIN DATA COLLECTOR                     │
│                                                             │
│  Glassnode API ──► Exchange Netflow (BTC,ETH,SOL,BNB,DOT)   │
│  DefiLlama API ──► Stablecoin Supply (USDT + USDC)          │
│  Binance API   ──► Cumulative Delta (aggTrades)             │
│                                                             │
│  Fréquence : 1h (H+5min pour laisser les APIs se mettre     │
│             à jour après la clôture horaire)                │
└──────────────────────────┬──────────────────────────────────┘
                           │ JSON structuré
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM ANALYST                             │
│                                                             │
│  Reçoit : JSON on-chain par actif + contexte global         │
│  Produit : UNE phrase factuelle par actif                   │
│  Rôle : Interpréter les données, pas décider                │
└──────────────────────────┬──────────────────────────────────┘
                           │ Phrase factuelle (string)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  POST-PROCESSING MODULE                      │
│                                                             │
│  Parse la phrase → détecte les motifs → deltas numériques   │
│  Sortie : on_chain_bias par actif (float [-0.15, +0.15])   │
│  Complètement déterministe, backtestable                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ on_chain_bias
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    BIAS COMPOSITE                             │
│                                                             │
│  bias = 0.50 × structural + 0.20 × LLM_macro                │
│       + 0.15 × on_chain + 0.15 × funding                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Sources de données

### 2.1 Exchange Netflow (Glassnode / CryptoQuant)

| Champ | Description | Source |
|-------|-------------|--------|
| `netflow_24h` | Volume net entrées - sorties sur 24h (BTC) | Glassnode free tier |
| `netflow_7d` | Volume net sur 7 jours | Glassnode |
| `exchange_balance` | Balance totale sur les exchanges | Glassnode / CryptoQuant |

**Interprétation standard** :
- `netflow_24h < 0` (sorties) → accumulation potentielle → signal haussier
- `netflow_24h > 0` (entrées) → pression vendeuse → signal baissier
- `exchange_balance` en baisse continue → tendance d'accumulation structurelle

**Disponibilité** : API gratuite, mise à jour horaire. 2-3 ans d'historique.

### 2.2 Stablecoin Supply (DefiLlama / Glassnode)

| Champ | Description | Source |
|-------|-------------|--------|
| `usdt_supply` | Offre totale USDT en circulation | DefiLlama |
| `usdc_supply` | Offre totale USDC en circulation | DefiLlama |
| `usdt_delta_24h` | Variation USDT sur 24h | Calculé (supply_now - supply_24h_ago) |
| `usdc_delta_24h` | Variation USDC sur 24h | Calculé |
| `stablecoin_total_delta_24h` | Variation combinée USDT+USDC (USD) | Calculé |

**Interprétation standard** :
- `stablecoin_total_delta_24h > +500M` → capital frais entrant → haussier
- `stablecoin_total_delta_24h < -200M` → fuite de capital → baissier
- Croissance soutenue sur 7j → tendance d'accumulation macro

**Segmentation par émetteur** : USDT et USDC sont suivis séparément pour éviter les faux signaux dus à l'arrivée de nouveaux stablecoins (BUIDL, PYUSD, etc.).

**Disponibilité** : API gratuite, mise à jour horaire. 2+ ans d'historique.

### 2.3 Cumulative Delta (Binance aggTrades)

| Champ | Description | Source |
|-------|-------------|--------|
| `cumulative_delta` | Somme des deltas (buy - sell volume) sur la période | Binance aggTrades |
| `delta_divergence` | Divergence prix/delta (prix baisse, delta monte = haussier) | Calculé |
| `delta_trend` | Tendance du delta sur les N dernières bougies | Calculé |

**Interprétation standard** :
- Prix fait un Lower Low, delta fait un Higher Low → divergence haussière → accumulation
- Prix fait un Higher High, delta fait un Lower High → divergence baissière → distribution
- `delta_trend = "rising"` et prix stable → absorption, signal haussier

**Calcul** : via `isBuyerMaker` dans les aggTrades Binance.
```
delta = sum(volume if isBuyerMaker == False else -volume)
```

**Disponibilité** : Gratuit via Binance API. Historique téléchargeable, fréquence de trade.

---

## 3. Collecte et stockage

### 3.1 Table Postgres

```sql
CREATE TABLE on_chain_snapshots (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    
    -- Netflow
    netflow_24h DECIMAL(18,2),
    netflow_7d DECIMAL(18,2),
    exchange_balance DECIMAL(18,2),
    
    -- Stablecoins (global, stocké une fois par snapshot, symbole = 'GLOBAL')
    usdt_supply DECIMAL(18,2),
    usdc_supply DECIMAL(18,2),
    usdt_delta_24h DECIMAL(18,2),
    usdc_delta_24h DECIMAL(18,2),
    stablecoin_total_delta_24h DECIMAL(18,2),
    
    -- Cumulative Delta
    cumulative_delta DECIMAL(18,2),
    delta_divergence VARCHAR(20),    -- 'bullish', 'bearish', 'none'
    delta_trend VARCHAR(20),         -- 'rising', 'falling', 'flat'
    
    -- Métadonnées
    source_netflow VARCHAR(50) DEFAULT 'glassnode',
    source_stablecoin VARCHAR(50) DEFAULT 'defillama',
    source_delta VARCHAR(50) DEFAULT 'binance_aggtrades',
    is_valid BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX idx_onchain_ts ON on_chain_snapshots(timestamp DESC);
CREATE INDEX idx_onchain_symbol_ts ON on_chain_snapshots(symbol, timestamp DESC);
```

### 3.2 Table bias on-chain

```sql
CREATE TABLE on_chain_bias_history (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    
    -- Phrase LLM brute
    llm_raw_response TEXT,
    
    -- Deltas calculés par le post-processor
    delta_netflow DECIMAL(3,2) DEFAULT 0,
    delta_stablecoin DECIMAL(3,2) DEFAULT 0,
    delta_cumulative DECIMAL(3,2) DEFAULT 0,
    delta_total DECIMAL(3,2) DEFAULT 0,
    
    -- Contrôle
    is_fallback BOOLEAN DEFAULT FALSE,
    parser_version VARCHAR(10),
    error_message TEXT
);

CREATE INDEX idx_onchain_bias_ts ON on_chain_bias_history(timestamp DESC);
CREATE INDEX idx_onchain_bias_symbol_ts ON on_chain_bias_history(symbol, timestamp DESC);
```

---

## 4. Format JSON envoyé au LLM (contexte on-chain)

Chaque heure, pour chaque actif, le contexte on-chain est envoyé au LLM :

```json
{
  "analysis_type": "on_chain",
  "symbol": "BTCUSDT",
  "timestamp": "2026-05-15T14:05:00Z",
  
  "on_chain_data": {
    "netflow": {
      "netflow_24h_btc": -3200,
      "netflow_7d_btc": -12000,
      "exchange_balance_btc": 2280000,
      "exchange_balance_7d_change_pct": -0.8,
      "interpretation_hint": "netflow_24h < 0 = accumulation potentielle"
    },
    
    "stablecoins": {
      "usdt_supply": 145000000000,
      "usdc_supply": 58000000000,
      "usdt_delta_24h": 800000000,
      "usdc_delta_24h": 200000000,
      "stablecoin_total_delta_24h": 1000000000,
      "interpretation_hint": "delta > +500M = capital frais entrant"
    },
    
    "cumulative_delta": {
      "delta_1h": 145.5,
      "delta_4h": -320.0,
      "delta_24h": 1250.0,
      "delta_divergence": "bullish",
      "delta_trend": "rising",
      "interpretation_hint": "divergence bullish = accumulation, bearish = distribution"
    }
  },
  
  "price_context": {
    "price_current": 67450.00,
    "price_change_24h_pct": 2.3,
    "trend_state_1H": "UPTREND"
  }
}
```

---

## 5. Prompt LLM (analyse on-chain)

### 5.1 Prompt système

```
Tu es NaiaTrade On-Chain Analyst, un analyste spécialisé dans l'interprétation 
des données on-chain pour les marchés crypto.

TON RÔLE :
Lire les données on-chain fournies et produire UNE phrase factuelle décrivant 
l'état d'accumulation/distribution pour l'actif concerné.

RÈGLES ABSOLUES :
1. Tu ne commentes QUE les données présentes dans le JSON fourni.
2. Tu n'inventes JAMAIS de données, tendances ou événements externes.
3. Tu ne formules JAMAIS de recommandation d'achat, de vente, ou de trade.
4. Ta sortie est UNE SEULE phrase, en anglais, factuelle et concise.
5. Si les données sont insuffisantes ou contradictoires, tu le dis explicitement.
6. Tu cites les valeurs numériques clés dans ta phrase.

INTERPRÉTATION ATTENDUE :
- Netflow négatif (sorties) = accumulation potentielle
- Netflow positif (entrées) = pression vendeuse potentielle
- Minting stablecoin élevé (>500M/24h) = capital frais entrant
- Delta divergence haussière = accumulation, baissière = distribution
- Si plusieurs signaux vont dans le même sens = confluence
- Si signaux contradictoires = neutre
```

### 5.2 Prompt utilisateur (exemple)

```
Analyse les données on-chain suivantes pour BTCUSDT et produis une phrase factuelle :

{JSON_DATA}
```

### 5.3 Exemple de réponse attendue

```
Netflow shows -3200 BTC leaving exchanges (accumulation signal), 
USDT supply increased by +800M (fresh capital entering), 
cumulative delta divergence is bullish with delta trending up — 
three bullish confluence signals for BTC.
```

---

## 6. Module de Post-Processing (déterministe)

### 6.1 Règles de parsing

Le module parse la phrase LLM et applique les règles suivantes dans l'ordre :

```python
DELTA_RULES = [
    # Netflow
    {
        "keywords": ["netflow.*negative", "outflow", "leaving exchange", 
                     "sorties", "salidas", "withdraw"],
        "keywords_exclude": ["inflow", "entering exchange", "deposit"],
        "delta": +0.10,
        "source": "netflow"
    },
    {
        "keywords": ["netflow.*positive", "inflow", "entering exchange",
                     "entrées", "deposit"],
        "keywords_exclude": ["outflow", "leaving exchange"],
        "delta": -0.10,
        "source": "netflow"
    },
    
    # Stablecoin
    {
        "keywords": ["stablecoin.*increas", "USDT.*increas", "USDC.*increas",
                     "mint", "fresh capital", "supply.*up"],
        "keywords_exclude": ["decreas", "supply.*down", "burn"],
        "delta": +0.05,
        "source": "stablecoin"
    },
    {
        "keywords": ["stablecoin.*decreas", "USDT.*decreas", "USDC.*decreas",
                     "burn", "supply.*down"],
        "keywords_exclude": ["increas", "mint"],
        "delta": -0.05,
        "source": "stablecoin"
    },
    
    # Cumulative Delta
    {
        "keywords": ["delta.*bullish", "bullish.*delta", "delta divergence.*bullish",
                     "absorption", "delta.*rising", "accumulation.*delta"],
        "keywords_exclude": ["bearish.*delta", "delta.*bearish", "distribution"],
        "delta": +0.05,
        "source": "cumulative_delta"
    },
    {
        "keywords": ["delta.*bearish", "bearish.*delta", "delta divergence.*bearish",
                     "distribution.*delta", "delta.*falling"],
        "keywords_exclude": ["bullish.*delta", "absorption"],
        "delta": -0.05,
        "source": "cumulative_delta"
    },
    
    # Neutre / Insuffisant / Contradictoire
    {
        "keywords": ["insufficient", "contradictory", "neutral", "no clear signal",
                     "mixed", "unclear", "pas de signal", "contradictoires"],
        "delta": 0.00,
        "source": "neutral"
    }
]
```

### 6.2 Algorithme de calcul

```
Pour chaque règle dans DELTA_RULES (dans l'ordre) :
    1. Vérifier si un keyword est présent dans la phrase (regex, case-insensitive)
    2. Vérifier qu'aucun keyword_exclude n'est présent
    3. Si match → accumuler le delta
    4. Un seul delta par source (netflow / stablecoin / cumulative_delta)
       Le premier match par source l'emporte.

delta_total = sum(all matched deltas)
delta_total = clamp(delta_total, -0.15, +0.15)
```

### 6.3 Table des deltas

| Source | Signal | Delta |
|--------|--------|-------|
| Netflow | Sorties (outflow) détectées | +0.10 |
| Netflow | Entrées (inflow) détectées | -0.10 |
| Netflow | Non mentionné / neutre | 0.00 |
| Stablecoin | Minting / hausse supply | +0.05 |
| Stablecoin | Burn / baisse supply | -0.05 |
| Stablecoin | Non mentionné / neutre | 0.00 |
| Cumulative Delta | Divergence haussière | +0.05 |
| Cumulative Delta | Divergence baissière | -0.05 |
| Cumulative Delta | Non mentionné / neutre | 0.00 |
| Global | Insuffisant / contradictoire | 0.00 |

**Max total** : ±0.15 (plafonné)
**Confluence max** : les 3 sources alignées = ±0.15

### 6.4 Gestion des erreurs

| Scénario | Comportement |
|----------|-------------|
| Phrase LLM vide ou None | delta_total = 0.00, is_fallback = TRUE |
| Aucun keyword matché | delta_total = 0.00 (neutre) |
| Phrase trop courte (< 10 caractères) | delta_total = 0.00, loggué comme "response_too_short" |
| Phrase contient "error", "fail", "timeout" | delta_total = 0.00, is_fallback = TRUE |
| Parsing qui donnerait > ±0.15 | Clampé à ±0.15 |
| Delta netflow +0.10 et delta cumulative +0.05 | +0.15 (cumulatif OK) |

---

## 7. Nouveau bias composite

```
bias_composite = 0.50 × structural_bias
               + 0.20 × LLM_macro_bias
               + 0.15 × on_chain_bias
               + 0.15 × funding_adjustment
```

**Changement par rapport à v1.3** : le poids LLM passe de 35% à 20% + 15% on-chain.

### 7.1 Divergence handling (mis à jour)

| Situation | Comportement |
|-----------|-------------|
| Structural + LLM + On-Chain alignés | confidence ×1.0 |
| On-Chain seul (structural neutre, LLM neutre) | confidence ×0.6, half size |
| On-Chain opposé au structural | confidence ×0.7, prefer structural |
| On-Chain + LLM alignés, structural opposé | confidence ×0.5, skip recommandé |
| On-Chain en fallback/erreur | son poids (15%) redistribué : structural +0.08, LLM +0.05, funding +0.02 |

---

## 8. Gestion des défaillances

### 8.1 Timeout et retry

| Scénario | Action |
|----------|--------|
| API Glassnode timeout (>5s) | Retry 1× après 3s. Échec → utiliser dernière valeur valide (cache 2h) |
| API DefiLlama timeout (>5s) | Retry 1× après 3s. Échec → cache 2h |
| Binance aggTrades indisponible | Delta = 0 pour cette source uniquement |
| Toutes les APIs down | Passer en dégradé complet → on_chain_bias = 0 |
| LLM timeout (>30s) | Retry 1×. Échec → cache dernier biais on-chain valide (2h) |
| Cache expiré (>2h) | on_chain_bias = 0, redistribution des poids |

### 8.2 Cache Redis

```python
# Clés Redis
onchain:snapshot:{symbol}          # Dernier snapshot on-chain valide
onchain:bias:{symbol}              # Dernier biais on-chain calculé
onchain:last_valid_ts:{symbol}     # Timestamp du dernier snapshot valide
```

Durée de validité du cache : **2 heures** (TTL = 7200s).

---

## 9. Intégration avec les modules existants

### 9.1 Data Flow mis à jour

```
[Glassnode] [DefiLlama] [Binance aggTrades]
     │            │              │
     └────────────┼──────────────┘
                  ▼
     ┌─────────────────────────┐
     │  On-Chain Collector     │  ← NOUVEAU (core/onchain/collector.py)
     │  Fréquence : 1h         │
     └───────────┬─────────────┘
                 │ JSON on-chain
                 ▼
     ┌─────────────────────────┐
     │  LLM Analyst            │  ← EXISTANT (modifié)
     │  + prompt on-chain      │
     └───────────┬─────────────┘
                 │ Phrase factuelle
                 ▼
     ┌─────────────────────────┐
     │  Post-Processing Module │  ← NOUVEAU (core/onchain/post_processor.py)
     │  Deltas déterministes   │
     └───────────┬─────────────┘
                 │ on_chain_bias (float)
                 ▼
     ┌─────────────────────────┐
     │  Bias Composite         │  ← EXISTANT (modifié : 50/20/15/15)
     │  Strategy Engine        │
     └─────────────────────────┘
```

### 9.2 Modules modifiés

| Fichier | Modification |
|---------|-------------|
| `core/strategy/bias_composite.py` | Nouvelle formule 50/20/15/15 |
| `core/llm/prompts.py` | Ajout prompt on-chain (section 5) |
| `core/llm/context_builder.py` | Ajout contexte on-chain dans le JSON |
| `core/llm/response_parser.py` | Nouveau : forwarding vers post_processor |
| `core/data/sources.py` | Ajout Glassnode, DefiLlama, aggTrades collectors |

### 9.3 Nouveaux modules

| Fichier | Rôle |
|---------|------|
| `core/onchain/__init__.py` | Package on-chain |
| `core/onchain/collector.py` | Collecte netflow + stablecoins + delta |
| `core/onchain/post_processor.py` | Parse phrase LLM → deltas |
| `core/onchain/bias.py` | Calcule le 15% on-chain du composite |
| `core/onchain/sources/glassnode.py` | Client Glassnode API |
| `core/onchain/sources/defillama.py` | Client DefiLlama API |
| `core/onchain/sources/delta.py` | Calcul delta depuis aggTrades |

---

## 10. Tests requis

### 10.1 Tests unitaires (Post-Processor)

```
test_post_processor_netflow_outflow  → delta_netflow = +0.10
test_post_processor_netflow_inflow   → delta_netflow = -0.10
test_post_processor_stablecoin_mint  → delta_stablecoin = +0.05
test_post_processor_stablecoin_burn  → delta_stablecoin = -0.05
test_post_processor_delta_bullish    → delta_cumulative = +0.05
test_post_processor_delta_bearish    → delta_cumulative = -0.05
test_post_processor_full_confluence  → delta_total = +0.15
test_post_processor_mixed_signals    → deltas compensate
test_post_processor_empty_response   → delta_total = 0.00
test_post_processor_clamp_max        → delta_total ≤ +0.15
test_post_processor_clamp_min        → delta_total ≥ -0.15
test_post_processor_french_keywords  → "sorties" triggers +0.10
test_post_processor_neutral          → "no clear signal" → 0.00
```

### 10.2 Tests d'intégration

```
test_collector_glassnode_returns_valid_netflow
test_collector_defillama_returns_valid_stablecoin_supply
test_collector_binance_delta_calculation
test_full_pipeline_snapshot_to_bias
test_fallback_on_api_failure
test_fallback_on_llm_failure
test_cache_redis_ttl_2h
test_composite_formula_50_20_15_15
test_weight_redistribution_on_onchain_failure
```

### 10.3 Tests adversariaux

```
test_extreme_netflow_values_clamped
test_llm_hallucination_not_affecting_delta   ← via post-processor strict
test_concurrent_snapshot_updates
test_graceful_degradation_all_apis_down
test_historical_replay_onchain_bias          ← replay mode Phase 2.5
```

---

## 11. Métriques de performance

À suivre après intégration :

| Métrique | Baseline (sans on-chain) | Cible (avec on-chain) |
|----------|--------------------------|----------------------|
| Sharpe ratio OOS | > 1.5 | ≥ 1.5 (pas de dégradation) |
| Profit factor | > 1.5 | > 1.6 |
| Win rate | 56-58% | ≥ 56% |
| Max drawdown | < 15% | ≤ 15% |
| Trades/mois | 15-25 | ≥ 15 |

L'objectif du module on-chain n'est pas d'augmenter le nombre de trades mais d'améliorer la **qualité contextuelle** des décisions via le biais composite.

---

## 12. Calendrier d'intégration

| Étape | Durée | Dépendance |
|-------|-------|------------|
| 1. Collectors (Glassnode, DefiLlama, Delta) | 2-3 jours | Rien |
| 2. Stockage Postgres (tables + indexes) | 0.5 jour | Étape 1 |
| 3. Post-Processor (règles de parsing) | 1-2 jours | Rien (testable avec phrases mock) |
| 4. Prompt LLM on-chain | 0.5 jour | Étape 1 |
| 5. Intégration bias composite (50/20/15/15) | 1 jour | Étapes 3-4 |
| 6. Tests unitaires + adversariaux | 2 jours | Étapes 1-5 |
| 7. Replay mode avec on-chain | 1 jour | Phase 2.5 + Étape 6 |
| **Total** | **8-10 jours** | |

---

## Changelog

**v1.0** (2026-05-15)
- [NEW] Module On-Chain Integration complet
- [NEW] 3 sources : Netflow (Glassnode), Stablecoins (DefiLlama), Delta (Binance aggTrades)
- [NEW] Pipeline 3 étapes : Collecte → LLM phrase factuelle → Post-Processing déterministe
- [NEW] Post-Processing Module avec 9 règles de parsing
- [BREAKING] Bias composite : 0.50/0.35/0.15 → 0.50/0.20/0.15/0.15
- [NEW] Stockage Postgres : on_chain_snapshots + on_chain_bias_history
- [NEW] Cache Redis TTL 2h pour fallback
- [NEW] Redistribution des poids si on-chain en échec

# LLM Analyst — Spécification

> Module d'analyse contextuelle. Le LLM fournit un biais interprétatif (35% du bias composite).
> Il ne déclenche JAMAIS un trade directement.

---

## Rôle

Le LLM Analyst est une couche de supervision qui :
1. Reçoit un snapshot de données marché toutes les heures
2. Produit une analyse structurée (bias, zones d'intérêt, momentum, notes)
3. Alimente le `bias_composite` à 35%
4. Ne prend aucune décision de trading

---

## Provider

- **Principal** : DeepSeek V4 standard
- **Fréquence** : 1 appel / heure (à H+5min pour laisser les bougies clôturer)
- **Fallback TTL** : 120 minutes (dernier contexte réutilisé si API down)
- **Après TTL** : `defensive_mode` — pas de nouveaux trades
- **Timeout API** : 30 secondes

---

## Données envoyées au LLM (chaque heure)

### Pour chaque actif (BTC, ETH, SOL, BNB, DOT)

```json
{
  "symbol": "BTCUSDT",
  "timestamp": "2026-05-15T14:05:00Z",
  
  "price_current": 67450.00,
  "price_change_24h_pct": 2.3,
  
  "ohlcv_context": {
    "1H": { "bars": 24, "high": 67800, "low": 66800 },
    "4H": { "bars": 12, "high": 68200, "low": 66000 },
    "1D": { "bars": 7,  "high": 69000, "low": 64000 }
  },
  
  "ict_structure": {
    "trend_state_1H": "UPTREND",
    "external_bias_4H": "BULLISH",
    "nearest_swings": {
      "external_high": 68200,
      "external_low": 65500,
      "short_term_high": 67600,
      "short_term_low": 66200
    },
    "pending_swings": [
      {"level": 67800, "type": "high", "layer": "short_term", "state": "pending"}
    ],
    "active_fvg": [
      {"type": "up", "low": 67100, "high": 67300, "strength": "strong"}
    ],
    "sweeps_last_4h": [
      {"type": "long", "level": 66200, "layer": "short_term", "time": "2026-05-15T11:30:00Z"}
    ],
    "trading_range": {"high": 68200, "low": 65500, "eq": 66850},
    "zone_current": "equilibrium"
  },
  
  "volume": {
    "volume_24h": 28500,
    "volume_vs_median_7d": 1.15,
    "delta_divergence": "none"
  },
  
  "funding": {
    "current": 0.00012,
    "mean_24h": 0.00008,
    "trend": "stable"
  },
  
  "derivatives": {
    "open_interest_usd": 12400000000,
    "oi_change_24h_pct": 3.2
  }
}
```

### Contexte global

```json
{
  "market_wide": {
    "btc_dominance": 52.4,
    "btc_dominance_trend": "declining",
    "total_market_cap": 2340000000000,
    "fear_greed_index": 62,
    "fear_greed_label": "Greed"
  },
  
  "correlations": {
    "btc_eth_7d": 0.82,
    "btc_sol_7d": 0.68
  },
  
  "active_kill_zone": "NY_AM",
  "is_weekend": false,
  
  "news_headlines": [
    "Bitcoin ETF flows positive for 5th consecutive day",
    "SEC postpones decision on ETH ETF options"
  ],
  
  "on_chain": {
    "exchange_netflow_24h_btc": "-3200 BTC",
    "stablecoin_mcap_change_7d": "+1.2B"
  }
}
```

---

## Format de sortie attendu (JSON strict)

```json
{
  "timestamp": "2026-05-15T14:05:00Z",
  "analysis_valid_until": "2026-05-15T15:05:00Z",
  
  "symbols": {
    "BTCUSDT": {
      "bias": "BULLISH",
      "bias_score": 0.72,
      "confidence": 0.75,
      "interest_zones": [
        {
          "level": 67100,
          "type": "FVG_ENTRY",
          "priority": 1,
          "description": "FVG haussier non touché, confluence avec OTE"
        }
      ],
      "invalidation_level": 66200,
      "momentum_score": 0.65,
      "narrative": "BTC accumulation en cours. ETF flows positifs renforcent le biais. Le sweep du low 66200 + FVG forme un setup classique de continuation."
    },
    "ETHUSDT": {
      "bias": "BULLISH",
      "bias_score": 0.65,
      "confidence": 0.70,
      "interest_zones": [],
      "invalidation_level": null,
      "momentum_score": 0.55,
      "narrative": "ETH suit BTC avec un léger retard. Pas de setup clair actuellement."
    }
  },
  
  "global_context": {
    "market_sentiment": "RISK_ON",
    "btc_dominance_trend": "DECLINING",
    "macro_events": ["FOMC minutes tomorrow 18:00 UTC"],
    "risk_adjustment": 0.85,
    "narrative": "Marché crypto en phase risk-on modérée. BTC dominance en baisse suggère un potentiel altseason à venir. Prudence avant FOMC demain."
  }
}
```

---

## Prompt système

```
Tu es NaiaTrade Analyst, un analyste de marché spécialisé dans la méthodologie 
ICT (Inner Circle Trader) appliquée aux marchés crypto.

TON RÔLE :
Tu analyses le contexte macro, la structure de prix ICT, et les données 
on-chain/sentiment pour fournir un biais directionnel par actif.

TA SORTIE :
Un JSON structuré avec bias, confidence, zones d'intérêt, et momentum score.

RÈGLES :
1. Biais = BULLISH, BEARISH, ou RANGE
2. bias_score = flottant entre -1.0 (bearish fort) et +1.0 (bullish fort)
3. Confidence = ta certitude dans ton analyse (0.0 à 1.0)
   - < 0.6 signifie que tu manques de données ou que le marché est ambigu
4. Les interest_zones sont des niveaux ICT exploitables (FVG, OTE, sweep levels)
5. Le momentum_score reflète la force de la dynamique actuelle (0.0 à 1.0)
6. Le risk_adjustment module l'exposition globale (0.5 = réduction de 50%)
   - < 0.7 : prudence accrue (news macro, incertitude)
   - > 0.9 : conditions favorables
```

---

## Gestion des erreurs

| Scénario | Comportement |
|---|---|
| API timeout (>30s) | Retry 1× après 5s. Si échec → utiliser dernier contexte valide |
| JSON invalide (mal formé) | Parser réessaye avec correction. Si échec → dernier contexte |
| Champ requis manquant | Valeur par défaut : bias=RANGE, confidence=0.3 |
| Confidence < 0.6 | Poids LLM redistribué : structural 0.85, funding 0.15 (LLM = 0) |
| TTL expiré (>2h sans réponse) | defensive_mode : pas de nouveaux trades |
| Hallucination (niveau hors range ±20%) | Niveau ignoré, loggué comme "hallucination_probable" |

---

## Intégration dans le système

```
[Data Pipeline] → [LLM Analyst] → [Postgres: bias_history]
                                        ↓
[Strategy Engine] ← bias_composite = 0.50 structural + 0.35 LLM + 0.15 funding
                                        ↓
                              [Signal Scoring] → [Risk Manager]
```

---

## Stockage

```sql
CREATE TABLE bias_history (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bias_label VARCHAR(10),
    bias_score DECIMAL(4,3),
    confidence DECIMAL(4,3),
    momentum_score DECIMAL(4,3),
    raw_response JSONB,
    source VARCHAR(20) DEFAULT 'deepseek_v4',
    is_fallback BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_bias_history_ts ON bias_history(timestamp DESC);
CREATE INDEX idx_bias_history_symbol_ts ON bias_history(symbol, timestamp DESC);
```

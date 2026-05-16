# Architecture Decisions — NaiaTrade

> Tous les choix tranchés, leur justification, et les alternatives rejetées.

---

## AD-001 : Timeframe de trading

**Décision** : 15m et 1H (pas de scalping sub-minute)
**Rejeté** : 1m/5m scalping
**Justification** :
- Sur 1m, ratio signal/bruit ~20/80. Patterns ICT écrasés par le bruit.
- Latence 150-300ms Algérie → Binance = désavantage structurel sur sub-minute.
- Frais 0.04% taker × 2 (aller-retour) = 0.08%/trade. Sur micro-mouvements 0.2%, les frais mangent l'edge.
- Les market makers HFT (colocalisés, <1ms) dominent le sub-minute.

---

## AD-002 : Multi-TF vs Single-TF avec N variables

**Décision** : Multi-TF (15m/N=5, 1H/N=5, 4H/N=5)
**Rejeté** : Single-TF avec N=3/5/9
**Justification** :
- Un swing N=27 sur 15m ≠ un swing N=5 sur 4H. Ce sont des structures de marché différentes.
- N=5 partout (fractal Williams) = confirmation homogène, prévisible.
- La sémantique ICT est préservée : micro = intra-session, short = session, external = multi-session.
- Évite le repaint des grands N sur petit timeframe.

---

## AD-003 : AND-stack vs Scoring probabiliste

**Décision** : Scoring probabiliste avec seuils (remplace le AND-stack)
**Rejeté** : Conditions binaires (all_of/any_of)
**Justification** :
- 10 conditions AND avec 60% de précision chacune → probabilité conjointe quasi-nulle.
- Under-trading massif (2-4 trades/mois observé).
- Le scoring permet de capturer des setups partiellement confluents avec un edge positif.
- Le marché crypto est non-stationnaire : les conditions exactes changent, l'edge relatif persiste.

---

## AD-004 : Objectif du système

**Décision** : Expectancy max (plus de trades, edge stable)
**Rejeté** : Précision max (peu de trades, haute qualité)
**Justification** :
- L'objectif est un revenu complémentaire → nécessite un flux régulier de trades.
- Seuils modérés (45/60/80) → 15-25 trades/mois, win rate 56-58%, profit factor > 1.35.
- Le Kelly cap protège contre les séries de pertes.
- La précision pure (70+) donne trop peu de trades pour un revenu stable.

---

## AD-005 : LLM en contexte vs LLM décisionnel

**Décision** : LLM fournit un contexte interprétatif UNIQUEMENT (35% du bias composite)
**Rejeté** : LLM génère des décisions de trade (ordre direct)
**Justification** :
- Le LLM n'est pas backtestable (non déterministe).
- Le LLM n'est pas fiable temps-réel (latence, timeout, hallucinations).
- Si hallucination → biais dans composite (dilué à 35%), pas ordre erroné.
- Architecture : LLM chuchote au Strategy Engine, ne prend pas le volant.

---

## AD-006 : Timezone

**Décision** : UTC pour le calcul interne, conversion locale pour affichage/LLM uniquement
**Rejeté** : Africa/Algiers comme timezone de référence
**Justification** :
- Les Kill Zones ICT sont définies en UTC (London = 07:00-10:00 UTC).
- En heure locale (UTC+1), tout était décalé d'1h → Silver Bullet à 14:00-15:00 UTC au lieu de 15:00-16:00.
- Les données de liquidité Binance confirment les patterns en UTC.
- La conversion locale est triviale pour l'affichage.

---

## AD-007 : Kill Zones crypto-adaptées

**Décision** : Kill Zones calibrées sur données réelles crypto (vs Forex standard)
**Rejeté** : Kill Zones ICT Forex standard sans adaptation
**Justification** :
- Données orderbook Binance (50,526 minutes) : pic liquidité 11:00 UTC, creux 21:00 UTC (-42%).
- NY AM (13:00-16:00 UTC) : volatilité maximale, overlap Europe/US.
- NY PM (19:00-21:00) : liquidité trop faible, désactivée sauf confluence forte.
- Weekend : ghost liquidity, biais vendeur dimanche -1.80% → mode restreint obligatoire.
- Sweep tolerance 90 min (vs 60 en Forex) car marché 24/7.

---

## AD-008 : Margin mode

**Décision** : Isolated margin (phase validation), Cross envisagé en phase live
**Rejeté** : Cross margin en phase test
**Justification** :
- Isolated cloisonne le risque : une position perdante n'affecte pas les autres.
- Cross est plus capital-efficient mais une erreur de sizing expose tout le compte.
- Changement vers Cross uniquement après 6 mois de track record.

---

## AD-009 : Risque initial

**Décision** : Ultra-conservateur (0.25% risk/trade, levier max 3x)
**Rejeté** : Standard (0.5-1%, 5x)
**Justification** :
- Phase de validation : la perception du risque est désalignée avec la réalité.
- Les seuils montent SEULEMENT après 60+ jours de paper trading validés.
- Le Kelly cap dynamique assure la transition progressive.

---

## AD-010 : Contrôle humain

**Décision** : Total en phase backtest/paper. Commit freeze en live réel.
**Rejeté** : Verrouillage total dès la phase test
**Justification** :
- Phase backtest/paper = itération rapide nécessaire, contrôle total.
- Phase live = kill switches codés en dur, modification uniquement via commit git.
- Pas de bouton "override" dans l'interface.
- Les modifications non-urgentes attendent la revue mensuelle.

---

## AD-011 : Signal Lifecycle

**Décision** : 5 états (DETECTED → ACTIVE → REINFORCED → DECAYING → INVALIDATED)
**Rejeté** : Signaux binaires (valide/invalide)
**Justification** :
- Sans lifecycle, un sweep vit éternellement → trades sur signaux morts.
- Interaction rules : un sweep vieillissant réactivé par un FVG au même niveau (+15pts).
- Sans REINFORCED, le decay tue des setups légitimes.
- Le marché crypto génère des signaux asynchrones (sweep puis FVG 5 barres plus tard).

---

## AD-012 : Global Market State

**Décision** : État unifié lu par tous les détecteurs
**Rejeté** : Chaque détecteur recalcule son contexte indépendamment
**Justification** :
- Sans état unifié → divergences runtime entre modules.
- Le session_state (KZ active, weekend) est partagé par tous les signaux.
- Le volatility_state ajuste les seuils de scoring dynamiquement.
- Un seul objet immuable mis à jour `on_each_bar_close`.

---

## AD-013 : SMT Corrélation

**Décision** : Rolling Pearson 7j + filtre de stabilité (min corr 0.5, min stability 0.6)
**Rejeté** : Seuil fixe 0.6, ou division par volatilité (mathématiquement invalide)
**Justification** :
- Les corrélations crypto changent de régime → seuil fixe = faux négatifs.
- La division par volatilité est incorrecte (Pearson déjà normalisé [-1,1]).
- Le filtre de stabilité : `1 - abs(corr - rolling_mean_corr_30d)` élimine les corrélations erratiques.
- Si conditions non remplies → 0 pts SMT pour ce signal.

---

## AD-014 : Kelly vs ICT sizing

**Décision** : Kelly = cap de survie (upper bound), ICT = allocation d'alpha (dans la limite du cap)
**Rejeté** : Conflit ou choix exclusif entre les deux
**Justification** :
- `final_risk = min(ict_risk × multiplier, kelly_cap_risk)`
- Kelly protège contre la ruine statistique (dérive de régime).
- ICT récompense la qualité contextuelle du setup.
- Si Kelly <= 0 → défensif (pas de trade), feature pas bug.
- C'est une hiérarchie, pas une tension.

---

## AD-015 : Stack technique

**Décision** : WSL2 Ubuntu, Docker, Postgres, Redis, Python 3.11+, CCXT
**Rejeté** : Windows natif, autre broker API
**Justification** :
- WSL2 pour le dev local (l'utilisateur est sur Windows).
- Docker pour reproductibilité (même environnement dev et VPS).
- Postgres pour état + journal (requêtes SQL puissantes sur l'historique).
- Redis pour messaging temps réel (pub/sub entre containers).
- CCXT plutôt que python-binance (portabilité multi-exchange future).

---

## AD-016 : LLM Provider

**Décision** : DeepSeek V4 standard
**Rejeté** : DeepSeek V4 Flash, GPT-4o, Claude API
**Justification** :
- Flash trop compressé → hallucinations sur setups ICT complexes.
- GPT-4o et Claude API = coûts récurrents élevés pour 24 appels/jour.
- DeepSeek V4 standard = bon compromis coût/qualité.
- Fallback : dernier contexte valide 2h, puis defensive_mode.

---

## AD-017 : Paper Trading

**Décision** : 30 jours minimum sur Binance Futures Testnet (si Replay Mode Phase 2.5 validé sur multi-actifs). Sinon 60 jours minimum.
**Rejeté** : Passage direct en réel après backtest
**Justification** :
- Le Replay Mode (bar-par-bar) valide la logique ICT, le scoring, et le lifecycle sur données historiques.
- Le Paper Trading valide exclusivement l'infrastructure : latence réseau, rejets d'ordres, déconnexions WebSocket.
- La séparation des responsabilités (logique vs infrastructure) permet de réduire la durée sans sacrifier la robustesse.
- Critères objectifs de passage : Sharpe live >= 60% du Sharpe backtest (si Replay validé).
- Zéro incident critique (perte d'état, ordre incohérent) sur les 30 derniers jours.
- Tous les régimes de marché traversés au moins une fois.

---

## AD-018 : Capital test réel

**Décision** : 200-500 USDT en phase C
**Rejeté** : Plus de capital pour "que ça vaille le coup"
**Justification** :
- Objectif phase C = découvrir les edge cases, pas générer du profit.
- Le capital doit être le minimum pour passer les filtres Binance (minNotional).
- "Perdre ce capital en apprentissage est normal."
- Scaling progressif seulement après 3+ mois de live stable.

---

## AD-019 : Actifs Phase 1

**Décision** : BTC, ETH, SOL, BNB, DOT
**Rejeté** : Plus d'actifs (XLM, XAUT, KASPA, MATIC, etc.) en phase 1
**Justification** :
- 5 actifs liquides suffisent pour valider le système.
- Les altcoins moins liquides ont slippage élevé et comportement erratique.
- Le LLM peut fournir un contexte plus détaillé sur 5 actifs que sur 15.
- Extension Phase 2+ après validation du core system.

---

## AD-020 : Backtester

**Décision** : VectorBT + custom avec slippage/frais/funding modélisés
**Rejeté** : Backtester custom from scratch
**Justification** :
- VectorBT est vectorisé (rapide), bien testé, walk-forward intégré.
- Custom layer par-dessus pour : frais maker/taker, funding rate historique, slippage modélisé, délai 1 bougie signal→exécution.
- Walk-forward obligatoire : 6 mois train / 2 mois test, fenêtre glissante sur 24 mois.

---

## AD-021 : Sources de données

**Décision** : Gratuit uniquement
**Rejeté** : Bloomberg Terminal, APIs payantes
**Justification** :
- OHLCV : Binance API + CCXT (gratuit, illimité)
- Funding : Binance Futures API (gratuit)
- On-chain : Glassnode free tier, CryptoQuant free, DefiLlama
- Fear & Greed : alternative.me (gratuit, 1 call/h)
- Sentiment : CoinDesk/CoinTelegraph RSS, LunarCrush free
- BTC Dominance : CoinGecko API
- Trading data (delta) : Binance aggTrades (gratuit, historique dispo)

---

## AD-022 : Formule bias_composite canonique en config versionnée

**Décision** : La formule `bias_composite` et ses 4 poids (structural, LLM, on-chain, funding) vivent dans `config/bias.yaml`, validé par pydantic (`core/risk/bias_config.py`). Tout le code et la doc référencent ce fichier. Aucun poids n'est écrit en dur ailleurs.

**Rejeté** : Poids en dur dans la doc (`01-ict-specs-v1.3.md`, `05-data-flow-architecture.md`, `AGENTS.md`, `07-on-chain-integration.md`).

**Justification** :
- La spec v1.3 contenait 5 versions divergentes du poids LLM (35% vs 20%) selon le doc consulté. Une source unique versionnée règle l'ambiguïté définitivement.
- Toute modification future des poids passe par un commit git + redéploiement (AD-010), traçable via le SHA git de `bias.yaml`.
- Les valeurs canoniques retenues : structural 0.50, LLM 0.20, on-chain 0.15, funding 0.15 — reflet de la séparation on-chain post-changelog v1.3.

---

## AD-023 : OCO non-atomique sur Binance Futures — transaction compensatoire

**Décision** : Binance Futures ne supporte pas d'ordre OCO atomique entrée + stop-loss + take-profit. La protection post-entrée repose sur une transaction compensatoire applicative : le stop-loss (et le take-profit) sont placés immédiatement après le fill de l'entrée. Un watchdog surveille la confirmation du stop-loss : si le SL n'est pas confirmé sous un timeout dur (N ms, à calibrer en Phase 7), une close marché immédiate est émise. Le test adversarial « entrée fillée, SL rejeté → flat sous X s » est obligatoire en Phase 5/6.

**Rejeté** : Hypothèse d'atomicité entrée+SL+TP (présente dans les specs v1.3).

**Justification** : Les specs `03-risk-manager-spec.md:97`, `09-sltp-optimization.md:101`, et `01-ict-specs-v1.3.md:351` supposent que l'entrée et le SL sont atomiques. Or Binance Futures API ne propose qu'un OCO SL/TP sur position existante (reduceOnly), pas d'OCO 3-jambes avec entrée. Une position nue entre le fill et l'ACK du SL expose le compte en flash-crash.

---

## AD-024 : Formule distance liquidation canonique

**Décision** : La contrainte de distance liquidation canonique est :
`|entry - liq| >= ratio × |entry - stop|` où `ratio = min_stop_to_liquidation_ratio` (valeur par défaut 2.0 dans `config/risk.yaml`). La maintenance margin est calculée par tiers de notional selon les paliers Binance réels (pas une constante).

**Rejeté** : La formule écrite dans `03-risk-manager-spec.md:220` (`distance(stop_loss, liq) >= ratio × distance(entry, liq)`) qui est mathématiquement contradictoire avec l'intention documentée et rejetterait tout stop raisonnable.

**Justification** : La spec et le commentaire de `config/risk.yaml:34` décrivent la même intention (« le stop doit être 2× plus proche de l'entrée que la liquidation ») mais la formule mathématique de la spec est fausse. Le commentaire a la bonne traduction : `|entry - liq| >= 2 × |entry - stop|`. La maintenance margin à paliers Binance doit être utilisée car la valeur constante de la spec sous-estime la liquidation sur gros notional.

---

## AD-025 : Définition drawdown — baseline et reset

**Décision** : Le drawdown est mesuré contre un high-water mark (peak equity glissant), pas contre l'open calendaire. Le daily DD est calculé sur une fenêtre glissante de 24h. Le weekly DD est calculé sur une fenêtre glissante de 7 jours. L'escalator Kill Switch (Règle 5) se déclenche sur ces métriques glissantes. Aucun reset à minuit calendaire — un saignement à cheval sur minuit ne remet pas le compteur à zéro.

**Rejeté** : Baseline = open 00:00 UTC calendaire (reset journalier). Cela masquerait les drawdowns lents à cheval sur la limite calendaire.

**Justification** : Sans définition explicite, la Règle 5 est inapplicable. Le reset calendaire est un « silent killer » classique : le drawdown n'atteint jamais le seuil parce que le compteur est remis à zéro toutes les 24h. La fenêtre glissante garantit qu'un -5% sur 24h glissantes est toujours détecté, quelle que soit l'heure.

---

## AD-026 : Kelly cold-start et ré-activation des setups

**Décision** : Tant que le nombre de trades enregistrés est < 30, le Kelly cap est désactivé et le risque par trade est fixé à `max_risk_per_trade_pct` (0.25%). Lorsqu'un setup est auto-désactivé (Kelly ≤ 0 sur 50 trades), un chemin de ré-activation est obligatoire : shadow-trading sur N trades avec expectancy > 0 sur fenêtre OOS avant ré-armement. Aucun setup n'est désactivé définitivement sans chemin de retour.

**Rejeté** : Kelly cap actif dès le premier trade (deadlock car besoin de trades pour calculer Kelly, besoin de Kelly pour trader). Setup désactivé définitivement (attrition garantie en marché non-stationnaire).

**Justification** : Le Kelly cold-start non spécifié produirait soit un deadlock (si défaut = « pas de trade »), soit une absence de protection (si défaut = permissif). La ré-activation est nécessaire car les marchés crypto changent de régime : un setup sous-performant pendant 50 trades peut redevenir profitable.

---

## AD-027 : Politique backtest — single-truth, anti-look-ahead

**Décision** : Le moteur de replay stateful (Phase 2.5) est la seule vérité pour les décisions go/no-go. VectorBT est utilisé uniquement pour le pré-screening de paramètres. Règles anti-look-ahead :
- Un swing n'est utilisable qu'après sa confirmation multi-barres (w=2 closes supplémentaires, spécifié dans `01-ict-specs-v1.3.md` §1).
- Le backtester applique le délai de confirmation swing + le délai 1 barre signal→exécution.
- Jamais de LLM live dans un backtest, replay, ou golden dataset : seules les réponses LLM historiques enregistrées (`bias_history`) ou des mocks sont utilisés.

**Rejeté** : VectorBT comme moteur de décision go/no-go. LLM live dans le replay.

**Justification** : Le replay stateful capture correctement le lifecycle des signaux, le Kelly path-dependent, et le Kill Switch — que le backtest vectorisé ignore. Le LLM live dans un replay « connaît le futur » (news, prix) et produit un edge fictif. Sans délai de confirmation swing, les swings confirmés « dans le futur » génèrent un faux edge systématique.

---

## AD-028 : Politique Decimal pour les montants monétaires

**Décision** : Toutes les valeurs monétaires (prix, quantités, notional, montants de risque, capital) utilisent `Decimal`. Les `float` sont réservés aux scores, ratios statistiques, et probabilités. La conversion Decimal ↔ float se fait uniquement aux frontières I/O (lecture YAML, envoi CCXT).

**Rejeté** : Float pour toutes les valeurs, y compris prix/quantités.

**Justification** : Les filtres Binance (stepSize, tickSize, minNotional) sont des frontières décimales exactes. Les erreurs d'arrondi flottant cumulées sur des centaines de trades produisent une érosion silencieuse. Le `Decimal` prévient les rejets d'ordres près de minNotional et l'imprécision cumulative. La migration est planifiée en WP-7 (conditionnée à validation humaine de cet ADR).

---

## Index des sigles

| Sigle | Définition |
|---|---|
| ICT | Inner Circle Trader (méthodologie de Michael Huddleston) |
| FVG | Fair Value Gap (gap de juste valeur) |
| SMT | Smart Money Technique (divergence) |
| AMD | Accumulation-Manipulation-Distribution |
| OTE | Optimal Trade Entry (Fibonacci 61.8%-79%) |
| BOS | Break of Structure (continuation de tendance) |
| CHoCH | Change of Character (retournement de tendance) |
| KZ | Kill Zone (fenêtre temporelle ICT) |
| SB | Silver Bullet (setup 15:00-16:00 UTC) |
| ATR | Average True Range (volatilité) |
| DD | Drawdown |
| OOS | Out-of-sample (validation hors échantillon) |
| HH/HL | Higher High / Higher Low (structure haussière) |
| LL/LH | Lower Low / Lower High (structure baissière) |

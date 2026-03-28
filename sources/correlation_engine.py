"""Correlation engine: detect cross-source narratives from financial data.

Sits between the aggregator and the LLM prompt formatter.
Receives deduplicated articles from fetch_all_sources() and identifies
pre-defined cross-source patterns (risk-on/off, divergences, policy-to-price, etc.).

Each detected narrative bundles related data points with a synthesis hint
that the LLM can use to generate cross-market tweets.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def detect_narratives(articles):
    """Scan articles for cross-source narrative patterns.

    Args:
        articles: List of article dicts from fetch_all_sources() (deduplicated, sorted).

    Returns:
        List of narrative dicts, sorted by strength (strongest first).
        Each narrative has: pattern_type, label, strength, data_points, synthesis_hint.
    """
    if not articles:
        return []

    # Index articles by type for fast lookup
    by_type = _index_by_type(articles)

    narratives = []

    # Run all pattern detectors
    detectors = [
        _detect_risk_regime,
        _detect_crypto_macro_divergence,
        _detect_policy_to_price,
        _detect_volatility_gap,
        _detect_dominance_rotation,
    ]

    for detector in detectors:
        try:
            narrative = detector(by_type, articles)
            if narrative:
                narratives.append(narrative)
        except Exception as e:
            logger.warning(f"Narrative detector {detector.__name__} failed: {e}")

    # Sort by strength descending
    narratives.sort(key=lambda n: n["strength"], reverse=True)

    if narratives:
        logger.info(f"Correlation engine: {len(narratives)} narratives detected")
        for n in narratives:
            logger.info(f"  - {n['pattern_type']}: {n['label']} (strength {n['strength']:.2f})")

    return narratives


def _index_by_type(articles):
    """Index articles by asset_type for fast pattern matching."""
    by_type = {
        "crypto": [],
        "macro": [],
        "polymarket": [],
        "sentiment": [],
    }
    for a in articles:
        atype = a.get("asset_type", "")
        if atype in by_type:
            by_type[atype].append(a)
    return by_type


def _find_article(articles, **criteria):
    """Find first article matching all criteria (partial match on asset_id)."""
    for a in articles:
        match = True
        for key, value in criteria.items():
            article_val = a.get(key, "")
            if isinstance(value, list):
                if not any(v.lower() in str(article_val).lower() for v in value):
                    match = False
                    break
            else:
                if value.lower() not in str(article_val).lower():
                    match = False
                    break
        if match:
            return a
    return None


def _get_change(article):
    """Get change_pct from article, defaulting to 0."""
    return article.get("change_pct") or 0


# --- Pattern Detectors ---


def _detect_risk_regime(by_type, all_articles):
    """Detect risk-on or risk-off signals across all markets.

    Risk-on: BTC up + S&P up + VIX down
    Risk-off: BTC up down + S&P down + VIX up
    Strength increases with each confirming signal.
    """
    signals = []
    data_points = []
    direction = None  # "risk_on" or "risk_off"

    # BTC signal
    btc = _find_article(by_type["crypto"], asset_id="bitcoin")
    if btc:
        btc_change = _get_change(btc)
        if abs(btc_change) >= 0.5:
            data_points.append(btc)
            if btc_change > 0:
                signals.append(("btc_up", btc_change))
            else:
                signals.append(("btc_down", btc_change))

    # S&P 500 signal
    sp500 = _find_article(by_type["macro"], asset_id="^GSPC")
    if sp500:
        sp_change = _get_change(sp500)
        if abs(sp_change) >= 0.2:
            data_points.append(sp500)
            if sp_change > 0:
                signals.append(("sp_up", sp_change))
            else:
                signals.append(("sp_down", sp_change))

    # VIX signal (inverted: VIX down = risk-on)
    vix = _find_article(by_type["macro"], asset_id="^VIX")
    if vix:
        vix_change = _get_change(vix)
        if abs(vix_change) >= 1.0:
            data_points.append(vix)
            if vix_change < 0:
                signals.append(("vix_down", vix_change))
            else:
                signals.append(("vix_up", vix_change))

    # Polymarket recession/macro signal
    recession_market = None
    for a in by_type["polymarket"]:
        q = a.get("title", "").lower()
        if any(kw in q for kw in ["recession", "downturn", "bear market", "crash"]):
            recession_market = a
            break
    if recession_market:
        rec_change = _get_change(recession_market)
        if abs(rec_change) >= 2.0:
            data_points.append(recession_market)
            if rec_change < 0:  # Recession odds dropping = risk-on
                signals.append(("recession_odds_down", rec_change))
            else:
                signals.append(("recession_odds_up", rec_change))

    if len(signals) < 2 or len(data_points) < 2:
        return None

    # Determine direction
    risk_on_signals = [s for s in signals if s[0] in ("btc_up", "sp_up", "vix_down", "recession_odds_down")]
    risk_off_signals = [s for s in signals if s[0] in ("btc_down", "sp_down", "vix_up", "recession_odds_up")]

    if len(risk_on_signals) >= 2 and len(risk_on_signals) > len(risk_off_signals):
        direction = "risk_on"
        strength = len(risk_on_signals) / 4.0
        label = "Risk-on across markets"
    elif len(risk_off_signals) >= 2 and len(risk_off_signals) > len(risk_on_signals):
        direction = "risk_off"
        strength = len(risk_off_signals) / 4.0
        label = "Risk-off across markets"
    else:
        return None

    # Build synthesis hint
    parts = []
    if btc and btc in data_points:
        parts.append(f"$BTC {_get_change(btc):+.1f}%")
    if sp500 and sp500 in data_points:
        parts.append(f"S&P 500 {_get_change(sp500):+.1f}%")
    if vix and vix in data_points:
        val = vix.get("summary", "")
        parts.append(f"VIX {_get_change(vix):+.1f}%")
    if recession_market and recession_market in data_points:
        parts.append(f"Polymarket recession odds {_get_change(recession_market):+.1f}pp")

    hint = f"{label}: {', '.join(parts)}."

    return {
        "pattern_type": direction,
        "label": label,
        "strength": min(strength, 1.0),
        "data_points": data_points,
        "synthesis_hint": hint,
        "suggested_template": "cross_market_narrative",
    }


def _detect_crypto_macro_divergence(by_type, all_articles):
    """Detect when crypto and traditional markets move in opposite directions.

    Triggers when BTC and S&P 500 diverge by significant amounts.
    """
    btc = _find_article(by_type["crypto"], asset_id="bitcoin")
    sp500 = _find_article(by_type["macro"], asset_id="^GSPC")

    if not btc or not sp500:
        return None

    btc_change = _get_change(btc)
    sp_change = _get_change(sp500)

    # Need meaningful moves in opposite directions
    if abs(btc_change) < 1.0 or abs(sp_change) < 0.3:
        return None

    # Check divergence (opposite signs)
    if btc_change * sp_change >= 0:
        return None  # Same direction, no divergence

    spread = abs(btc_change - sp_change)
    if spread < 2.0:
        return None  # Not significant enough

    strength = min(spread / 8.0, 1.0)

    data_points = [btc, sp500]

    # Add VIX for extra context if available
    vix = _find_article(by_type["macro"], asset_id="^VIX")
    if vix:
        data_points.append(vix)

    if btc_change > 0:
        label = "Crypto rallying while stocks decline"
        hint = f"$BTC {btc_change:+.1f}% while S&P 500 {sp_change:+.1f}%. Unusual divergence."
    else:
        label = "Stocks rising while crypto drops"
        hint = f"S&P 500 {sp_change:+.1f}% while $BTC {btc_change:+.1f}%. Markets decoupling."

    if vix:
        hint += f" VIX at {_get_change(vix):+.1f}%."

    return {
        "pattern_type": "divergence",
        "label": label,
        "strength": strength,
        "data_points": data_points,
        "synthesis_hint": hint,
        "suggested_template": "divergence_alert",
    }


def _detect_policy_to_price(by_type, all_articles):
    """Detect when Polymarket policy odds shifts correlate with price movements.

    E.g., Fed rate cut odds rising + Treasury yields falling + crypto reacting.
    """
    # Look for Fed/rate/tariff-related Polymarket markets
    policy_market = None
    policy_keywords = ["rate cut", "rate hike", "fed", "fomc", "tariff", "interest rate"]

    for a in by_type["polymarket"]:
        q = a.get("title", "").lower()
        if any(kw in q for kw in policy_keywords):
            if abs(_get_change(a)) >= 2.0:  # At least 2pp shift
                policy_market = a
                break

    if not policy_market:
        return None

    data_points = [policy_market]
    context_parts = []
    strength_signals = 1

    policy_change = _get_change(policy_market)
    question = policy_market.get("title", "")[:80]
    context_parts.append(f'Polymarket "{question}" {policy_change:+.1f}pp')

    # Treasury yield response
    tnx = _find_article(by_type["macro"], asset_id="^TNX")
    if tnx and abs(_get_change(tnx)) >= 0.5:
        data_points.append(tnx)
        strength_signals += 1
        context_parts.append(f"10Y Treasury {_get_change(tnx):+.1f}%")

    # Crypto response
    btc = _find_article(by_type["crypto"], asset_id="bitcoin")
    if btc and abs(_get_change(btc)) >= 0.5:
        data_points.append(btc)
        strength_signals += 1
        context_parts.append(f"$BTC {_get_change(btc):+.1f}%")

    # S&P response
    sp500 = _find_article(by_type["macro"], asset_id="^GSPC")
    if sp500 and abs(_get_change(sp500)) >= 0.2:
        data_points.append(sp500)
        strength_signals += 1
        context_parts.append(f"S&P 500 {_get_change(sp500):+.1f}%")

    if strength_signals < 2:
        return None

    strength = min(strength_signals / 4.0, 1.0)
    label = "Policy odds shifting with market reaction"
    hint = f"{'. '.join(context_parts)}."

    return {
        "pattern_type": "policy_to_price",
        "label": label,
        "strength": strength,
        "data_points": data_points,
        "synthesis_hint": hint,
        "suggested_template": "cross_market_narrative",
    }


def _detect_volatility_gap(by_type, all_articles):
    """Detect when stock volatility and crypto volatility diverge.

    E.g., VIX spiking while crypto is calm, or vice versa.
    """
    vix = _find_article(by_type["macro"], asset_id="^VIX")
    if not vix:
        return None

    vix_change = _get_change(vix)

    # Calculate average crypto volatility from top movers
    crypto_changes = [abs(_get_change(a)) for a in by_type["crypto"]
                      if a.get("asset_id") != "global" and _get_change(a) is not None]

    if not crypto_changes:
        return None

    avg_crypto_vol = sum(crypto_changes) / len(crypto_changes)

    # VIX spiking but crypto calm
    if vix_change >= 5.0 and avg_crypto_vol <= 2.0:
        label = "Stock volatility spiking, crypto calm"
        hint = f"VIX {vix_change:+.1f}% but top crypto average move just {avg_crypto_vol:.1f}%."
        strength = min(vix_change / 15.0, 1.0)
    # Crypto volatile but VIX dropping
    elif avg_crypto_vol >= 5.0 and vix_change <= -2.0:
        label = "Crypto volatile while stock volatility drops"
        hint = f"Top crypto average move {avg_crypto_vol:.1f}% while VIX {vix_change:+.1f}%."
        strength = min(avg_crypto_vol / 10.0, 1.0)
    else:
        return None

    # Get biggest crypto mover for the data points
    data_points = [vix]
    biggest_crypto = max(by_type["crypto"],
                         key=lambda a: abs(_get_change(a)) if a.get("asset_id") != "global" else 0,
                         default=None)
    if biggest_crypto:
        data_points.append(biggest_crypto)

    return {
        "pattern_type": "volatility_gap",
        "label": label,
        "strength": strength,
        "data_points": data_points,
        "synthesis_hint": hint,
        "suggested_template": "divergence_alert",
    }


def _detect_dominance_rotation(by_type, all_articles):
    """Detect capital rotation signals in crypto.

    BTC dominance dropping while total market cap rises = altcoin rotation.
    BTC dominance rising while total cap drops = flight to BTC safety.
    """
    # Find global crypto data
    global_article = _find_article(by_type["crypto"], asset_id="global")
    if not global_article:
        return None

    summary = global_article.get("summary", "").lower()
    mcap_change = _get_change(global_article)

    # Parse BTC dominance from summary (format: "BTC dominance: XX.X%")
    import re
    dom_match = re.search(r"btc dominance:\s*([\d.]+)%", summary)
    if not dom_match:
        return None

    btc_dom = float(dom_match.group(1))

    # Check BTC for price direction
    btc = _find_article(by_type["crypto"], asset_id="bitcoin")
    if not btc:
        return None

    btc_change = _get_change(btc)

    data_points = [global_article, btc]

    # Find biggest altcoin mover
    alt_movers = [a for a in by_type["crypto"]
                  if a.get("asset_id") not in ("bitcoin", "global")
                  and abs(_get_change(a)) >= 3.0]

    if not alt_movers:
        return None

    biggest_alt = max(alt_movers, key=lambda a: abs(_get_change(a)))
    data_points.append(biggest_alt)

    alt_symbol = biggest_alt.get("title", "").split("(")[-1].strip(") ") if "(" in biggest_alt.get("title", "") else ""
    alt_change = _get_change(biggest_alt)

    # Altcoin rotation: BTC dominance low/dropping + alts pumping
    if btc_dom < 55 and alt_change > 3.0 and mcap_change > 0:
        label = "Capital rotating into altcoins"
        hint = (f"BTC dominance at {btc_dom:.1f}%. "
                f"${alt_symbol} {alt_change:+.1f}% while total crypto cap {mcap_change:+.1f}%.")
        strength = min(abs(alt_change) / 10.0, 1.0)
    # Flight to BTC: BTC up while alts dump
    elif btc_change > 1.0 and alt_change < -3.0:
        label = "Flight to Bitcoin, altcoins dropping"
        hint = (f"$BTC {btc_change:+.1f}% while ${alt_symbol} {alt_change:+.1f}%. "
                f"BTC dominance at {btc_dom:.1f}%.")
        strength = min(abs(alt_change) / 10.0, 1.0)
    else:
        return None

    return {
        "pattern_type": "dominance_rotation",
        "label": label,
        "strength": strength,
        "data_points": data_points,
        "synthesis_hint": hint,
        "suggested_template": "cross_market_narrative",
    }

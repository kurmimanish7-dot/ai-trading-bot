import datetime
from typing import Dict, Any

class GlobalMacroSignalEngine:
    def __init__(self):
        # Benchmark thresholds
        self.weights = {
            "global_indices": 0.25,
            "commodities_macro": 0.15,
            "smart_money_fii": 0.20,
            "options_volatility": 0.20,
            "news_sentiment": 0.20
        }

    def evaluate_global_indices(self, gift_nifty_change: float, nasdaq_change: float) -> float:
        """Score: -100 (Full Bearish) to +100 (Full Bullish)"""
        # Gift Nifty aur Nasdaq overnight sentiment ka weighted average
        score = (gift_nifty_change * 15.0) + (nasdaq_change * 10.0)
        return max(-100.0, min(100.0, score))

    def evaluate_macro_commodities(self, crude_change_pct: float, dxy_val: float, us10y_yield: float) -> float:
        """Crude oil jump aur Dollar Index rise India ke liye negative hote hain"""
        score = 0.0
        # Crude impact
        if crude_change_pct > 1.5:
            score -= 40
        elif crude_change_pct < -1.5:
            score += 40

        # DXY (Dollar Index) impact
        if dxy_val > 104.5:
            score -= 30
        elif dxy_val < 102.0:
            score += 30

        # US 10-Year Bond Yield impact
        if us10y_yield > 4.30:
            score -= 30
        elif us10y_yield < 3.90:
            score += 30

        return max(-100.0, min(100.0, score))

    def evaluate_smart_money(self, fii_long_ratio: float, fii_cash_net_cr: float) -> float:
        """FII Futures Long-Short Ratio & Net Cash Flow"""
        score = 0.0
        # FII Long-Short Ratio (< 20% Extreme Bearish/Oversold, > 75% Overbought)
        if fii_long_ratio > 60.0:
            score += 50
        elif fii_long_ratio < 25.0:
            score -= 50

        # Cash Flow in Crores
        if fii_cash_net_cr > 1500:
            score += 50
        elif fii_cash_net_cr < -1500:
            score -= 50

        return max(-100.0, min(100.0, score))

    def evaluate_options_vix(self, pcr: float, india_vix: float) -> float:
        """PCR aur VIX Volatility Filter"""
        score = 0.0
        # Put-Call Ratio
        if pcr > 1.25:
            score += 50  # Bullish support
        elif pcr < 0.75:
            score -= 50  # Heavy call writing / Bearish

        # Volatility penalty
        if india_vix > 18.0:
            score -= 20  # High uncertainty
        elif india_vix < 13.5:
            score += 20  # Stable market trend

        return max(-100.0, min(100.0, score))

    def generate_market_advisory(self, telemetry_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Consolidated engine jo Current Day aur Tomorrow dono ke signals deta hai.
        """
        now = datetime.datetime.now()
        is_after_market = now.time() > datetime.time(15, 30) or now.time() < datetime.time(9, 15)

        # 1. Component Scores (-100 to +100)
        s_global = self.evaluate_global_indices(
            telemetry_input.get("gift_nifty_change_pct", 0.0),
            telemetry_input.get("nasdaq_change_pct", 0.0)
        )
        s_macro = self.evaluate_macro_commodities(
            telemetry_input.get("brent_crude_change_pct", 0.0),
            telemetry_input.get("dxy_index", 103.0),
            telemetry_input.get("us10y_yield", 4.10)
        )
        s_smart_money = self.evaluate_smart_money(
            telemetry_input.get("fii_long_ratio_pct", 45.0),
            telemetry_input.get("fii_cash_net_cr", 0.0)
        )
        s_options = self.evaluate_options_vix(
            telemetry_input.get("pcr", 1.0),
            telemetry_input.get("india_vix", 14.0)
        )
        s_news = float(telemetry_input.get("gemini_news_sentiment_score", 0.0)) * 10.0  # scale -10..+10 to -100..+100

        # 2. Weighted Institutional Composite Score (-100 to +100)
        composite_score = (
            (s_global * self.weights["global_indices"]) +
            (s_macro * self.weights["commodities_macro"]) +
            (s_smart_money * self.weights["smart_money_fii"]) +
            (s_options * self.weights["options_volatility"]) +
            (s_news * self.weights["news_sentiment"])
        )

        # 3. Actionable Advisory Classification
        if composite_score >= 45:
            bias = "AGGRESSIVE BULLISH"
            action_today = "BUY ON DIPS (CE / LONG)"
            tomorrow_outlook = "GAP-UP EXPECTED (+0.6% to +1.2%) - HOLD LONGS / BTST"
        elif composite_score >= 15:
            bias = "MODERATE BULLISH"
            action_today = "MOMENTUM BUY NEAR SUPPORT"
            tomorrow_outlook = "MILD GAP-UP / FLAT WITH BULLISH BIAS"
        elif composite_score <= -45:
            bias = "AGGRESSIVE BEARISH"
            action_today = "SELL ON RISE (PE / SHORT)"
            tomorrow_outlook = "GAP-DOWN EXPECTED (-0.7% to -1.5%) - OVERNIGHT PUTS (STBT)"
        elif composite_score <= -15:
            bias = "MODERATE BEARISH"
            action_today = "FADE RALLIES AT VWAP RESISTANCE"
            tomorrow_outlook = "MILD GAP-DOWN / CHOPPY FLAT"
        else:
            bias = "NEUTRAL / CHOPPY"
            action_today = "NO DIRECTIONAL TRADE (OPTION SELLING / STRANGLE)"
            tomorrow_outlook = "FLAT OPENING EXPECTED (±0.2%) - RANGE BOUND"

        return {
            "mode": "AFTER_MARKET_PREDICTION" if is_after_market else "LIVE_MARKET_EXECUTION",
            "composite_score": round(composite_score, 1),
            "institutional_bias": bias,
            "current_day_advisory": action_today,
            "tomorrow_prediction": tomorrow_outlook,
            "pillar_breakdown": {
                "global_indices_score": round(s_global, 1),
                "macro_commodities_score": round(s_macro, 1),
                "smart_money_fii_score": round(s_smart_money, 1),
                "options_volatility_score": round(s_options, 1),
                "geopolitical_news_score": round(s_news, 1)
            }
        }
if __name__ == "__main__":
    engine = GlobalMacroSignalEngine()

    # Telemetry data format
    sample_market_data = {
        "gift_nifty_change_pct": 0.85,          # Gift Nifty up
        "nasdaq_change_pct": 1.10,              # US Tech rally
        "brent_crude_change_pct": -1.8,         # Crude cooling down (Bullish for India)
        "dxy_index": 103.2,                     # Dollar stable
        "us10y_yield": 4.12,                    # US Yields stable
        "fii_long_ratio_pct": 68.0,             # Institutions heavily long
        "fii_cash_net_cr": 2150.0,              # Massive FII inflow
        "pcr": 1.28,                            # Put writers in control
        "india_vix": 13.2,                      # Low risk environment
        "gemini_news_sentiment_score": 7.5      # Positive macro geopolitics
    }

    advisory = engine.generate_market_advisory(sample_market_data)

    print("--- INSTITUTIONAL TRADING ADVISORY ---")
    print(f"Mode                : {advisory['mode']}")
    print(f"Composite Score     : {advisory['composite_score']} / 100")
    print(f"Bias                : {advisory['institutional_bias']}")
    print(f"Current Day Action  : {advisory['current_day_advisory']}")
    print(f"Tomorrow Prediction : {advisory['tomorrow_prediction']}")
    print("Scores Breakdown    :", advisory['pillar_breakdown'])
  

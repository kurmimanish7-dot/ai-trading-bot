
# -*- coding: utf-8 -*-
"""
OTR v2 - Opening Trap Ratio + Global Impact Engine
Paste / import in app.py - Bhai ka patch

Kya karta hai:
- 9:15-9:45 ke trap ko pakadta hai
- Global impact ko OTR se jodta hai, alag se nahi
- CE ko tabhi allow karta hai jab sab layers green hon

Usage in app.py:
  from otr_v2 import calculate_otr_v2
  otr = calculate_otr_v2(...)
  if otr["ce_blocked"]:
      return None  # make_trade_idea me CE mat bana
"""

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")

# ============ 1. GLOBAL IMPACT LAYER ============
# Har global factor ka weight fix hai, taaki ek din Nasdaq gira to OTR khud CE block kar de

def global_impact_score(macro=None, gift_gap_pct=0.0, us_vix_change_pct=0.0, usd_inr_change_pct=0.0):
    """
    macro = GlobalMacroEngine.fetch_macro_quotes() wala dict
    gift_gap_pct = (GIFT Nifty - Prev Nifty Close) / Prev Close * 100
    Returns: score -5 se +5, verdict, reasons list
    Negative = Global bearish = CE ke liye dangerous
    """
    score = 0.0
    reasons = []
    if macro is None:
        macro = {}

    # Nasdaq / S&P - sabse bada global driver
    nasdaq = macro.get("NASDAQ", {}).get("change_pct", 0.0) if isinstance(macro.get("NASDAQ"), dict) else 0.0
    spx = macro.get("SP500", {}).get("change_pct", 0.0) if isinstance(macro.get("SP500"), dict) else nasdaq
    us_avg = (nasdaq + spx) / 2.0
    if us_avg <= -1.0:
        score -= 2.0; reasons.append(f"US weak: Nasdaq/SPX {us_avg:.2f}%")
    elif us_avg <= -0.4:
        score -= 1.0; reasons.append(f"US soft: {us_avg:.2f}%")
    elif us_avg >= 1.0:
        score += 1.5; reasons.append(f"US strong: {us_avg:.2f}%")
    elif us_avg >= 0.4:
        score += 0.5; reasons.append(f"US mild positive: {us_avg:.2f}%")

    # GIFT Nifty - India ka overnight gap batata hai
    if gift_gap_pct <= -0.5:
        score -= 1.5; reasons.append(f"GIFT gap-down {gift_gap_pct:.2f}% - opening trap risk")
    elif gift_gap_pct <= -0.2:
        score -= 0.5; reasons.append(f"GIFT soft {gift_gap_pct:.2f}%")
    elif gift_gap_pct >= 0.5:
        score += 1.0; reasons.append(f"GIFT gap-up {gift_gap_pct:.2f}%")
    
    # Crude - India ke liye inflation + FII sentiment
    crude = macro.get("CRUDE_OIL", {}).get("change_pct", 0.0) if isinstance(macro.get("CRUDE_OIL"), dict) else 0.0
    if crude >= 2.0:
        score -= 1.0; reasons.append(f"Crude spike {crude:.2f}% - FII selling risk")
    elif crude <= -2.0:
        score += 0.5; reasons.append(f"Crude cool {crude:.2f}%")

    # USDINR - Dollar strong = FII outflow
    if usd_inr_change_pct >= 0.4:
        score -= 1.0; reasons.append(f"USDINR up {usd_inr_change_pct:.2f}% - FII outflow pressure")
    elif usd_inr_change_pct <= -0.3:
        score += 0.5; reasons.append(f"USDINR down {usd_inr_change_pct:.2f}% - FII comfort")

    # US VIX spike - Global fear
    if us_vix_change_pct >= 10:
        score -= 1.0; reasons.append(f"US VIX spike +{us_vix_change_pct:.1f}% - global fear")
    
    score = max(-5.0, min(5.0, score))
    verdict = "BEARISH" if score <= -2 else ("BULLISH" if score >= 2 else "NEUTRAL")
    return {"score": round(score, 2), "verdict": verdict, "reasons": reasons}


# ============ 2. OTR v2 MAIN ENGINE ============
def calculate_otr_v2(
    spot=0, day_open=0, prev_close=0, prev_day_high=0, prev_day_low=0,
    orb_high=0, orb_low=0, vwap=0,
    ce_oi_change=0, pe_oi_change=0,
    ce_premium_pct=0.0, spot_pct_5m=0.0,
    vix_now=13.0, vix_prev_close=13.0,
    macro=None, gift_gap_pct=0.0, usd_inr_change_pct=0.0, us_vix_change_pct=0.0,
    breadth_adv=0, breadth_dec=0,
    nifty_pct=0.0, banknifty_pct=0.0,
    max_pain=0, gamma_flip=0,
    first_15m_volume_ratio=1.0,
    current_time=None
):
    """
    Sab signals ko ek OTR score me jodta hai.
    Returns dict with otr_score 0-10, ce_blocked, pe_only, verdict, reasons
    OTR high = TRAP = CE mat lo
    """
    if current_time is None:
        current_time = datetime.now(IST).time()
    
    otr = 0.0
    reasons = []
    blocks = []

    # --- A. OPENING STRUCTURE - 40% weight ---
    if orb_low and spot and spot < orb_low:
        otr += 2.0; reasons.append(f"TRAP: Spot {spot:.0f} < OR Low {orb_low:.0f} - opening breakdown")
        blocks.append("ORB_BREAKDOWN")
    if vwap and spot and spot < vwap:
        otr += 1.0; reasons.append(f"Spot < VWAP {vwap:.0f} - institutions bech rahe hain")
    if day_open and spot and spot < day_open:
        otr += 1.0; reasons.append(f"Spot < Day Open {day_open:.0f} - gap fill / weakness")
    if prev_day_low and spot and spot < prev_day_low:
        otr += 1.5; reasons.append(f"Spot < Prev Day Low {prev_day_low:.0f} - major breakdown")
        blocks.append("PDL_BREAKDOWN")
    # Gap fill trap: Gap-up khul ke gap fill kar diya to CE trap
    if prev_close and day_open and spot:
        gap_pct = (day_open - prev_close) / prev_close * 100
        if gap_pct > 0.3 and spot <= prev_close:
            otr += 1.5; reasons.append(f"Gap-up {gap_pct:.2f}% fill ho gaya - bull trap")
            blocks.append("GAP_FILL_TRAP")

    # --- B. LIVE OI DELTA - 20% weight ---
    # Total PCR nahi, sirf aaj ke pehle 15 min ka change
    if ce_oi_change > 0 and spot_pct_5m < 0:
        otr += 1.5; reasons.append(f"SHORT BUILDUP: Spot down + CE OI +{ce_oi_change:,} - Call writing")
        blocks.append("SHORT_BUILDUP")
    if pe_oi_change < 0 and spot_pct_5m < 0:
        otr += 0.5; reasons.append("PE OI unwinding - put support hat raha hai")
    if ce_oi_change < 0 and pe_oi_change > 0 and spot_pct_5m > 0:
        otr -= 0.5; reasons.append("Healthy: CE unwinding + PE building - real buying")

    # --- C. PREMIUM VELOCITY - Theta Trap ---
    if spot_pct_5m < -0.15 and ce_premium_pct < -5:
        ratio = abs(ce_premium_pct / spot_pct_5m) if spot_pct_5m != 0 else 0
        if ratio >= 8:
            otr += 1.5; reasons.append(f"THETA TRAP: Spot {spot_pct_5m:.2f}% par CE {ce_premium_pct:.1f}% gira - velocity {ratio:.1f}x")
            blocks.append("THETA_TRAP")

    # --- D. GLOBAL IMPACT - 25% weight, OTR se connected ---
    g = global_impact_score(macro, gift_gap_pct, us_vix_change_pct, usd_inr_change_pct)
    if g["score"] <= -3:
        otr += 2.0; reasons.append(f"GLOBAL BEARISH ({g['score']}): " + " | ".join(g["reasons"][:2]))
        blocks.append("GLOBAL_BEARISH")
    elif g["score"] <= -1.5:
        otr += 1.0; reasons.append(f"Global soft ({g['score']}): " + " | ".join(g["reasons"][:1]))
    elif g["score"] >= 2:
        otr -= 0.5; reasons.append(f"Global supportive ({g['score']})")

    # --- E. INDIA VIX + VOLATILITY ---
    vix_change = vix_now - vix_prev_close
    if vix_change >= 1.0:
        otr += 1.0; reasons.append(f"VIX spike {vix_prev_close:.1f} -> {vix_now:.1f} (+{vix_change:.1f}) - premium crush risk")
    if vix_now >= 18:
        otr += 0.5; reasons.append(f"VIX high {vix_now:.1f} - option buying risky")

    # --- F. BREADTH + SECTOR DIVERGENCE ---
    total_breadth = breadth_adv + breadth_dec
    if total_breadth > 0:
        adv_pct = breadth_adv / total_breadth * 100
        if adv_pct < 35:
            otr += 1.0; reasons.append(f"Breadth weak: {breadth_adv} adv vs {breadth_dec} dec ({adv_pct:.0f}%)")
        elif adv_pct > 65:
            otr -= 0.5; reasons.append(f"Breadth strong {adv_pct:.0f}% adv")
    # BankNifty vs Nifty divergence - Bank lead nahi kar raha to rally fake
    if nifty_pct > 0.2 and banknifty_pct < -0.2:
        otr += 1.0; reasons.append(f"Divergence: Nifty {nifty_pct:+.2f}% par BankNifty {banknifty_pct:+.2f}% - rally me dum nahi")
        blocks.append("BANK_DIVERGENCE")

    # --- G. MAX PAIN + GEX MAGNET ---
    if max_pain and spot and spot > max_pain and (spot - max_pain) > 80:
        otr += 0.5; reasons.append(f"Max Pain magnet neeche {max_pain:.0f} - CE ko neeche kheenchega")
    if gamma_flip and spot and spot < gamma_flip:
        otr += 0.5; reasons.append(f"Spot < Gamma Flip {gamma_flip:.0f} - negative gamma zone, fast fall")

    # --- H. VOLUME CONFIRMATION ---
    if first_15m_volume_ratio < 0.7:
        otr += 0.5; reasons.append(f"Volume weak {first_15m_volume_ratio:.2f}x - breakout me dum nahi")

    # --- I. TIME TRAP WINDOW ---
    is_trap_window = dtime(9, 15) <= current_time <= dtime(9, 45)
    if is_trap_window and otr >= 2:
        otr += 0.5; reasons.append("9:15-9:45 trap window - extra caution")

    otr = max(0.0, min(10.0, round(otr, 2)))

    # Final verdict
    if otr >= 5.5:
        verdict = "NO TRADE - FULL TRAP"
        ce_blocked, pe_only = True, False
    elif otr >= 3.5:
        verdict = "CE BLOCK - PE ONLY / WAIT"
        ce_blocked, pe_only = True, True
    elif otr >= 2.0:
        verdict = "CE CAUTION - HALF QTY + TIGHT SL"
        ce_blocked, pe_only = False, False
    else:
        verdict = "CE ALLOWED - CLEAN OPENING"
        ce_blocked, pe_only = False, False

    return {
        "otr": otr, "verdict": verdict,
        "ce_blocked": ce_blocked, "pe_only": pe_only,
        "global": g, "blocks": blocks, "reasons": reasons,
        "is_trap_window": is_trap_window
    }


# ============ 3. APP.PY ME KAHAN JODE - COPY PASTE ============
"""
1. make_trade_idea() ke start me, bullish decide karne se PEHLE:

   otr = calculate_otr_v2(spot=last, day_open=day_open, orb_high=orb_high, ...)
   if otr["ce_blocked"] and option_side == "CE":
       return None  # CE mat bana

2. auto_send_entry_alert_if_new() me Telegram bhejne se pehle:

   if otr["otr"] >= 3.5:
       return False, "OTR Block - Trap"

3. Main scan loop me, idea banane se pehle OTR print kar:
   st.warning(f"OTR {otr['otr']} - {otr['verdict']}")

4. Global data ke liye existing GlobalMacroEngine use kar:
   macro_q = global_macro_inst.fetch_macro_quotes()
   gift_gap = (gift_nifty - prev_close) / prev_close * 100
"""
print("OTR v2 loaded - 8 layers ready")

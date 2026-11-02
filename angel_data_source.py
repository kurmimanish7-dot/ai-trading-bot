# -*- coding: utf-8 -*-
"""
Angel Data Source - V17 FINAL - Fixes Prior Month Bug + Auto-Rolling Nearest
User: Active underlying ka LTP sahi, baki Nifty chod ke prior month ka dikh raha hai
Fix: Idea ki expiry use karo, selected_expiry nahi + Nearest auto-rolls every month
"""

import re
import time
import requests
from datetime import datetime, date, timedelta

_MASTER_CACHE = None
_MASTER_CACHE_TIME = 0
_MASTER_CACHE_TTL = 300

def parse_expiry_from_tradingsymbol(tradingsym: str):
    try:
        sym = tradingsym.upper().strip()
        for name in ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX", "NIFTY", "SENSEX"]:
            if sym.startswith(name):
                sym = sym[len(name):]
                break
        m = re.match(r'^(\d{2})([A-Z]{3})(\d{4})(\d+)(CE|PE)$', sym)
        if m:
            day, mon, yr = int(m.group(1)), m.group(2), int(m.group(3))
            mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            if mon in mon_map:
                return date(yr, mon_map[mon], day)
        m = re.match(r'^(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)$', sym)
        if m:
            day, mon, yr = int(m.group(1)), m.group(2), int(m.group(3))
            if yr < 100:
                yr += 2000
            mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            if mon in mon_map:
                return date(yr, mon_map[mon], day)
        return None
    except:
        return None

def parse_expiry_to_date(s: str):
    if not s:
        return None
    s = s.strip().upper()
    for fmt in ["%d %b %Y", "%d%b%Y", "%d%b%y", "%d-%b-%Y", "%Y-%m-%d"]:
        try:
            m = re.search(r'(\d{2})([A-Z]{3})(\d{2,4})', s)
            if m and "%b" in fmt:
                d, mon, y = m.groups()
                if len(y) == 2:
                    y = "20" + y
                test = f"{d} {mon.title()} {y}" if " " in fmt else f"{d}{mon.title()}{y}"
            else:
                test = s
            dt = datetime.strptime(test, fmt)
            return dt.date()
        except:
            continue
    return None

def get_angel_master():
    global _MASTER_CACHE, _MASTER_CACHE_TIME
    now = time.time()
    if _MASTER_CACHE and (now - _MASTER_CACHE_TIME) < _MASTER_CACHE_TTL:
        return _MASTER_CACHE
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        _MASTER_CACHE = data
        _MASTER_CACHE_TIME = now
        return data
    except:
        return _MASTER_CACHE if _MASTER_CACHE else []

def get_all_expiries_for_dropdown_correct(symbol: str):
    """V17: All future expiries sorted ascending - nearest first - auto rolls"""
    try:
        instruments = get_angel_master()
        exp_count = {}
        sym_upper = symbol.upper().strip()
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            if str(inst.get("exch_seg","")).upper() not in ["NFO", "BFO"]:
                continue
            if "FUT" in str(inst.get("instrumenttype","")).upper():
                continue
            tradingsym = str(inst.get("symbol","")).upper()
            if sym_upper == "NIFTY":
                if not tradingsym.startswith("NIFTY") or any(x in tradingsym for x in ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]):
                    continue
            elif sym_upper == "BANKNIFTY":
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif sym_upper == "FINNIFTY":
                if "FINNIFTY" not in tradingsym:
                    continue
            elif sym_upper == "SENSEX":
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif sym_upper == "BANKEX":
                if "BANKEX" not in tradingsym:
                    continue
            exp = parse_expiry_from_tradingsymbol(tradingsym)
            if not exp:
                exp = parse_expiry_to_date(str(inst.get("expiry","")))
            if exp:
                exp_count[exp] = exp_count.get(exp, 0) + 1
        valid_exps = [d for d, cnt in exp_count.items() if cnt >= 10]
        unique = sorted(set(valid_exps))
        today = datetime.now().date()
        future = [d for d in unique if d >= today]
        if not future:
            future = [d for d in unique if d >= today - timedelta(days=1)]
        result = future[:12] if future else unique[:12]
        return [d.strftime("%d %b %Y") for d in result]
    except:
        return []

def get_current_month_nearest_expiry(symbol: str):
    """V17: Nearest expiry auto-rolls every month - fixes prior month bug"""
    try:
        exps = get_all_expiries_for_dropdown_correct(symbol)
        if exps:
            return exps[0]
        return datetime.now().date().strftime("%d %b %Y")
    except:
        return datetime.now().date().strftime("%d %b %Y")

def get_nearest_expiry_auto_roll(symbol: str):
    return get_current_month_nearest_expiry(symbol)

def get_angel_ltp_EXACT_EXPIRY_ONLY(symbol: str, strike: int, opt_type: str, expiry: str, api_key="", client_id="", password="", totp_secret=""):
    """V17 FINAL - NO FALLBACK - Exact expiry only - fixes prior month + 3 month ahead"""
    target_symbol = symbol.upper().strip()
    target_strike = int(strike)
    target_opt = opt_type.upper().strip()
    target_date = parse_expiry_to_date(expiry)
    if not target_date:
        target_date = parse_expiry_from_tradingsymbol(expiry)
    if not target_date:
        return 0, f"V17_INVALID_EXPIRY_{expiry}", False
    str_7 = target_date.strftime("%d%b%y").upper()
    str_9 = target_date.strftime("%d%b%Y").upper()
    try:
        instruments = get_angel_master()
        candidates = []
        available_exps_for_strike = set()
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            if str(inst.get("exch_seg","")).upper() not in ["NFO", "BFO"]:
                continue
            if "FUT" in str(inst.get("instrumenttype","")).upper():
                continue
            tradingsym = str(inst.get("symbol","")).upper()
            if target_symbol == "NIFTY":
                if not tradingsym.startswith("NIFTY") or any(x in tradingsym for x in ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]):
                    continue
            elif target_symbol == "BANKNIFTY":
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif target_symbol == "FINNIFTY":
                if "FINNIFTY" not in tradingsym:
                    continue
            elif target_symbol == "SENSEX":
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif target_symbol == "BANKEX":
                if "BANKEX" not in tradingsym:
                    continue
            try:
                raw = inst.get("strike", -1)
                stk = int(float(raw)/100) if float(raw) > 1000 else int(float(raw))
                if stk == target_strike:
                    d = parse_expiry_from_tradingsymbol(tradingsym)
                    if not d:
                        d = parse_expiry_to_date(str(inst.get("expiry","")))
                    if d:
                        available_exps_for_strike.add(d.strftime("%d %b %Y"))
            except:
                continue
            try:
                raw = inst.get("strike", -1)
                stk = int(float(raw)/100) if float(raw) > 1000 else int(float(raw))
            except:
                continue
            if stk != target_strike:
                continue
            if target_opt == "CE" and not tradingsym.endswith("CE"):
                continue
            if target_opt == "PE" and not tradingsym.endswith("PE"):
                continue
            inst_date = parse_expiry_from_tradingsymbol(tradingsym)
            if not inst_date:
                inst_date = parse_expiry_to_date(str(inst.get("expiry","")))
            is_exact = False
            if str_7 in tradingsym or str_9 in tradingsym:
                is_exact = True
            elif inst_date and inst_date == target_date:
                is_exact = True
            if not is_exact:
                continue
            token = str(inst.get("token",""))
            if token:
                candidates.append({"token": token, "tradingsym": tradingsym, "expiry": inst_date})
        if not candidates:
            avail = sorted(list(available_exps_for_strike))[:5]
            debug_msg = f"V17_NO_CANDIDATE_EXACT_{target_symbol}_{target_strike}{target_opt}_WANT_{target_date.strftime('%d %b %Y')}_AVAILABLE_{avail}"
            return 0, debug_msg, False
        try:
            from SmartApi import SmartConnect
            import pyotp
            if not api_key or not client_id:
                return 0, "V17_NO_CREDS", False
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now() if totp_secret else ""
            sess = obj.generateSession(client_id, password, totp)
            if not sess or not sess.get('status'):
                return 0, "V17_SESSION_FAILED", False
            for cand in candidates:
                try:
                    exch = "BFO" if "SENSEX" in target_symbol or "BANKEX" in target_symbol else "NFO"
                    data = obj.ltpData(exch, cand["tradingsym"], cand["token"])
                    if data and data.get('status'):
                        ltp = float(data.get('data', {}).get('ltp', 0))
                        if ltp > 0:
                            return ltp, f"V17_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_date.strftime('%d%b%Y')}_{cand['tradingsym']}_LTP_{ltp}", True
                except:
                    continue
            return 0, f"V17_LTP_FAILED_{len(candidates)}", False
        except Exception as e:
            return 0, f"V17_EXC_{str(e)[:100]}", False
    except Exception as e:
        return 0, f"V17_OUTER_EXC_{str(e)[:150]}", False

def get_angel_ltp_100pct_broker_match(symbol="NIFTY", strike=0, opt_type="CE", expiry=""):
    try:
        import streamlit as st
        api_key = st.secrets.get("ANGEL_API_KEY", "") or st.secrets.get("API_KEY", "")
        client_id = st.secrets.get("ANGEL_CLIENT_ID", "") or st.secrets.get("CLIENT_ID", "")
        password = st.secrets.get("ANGEL_PASSWORD", "") or st.secrets.get("PASSWORD", "")
        totp_secret = st.secrets.get("ANGEL_TOTP_SECRET", "") or st.secrets.get("TOTP_SECRET", "")
        return get_angel_ltp_EXACT_EXPIRY_ONLY(symbol, strike, opt_type, expiry, api_key, client_id, password, totp_secret)
    except:
        return get_angel_ltp_EXACT_EXPIRY_ONLY(symbol, strike, opt_type, expiry)

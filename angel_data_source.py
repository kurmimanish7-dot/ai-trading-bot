# -*- coding: utf-8 -*-
"""
Angel Data Source - DEBUG V5 - Logs exact matching for SENSEX bug
"""

import datetime
from datetime import datetime, timedelta, date
import json
import re
import requests
import time

_MASTER_CACHE = None
_MASTER_CACHE_TIME = 0
_MASTER_CACHE_TTL = 300

KNOWN_INDEX_TOKENS = {
    "NIFTY": "99926000",
    "BANKNIFTY": "99926009",
    "FINNIFTY": "99926037",
    "SENSEX": "99919000",
    "MIDCPNIFTY": "99926034",
    "BANKEX": "99919001",
}

def parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym: str, symbol: str = ""):
    try:
        sym = tradingsym.upper().strip()
        idx_names = ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX", "NIFTY", "SENSEX"]
        remaining = sym
        for name in sorted(idx_names, key=len, reverse=True):
            if sym.startswith(name):
                remaining = sym[len(name):]
                break
        if len(remaining) >= 9:
            candidate_9 = remaining[:9]
            m = re.match(r'^(\d{2})([A-Z]{3})(\d{4})$', candidate_9)
            if m:
                day_str, mon_str, yr_str = m.groups()
                rest = remaining[9:]
                if re.match(r'^\d+CE$|^\d+PE$', rest):
                    day = int(day_str)
                    yr = int(yr_str)
                    mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                    mon = mon_map.get(mon_str.upper(), 0)
                    if mon and 1 <= day <= 31 and 2020 <= yr <= 2035:
                        return date(yr, mon, day)
        if len(remaining) >= 7:
            candidate_7 = remaining[:7]
            m = re.match(r'^(\d{2})([A-Z]{3})(\d{2})$', candidate_7)
            if m:
                day_str, mon_str, yr_str = m.groups()
                rest = remaining[7:]
                if re.match(r'^\d+CE$|^\d+PE$', rest):
                    day = int(day_str)
                    yr = int(yr_str)
                    if yr < 100:
                        yr = 2000 + yr
                    mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                    mon = mon_map.get(mon_str.upper(), 0)
                    if mon and 1 <= day <= 31 and 2020 <= yr <= 2035:
                        return date(yr, mon, day)
        return None
    except:
        return None

def parse_expiry_to_date_ULTIMATE(s: str):
    if not s or str(s).strip() in ["", "-1", "None"]:
        return None
    s = str(s).strip().upper()
    formats_to_try = ["%d%b%Y", "%d %b %Y", "%d-%b-%Y", "%d%b%y", "%d %b %y", "%Y-%m-%d"]
    candidates = [s, s.replace(" ", ""), s.replace("-", "")]
    for cand in candidates:
        for fmt in formats_to_try:
            try:
                test_cand = cand
                if "%b" in fmt:
                    m_match = re.search(r'(\d{2})([A-Z]{3})(\d+)', cand)
                    if m_match:
                        d, mon, y = m_match.groups()
                        if " " in fmt:
                            test_cand = f"{d} {mon.title()} {y}"
                        elif "-" in fmt:
                            test_cand = f"{d}-{mon.title()}-{y}"
                        else:
                            test_cand = f"{d}{mon.title()}{y}"
                dt = datetime.strptime(test_cand, fmt)
                return dt.date()
            except:
                continue
    for pat in [r'(\d{2})([A-Z]{3})(\d{4})', r'(\d{2})([A-Z]{3})(\d{2})']:
        m = re.search(pat, s)
        if m:
            day_str, mon_str, yr_str = m.groups()
            try:
                day = int(day_str)
                yr = int(yr_str)
                if len(yr_str) == 2:
                    yr = 2000 + yr
                mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                mon = mon_map.get(mon_str, 0)
                if mon:
                    return date(yr, mon, day)
            except:
                continue
    return None

def get_angel_master_ULTIMATE(force_refresh=False):
    global _MASTER_CACHE, _MASTER_CACHE_TIME
    now = time.time()
    if not force_refresh and _MASTER_CACHE is not None and (now - _MASTER_CACHE_TIME) < _MASTER_CACHE_TTL:
        return _MASTER_CACHE
    try:
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(master_url, timeout=15)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        instruments = r.json()
        _MASTER_CACHE = instruments
        _MASTER_CACHE_TIME = now
        return instruments
    except Exception as e:
        if _MASTER_CACHE is not None:
            return _MASTER_CACHE
        return []

def get_all_index_tokens_from_angel_master():
    try:
        instruments = get_angel_master_ULTIMATE()
        tokens = {}
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            symbol = str(inst.get("symbol","")).upper()
            name = str(inst.get("name","")).upper()
            token = str(inst.get("token",""))
            exch_seg = str(inst.get("exch_seg","")).upper()
            if exch_seg in ["NSE", "BSE"]:
                if symbol == "NIFTY" or name == "NIFTY":
                    tokens["NIFTY"] = token
                if "BANKNIFTY" in symbol or "BANKNIFTY" in name:
                    tokens["BANKNIFTY"] = token
                if "FINNIFTY" in symbol:
                    tokens["FINNIFTY"] = token
                if "MIDCPNIFTY" in symbol:
                    tokens["MIDCPNIFTY"] = token
                if symbol == "SENSEX" or (name == "SENSEX" and "BANKEX" not in name):
                    tokens["SENSEX"] = token
                if "BANKEX" in symbol:
                    tokens["BANKEX"] = token
        for k, v in KNOWN_INDEX_TOKENS.items():
            if k not in tokens:
                tokens[k] = v
        return tokens
    except:
        return KNOWN_INDEX_TOKENS

def get_expiry_list_from_angel_master_correct(symbol: str):
    try:
        instruments = get_angel_master_ULTIMATE()
        filtered = []
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
                if not tradingsym.startswith("NIFTY"):
                    continue
                if any(x in tradingsym for x in ["FINNIFTY", "BANKNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]):
                    continue
            elif "BANKNIFTY" in sym_upper:
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif "FINNIFTY" in sym_upper:
                if "FINNIFTY" not in tradingsym:
                    continue
            elif "SENSEX" in sym_upper and "BANKEX" not in sym_upper:
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif "MIDCP" in sym_upper:
                if "MIDCPNIFTY" not in tradingsym:
                    continue
            elif "BANKEX" in sym_upper:
                if "BANKEX" not in tradingsym:
                    continue
            exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, sym_upper)
            if not exp_date:
                exp_raw = str(inst.get("expiry","")).strip()
                if exp_raw and exp_raw not in ["", "-1"]:
                    exp_date = parse_expiry_to_date_ULTIMATE(exp_raw)
            if exp_date:
                filtered.append(exp_date)
        unique = sorted(list(set(filtered)))
        today = datetime.now().date()
        future_filtered = [d for d in unique if d >= today - timedelta(days=7) and d <= today + timedelta(days=180)]
        if future_filtered:
            return sorted(future_filtered)
        return sorted(unique)
    except:
        return []

def get_all_expiries_for_dropdown_correct(symbol: str):
    all_exps = get_expiry_list_from_angel_master_correct(symbol)
    return [d.strftime("%d %b %Y") for d in all_exps[:6]]

# DEBUG VERSION - Logs everything
def get_angel_ltp_EXACT_EXPIRY_ONLY(symbol: str, strike: int, opt_type: str, expiry: str, api_key="", client_id="", password="", totp_secret=""):
    """
    DEBUG - Exact expiry only - Logs why 05 Nov returns 26 Nov
    """
    target_symbol = symbol.upper().strip()
    target_strike = int(strike)
    target_opt = opt_type.upper().strip()
    target_exp_date = parse_expiry_to_date_ULTIMATE(expiry)
    if not target_exp_date:
        target_exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(expiry, target_symbol)
    if not target_exp_date:
        return 0, f"INVALID_EXPIRY_{expiry}", False
    
    try:
        instruments = get_angel_master_ULTIMATE()
        candidates_exact = []
        candidates_all_74500 = []  # For debugging SENSEX 74500
        
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            if str(inst.get("exch_seg","")).upper() not in ["NFO", "BFO"]:
                continue
            if "FUT" in str(inst.get("instrumenttype","")).upper():
                continue
            if "OPT" not in str(inst.get("instrumenttype","")).upper():
                continue
            tradingsym = str(inst.get("symbol","")).upper()
            
            # For debugging, collect all SENSEX 74500 CE
            if target_symbol == "SENSEX" and "74500" in tradingsym and tradingsym.endswith("CE"):
                if "SENSEX" in tradingsym and "BANKEX" not in tradingsym:
                    exp_for_debug = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, target_symbol)
                    candidates_all_74500.append((tradingsym, str(inst.get("token","")), exp_for_debug))
            
            if target_symbol == "NIFTY":
                if not tradingsym.startswith("NIFTY"):
                    continue
                if any(x in tradingsym for x in ["FINNIFTY", "BANKNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]):
                    continue
            elif "BANKNIFTY" in target_symbol:
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif "FINNIFTY" in target_symbol:
                if "FINNIFTY" not in tradingsym:
                    continue
            elif "SENSEX" in target_symbol and "BANKEX" not in target_symbol:
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif "MIDCP" in target_symbol:
                if "MIDCPNIFTY" not in tradingsym:
                    continue
            elif "BANKEX" in target_symbol:
                if "BANKEX" not in tradingsym:
                    continue
            
            try:
                inst_strike_raw = inst.get("strike", -1)
                inst_strike = int(float(inst_strike_raw) / 100) if float(inst_strike_raw) > 1000 else int(float(inst_strike_raw))
            except:
                continue
            if inst_strike != target_strike:
                continue
            
            if target_opt == "CE" and not tradingsym.endswith("CE"):
                continue
            if target_opt == "PE" and not tradingsym.endswith("PE"):
                continue
            
            inst_exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, target_symbol)
            if not inst_exp_date:
                inst_expiry_raw = str(inst.get("expiry","")).strip()
                inst_exp_date = parse_expiry_to_date_ULTIMATE(inst_expiry_raw)
            
            if not inst_exp_date:
                continue
            if inst_exp_date != target_exp_date:
                continue
            
            token = str(inst.get("token",""))
            if token:
                candidates_exact.append({'token': token, 'tradingsym': tradingsym, 'expiry': inst_exp_date})
        
        # DEBUG LOG for SENSEX 05 Nov case
        debug_info = ""
        if target_symbol == "SENSEX" and target_strike == 74500 and target_exp_date == date(2026, 11, 5):
            debug_info = f"DEBUG_SENSEX_05NOV: Found {len(candidates_exact)} exact candidates for 05 Nov, All 74500 tokens: {candidates_all_74500[:5]}"
            print(debug_info)
        
        if not candidates_exact:
            # No exact candidate - this is the bug! Return debug info
            if candidates_all_74500:
                return 0, f"NO_EXACT_CANDIDATE_05NOV_BUT_FOUND_{len(candidates_all_74500)}_TOKENS_{candidates_all_74500[:3]}_TARGET_{target_exp_date}", False
            return 0, f"NO_CANDIDATE_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_TOTAL_MASTER_{len(instruments)}", False
        
        try:
            from SmartApi import SmartConnect
            import pyotp
            if not api_key or not client_id:
                return 0, f"NO_CREDS_CANDIDATES_{len(candidates_exact)}_EXP_{target_exp_date.strftime('%d%b%Y')}_{debug_info}", False
            
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now() if totp_secret else ""
            sess = obj.generateSession(client_id, password, totp)
            if not sess or not sess.get('status'):
                return 0, f"SESSION_FAILED", False
            
            best_ltp = 0
            best_cand = None
            for cand in candidates_exact:
                try:
                    exchange = "BFO" if "SENSEX" in target_symbol or "BANKEX" in target_symbol else "NFO"
                    ltp_data = obj.ltpData(exchange, cand['tradingsym'], cand['token'])
                    if ltp_data and ltp_data.get('status'):
                        ltp = float(ltp_data.get('data', {}).get('ltp', 0))
                        if ltp > 0 and ltp < 10000:
                            if best_ltp == 0 or ltp < best_ltp:
                                best_ltp = ltp
                                best_cand = cand
                except:
                    continue
            
            if best_cand and best_ltp > 0:
                return best_ltp, f"ANGEL_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_TOKEN_{best_cand['token']}_LTP_{best_ltp}_{debug_info}", True
            
            return 0, f"ANGEL_LTP_FAILED_CAND_{len(candidates_exact)}_EXP_{target_exp_date.strftime('%d%b%Y')}_{debug_info}", False
            
        except Exception as e:
            return 0, f"ANGEL_EXC_{str(e)[:80]}_CAND_{len(candidates_exact)}_{debug_info}", False
            
    except Exception as e:
        return 0, f"EXC_{str(e)[:150]}", False

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

def get_yahoo_spot(symbol: str):
    try:
        import yfinance as yf
        ticker_map = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "FINNIFTY": "NIFTY_FIN_SERVICE.NS", "SENSEX": "^BSESN", "MIDCPNIFTY": "NIFTY_MID_SELECT.NS", "BANKEX": "^BSEBANK"}
        ticker = ticker_map.get(symbol.upper(), "^NSEI")
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist['Close'].iloc[-1]), f"YAHOO_{symbol}"
        return 0, "YAHOO_FAILED"
    except:
        return 0, "YAHOO_EXC"

def get_angel_spot(symbol: str, api_key="", client_id="", password="", totp_secret=""):
    try:
        from SmartApi import SmartConnect
        import pyotp
        tokens = get_all_index_tokens_from_angel_master()
        token = tokens.get(symbol.upper(), "")
        if not token or not api_key:
            return 0, "NO_TOKEN_OR_CREDS"
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now() if totp_secret else ""
        sess = obj.generateSession(client_id, password, totp)
        if not sess or not sess.get('status'):
            return 0, "SESSION_FAILED"
        exchange = "BSE" if "SENSEX" in symbol.upper() or "BANKEX" in symbol.upper() else "NSE"
        ltp_data = obj.ltpData(exchange, symbol.upper(), token)
        if ltp_data and ltp_data.get('status'):
            ltp = float(ltp_data.get('data', {}).get('ltp', 0))
            if ltp > 0:
                return ltp, f"ANGEL_SPOT_{symbol}_{token}"
        return 0, "ANGEL_SPOT_FAILED"
    except Exception as e:
        return 0, f"ANGEL_SPOT_EXC_{str(e)[:30]}"

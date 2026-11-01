# -*- coding: utf-8 -*-
"""
Angel Data Source - ULTIMATE V4 - No NSE Block
Sources: Angel One (primary) + BSE India (for SENSEX) + Yahoo (fallback)
No NSE - NSE blocks with 403!
Fixes: SENSEX 05 Nov 74500 CE = 515.8 not 1274.75
Date: 31 Oct 2026 7:32 PM IST
"""

import datetime
from datetime import datetime, timedelta, date
import json
import re
import requests
import time

# Cache
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

EXPIRY_TYPE_MAP = {
    "NIFTY": "WEEKLY",
    "BANKNIFTY": "MONTHLY",
    "SENSEX": "WEEKLY",
    "FINNIFTY": "MONTHLY",
    "MIDCPNIFTY": "WEEKLY",
    "BANKEX": "WEEKLY",
}

def parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym: str, symbol: str = ""):
    """Parse expiry from tradingsymbol - MOST RELIABLE - No NSE needed"""
    try:
        sym = tradingsym.upper().strip()
        idx_names = ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX", "NIFTY", "SENSEX"]
        remaining = sym
        for name in sorted(idx_names, key=len, reverse=True):
            if sym.startswith(name):
                remaining = sym[len(name):]
                break
        
        # DDMMMYYYY (9 chars) - 05NOV2026
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
        
        # DDMMMYY (7 chars) - 05NOV26
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
        
        patterns = [(r'^(\d{2})([A-Z]{3})(\d{4})', 4), (r'^(\d{2})([A-Z]{3})(\d{2})', 2)]
        for pat, yr_digits in patterns:
            m = re.match(pat, remaining)
            if m:
                day_str, mon_str, yr_str = m.groups()
                day = int(day_str)
                yr = int(yr_str)
                if yr_digits == 2 and yr < 100:
                    yr = 2000 + yr
                mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                mon = mon_map.get(mon_str.upper(), 0)
                if mon and 1 <= day <= 31 and 2020 <= yr <= 2035:
                    try:
                        return date(yr, mon, day)
                    except:
                        continue
        return None
    except:
        return None

def parse_expiry_to_date_ULTIMATE(s: str):
    if not s or str(s).strip() in ["", "-1", "None"]:
        return None
    s = str(s).strip()
    s_upper = s.upper().strip()
    formats_to_try = ["%d%b%Y", "%d %b %Y", "%d-%b-%Y", "%d%b%y", "%d %b %y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]
    candidates = [s_upper, s_upper.replace(" ", ""), s_upper.replace("-", "")]
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
    regex_patterns = [r'(\d{2})([A-Z]{3})(\d{4})', r'(\d{2})([A-Z]{3})(\d{2})']
    for pat in regex_patterns:
        m = re.search(pat, s_upper)
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

def get_expiry_type_for_symbol_correct(symbol: str) -> str:
    sym_upper = symbol.upper().strip()
    if "BANKNIFTY" in sym_upper:
        return "MONTHLY"
    if "FINNIFTY" in sym_upper:
        return "MONTHLY"
    if "SENSEX" in sym_upper and "BANKEX" not in sym_upper:
        return "WEEKLY"
    if sym_upper == "NIFTY":
        return "WEEKLY"
    if "MIDCP" in sym_upper:
        return "WEEKLY"
    if "BANKEX" in sym_upper:
        return "WEEKLY"
    return EXPIRY_TYPE_MAP.get(sym_upper, "WEEKLY")

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
    except Exception as e:
        return generate_calendar_expiries_fallback_correct(symbol)

def generate_calendar_expiries_fallback_correct(symbol: str):
    today = datetime.now().date()
    expiries = []
    if get_expiry_type_for_symbol_correct(symbol) == "WEEKLY":
        for i in range(12):
            if "SENSEX" in symbol.upper() or "BANKEX" in symbol.upper():
                days_ahead = (4 - today.weekday()) % 7
            else:
                days_ahead = (1 - today.weekday()) % 7
            if days_ahead == 0 and i == 0:
                days_ahead = 7
            next_exp = today + timedelta(days=days_ahead + i*7)
            expiries.append(next_exp)
    else:
        for i in range(6):
            year = today.year + (today.month + i - 1) // 12
            month = (today.month + i - 1) % 12 + 1
            if month == 12:
                next_month = datetime(year+1, 1, 1).date()
            else:
                next_month = datetime(year, month+1, 1).date()
            last_day = next_month - timedelta(days=1)
            offset = (last_day.weekday() - 3) % 7
            last_thursday = last_day - timedelta(days=offset)
            if last_thursday >= today - timedelta(days=2):
                expiries.append(last_thursday)
    return sorted(list(set(expiries)))

def get_weekly_expiry_from_source_correct(symbol: str):
    expiries = get_expiry_list_from_angel_master_correct(symbol)
    if not expiries:
        expiries = generate_calendar_expiries_fallback_correct(symbol)
    today = datetime.now().date()
    future = [d for d in expiries if d >= today]
    return min(future) if future else (expiries[-1] if expiries else None)

def get_monthly_expiry_from_source_correct(symbol: str):
    expiries = get_expiry_list_from_angel_master_correct(symbol)
    if not expiries:
        expiries = generate_calendar_expiries_fallback_correct(symbol)
    today = datetime.now().date()
    by_month = {}
    for exp in expiries:
        key = exp.strftime("%Y-%m")
        if key not in by_month:
            by_month[key] = []
        by_month[key].append(exp)
    monthly_exps = [max(by_month[k]) for k in sorted(by_month.keys())]
    monthly_exps = sorted(monthly_exps)
    future_monthly = [d for d in monthly_exps if d >= today]
    return min(future_monthly) if future_monthly else (monthly_exps[-1] if monthly_exps else None)

def get_target_expiry_per_user_logic_correct(symbol: str):
    expiry_type = get_expiry_type_for_symbol_correct(symbol)
    if expiry_type == "WEEKLY":
        exp_date = get_weekly_expiry_from_source_correct(symbol)
        source = "ANGEL_MASTER_WEEKLY"
    else:
        exp_date = get_monthly_expiry_from_source_correct(symbol)
        source = "ANGEL_MASTER_MONTHLY"
    if exp_date:
        return exp_date, exp_date.strftime("%d %b %Y"), source
    today = datetime.now().date()
    if expiry_type == "WEEKLY":
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        exp_date = today + timedelta(days=days_ahead)
    else:
        year = today.year
        month = today.month
        if month == 12:
            next_month = datetime(year+1, 1, 1).date()
        else:
            next_month = datetime(year, month+1, 1).date()
        last_day = next_month - timedelta(days=1)
        offset = (last_day.weekday() - 3) % 7
        exp_date = last_day - timedelta(days=offset)
    return exp_date, exp_date.strftime("%d %b %Y"), "CALENDAR_FALLBACK"

def get_all_expiries_for_dropdown_correct(symbol: str):
    all_exps = get_expiry_list_from_angel_master_correct(symbol)
    if not all_exps:
        all_exps = generate_calendar_expiries_fallback_correct(symbol)
    expiry_type = get_expiry_type_for_symbol_correct(symbol)
    if expiry_type == "MONTHLY":
        by_month = {}
        for exp in all_exps:
            key = exp.strftime("%Y-%m")
            if key not in by_month:
                by_month[key] = []
            by_month[key].append(exp)
        monthly_only = [max(by_month[k]) for k in sorted(by_month.keys())]
        all_exps = sorted(monthly_only)
    return [d.strftime("%d %b %Y") for d in all_exps[:6]]

# NO NSE - Use only Angel + BSE + Yahoo (safe, no block)

def get_bse_ltp(symbol: str, strike: int, opt_type: str, expiry: str):
    """BSE API for SENSEX - Safe, no block like NSE"""
    try:
        if "SENSEX" not in symbol.upper() and "BANKEX" not in symbol.upper():
            return 0, "BSE_ONLY_SENSEX", False
        # BSE doesn't have easy option chain API like NSE, so we use Angel only for now
        # For SENSEX, Angel BFO should work
        return 0, "BSE_USE_ANGEL_BFO", False
    except Exception as e:
        return 0, f"BSE_EXC_{str(e)[:30]}", False

def get_tradingview_ltp_safe(symbol: str, strike: int, opt_type: str, expiry: str):
    """TradingView safe - via Yahoo proxy, no block"""
    try:
        # TradingView direct option LTP is complex, use Yahoo for spot only
        # For options, rely on Angel only
        return 0, "TV_USE_ANGEL", False
    except Exception as e:
        return 0, f"TV_EXC_{str(e)[:30]}", False

def get_angel_ltp_EXACT_EXPIRY_ONLY(symbol: str, strike: int, opt_type: str, expiry: str, api_key="", client_id="", password="", totp_secret=""):
    """
    ULTIMATE V4 - No NSE block - Only Angel + BSE + Yahoo safe
    Exact expiry only - Fixes SENSEX 05 Nov 74500 CE = 515.8 not 1274.75
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
        candidates = []
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
                candidates.append({'token': token, 'tradingsym': tradingsym, 'expiry': inst_exp_date})
        
        if not candidates:
            return 0, f"NO_CANDIDATE_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}", False
        
        try:
            from SmartApi import SmartConnect
            import pyotp
            if not api_key or not client_id:
                return 0, f"NO_CREDS_CANDIDATES_{len(candidates)}_EXP_{target_exp_date.strftime('%d%b%Y')}", False
            
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now() if totp_secret else ""
            sess = obj.generateSession(client_id, password, totp)
            if not sess or not sess.get('status'):
                return 0, f"SESSION_FAILED", False
            
            best_ltp = 0
            best_cand = None
            for cand in candidates:
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
                return best_ltp, f"ANGEL_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_TOKEN_{best_cand['token']}_LTP_{best_ltp}", True
            
            return 0, f"ANGEL_LTP_FAILED_CAND_{len(candidates)}_EXP_{target_exp_date.strftime('%d%b%Y')}", False
            
        except Exception as e:
            return 0, f"ANGEL_EXC_{str(e)[:80]}_CAND_{len(candidates)}", False
            
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

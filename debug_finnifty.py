# -*- coding: utf-8 -*-
"""
Angel One Data Source - Only LTP Data Fetch
SOURCE: Angel One OpenAPIScripMaster.json + SmartAPI
- All index tokens from Angel master (not just 4)
- Exact expiry match only (no ANY_EXPIRY)
- NIFTY Weekly, BANKNIFTY Monthly, SENSEX Weekly, FINNIFTY Monthly
- SENSEX 05 Nov = 515.8 not 26 Nov 1274.75
"""

import datetime
from datetime import datetime, timedelta, date
import json
import re
import requests

KNOWN_INDEX_TOKENS = {
    "NIFTY": "99926000",
    "BANKNIFTY": "99926009",
    "FINNIFTY": "99926037",
    "SENSEX": "99919000",
    "MIDCPNIFTY": "99926034",
    "BANKEX": "99919001",
    "SENSEX50": "99919002"
}

EXPIRY_TYPE_MAP = {
    "NIFTY": "WEEKLY",
    "BANKNIFTY": "MONTHLY",
    "SENSEX": "WEEKLY",
    "FINNIFTY": "MONTHLY",
    "MIDCPNIFTY": "WEEKLY",
    "BANKEX": "WEEKLY",
}

EXPIRY_FORMATS = [
    "%d%b%Y", "%d %b %Y", "%d-%b-%Y", "%d%b%y", "%d %b %y",
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"
]

def parse_expiry_to_date_ULTIMATE(s: str):
    if not s:
        return None
    s = str(s).strip()
    s_clean = re.sub(r"\s+", " ", s).strip()
    candidates = [s_clean, s_clean.upper(), s_clean.title(), s_clean.replace(" ", ""), s_clean.replace("-", ""), s_clean.replace(" ", "").upper()]
    for cand in candidates:
        for fmt in EXPIRY_FORMATS:
            try:
                try_cand = cand
                if "%b" in fmt:
                    try_cand = cand[:2] + cand[2:5].title() + cand[5:] if len(cand) > 5 else cand.title()
                dt = datetime.strptime(try_cand, fmt)
                return dt.date()
            except:
                continue
        m = re.search(r"(\d{2})([A-Z]{3})(\d{2,4})", s.upper())
        if m:
            day, mon, yr = m.groups()
            yr_full = "20"+yr if len(yr)==2 else yr
            try:
                return datetime.strptime(f"{day}{mon}{yr_full}", "%d%b%Y").date()
            except:
                pass
    return None

def get_expiry_type_for_symbol_correct(symbol: str) -> str:
    sym_upper = symbol.upper().strip()
    if "BANKNIFTY" in sym_upper:
        return "MONTHLY"
    if "FINNIFTY" in sym_upper or sym_upper == "FIN":
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

def get_all_index_tokens_from_angel_master():
    try:
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(master_url, timeout=10)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        instruments = r.json()
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
    except Exception as e:
        print(f"Tokens fetch error: {e}")
        return KNOWN_INDEX_TOKENS

def get_expiry_list_from_angel_master_correct(symbol: str):
    try:
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(master_url, timeout=10)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        instruments = r.json()
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
            exp_raw = str(inst.get("expiry","")).strip()
            if not exp_raw or exp_raw in ["", "-1"]:
                continue
            exp_date = parse_expiry_to_date_ULTIMATE(exp_raw)
            if exp_date:
                filtered.append(exp_date)
        return sorted(list(set(filtered)))
    except Exception as e:
        print(f"Expiry list error for {symbol}: {e}")
        return generate_calendar_expiries_fallback_correct(symbol)

def generate_calendar_expiries_fallback_correct(symbol: str):
    today = datetime.now().date()
    expiries = []
    if get_expiry_type_for_symbol_correct(symbol) == "WEEKLY":
        for i in range(10):
            if "SENSEX" in symbol.upper():
                days_ahead = (4 - today.weekday()) % 7
            else:
                days_ahead = (1 - today.weekday()) % 7
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
            if last_thursday >= today:
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

def get_angel_ltp_EXACT_EXPIRY_ONLY(symbol: str, strike: int, opt_type: str, expiry: str, api_key="", client_id="", password="", totp_secret=""):
    try:
        target_symbol = symbol.upper().strip()
        target_strike = int(strike)
        target_opt = opt_type.upper().strip()
        target_exp_date = parse_expiry_to_date_ULTIMATE(expiry)
        if not target_exp_date:
            return 0, f"INVALID_EXPIRY_{expiry}", False
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(master_url, timeout=10)
        if r.status_code != 200:
            return 0, f"MASTER_FETCH_FAILED_{r.status_code}", False
        instruments = r.json()
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
                inst_strike = int(float(inst.get("strike", -1)) / 100) if float(inst.get("strike", -1)) > 1000 else int(inst.get("strike", -1))
            except:
                continue
            if inst_strike != target_strike:
                continue
            if target_opt == "CE" and "CE" not in tradingsym[-5:]:
                continue
            if target_opt == "PE" and "PE" not in tradingsym[-5:]:
                continue
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
                        if ltp > 0 and ltp < 5000:
                            if best_ltp == 0 or ltp < best_ltp:
                                best_ltp = ltp
                                best_cand = cand
                except:
                    continue
            if best_cand and best_ltp > 0:
                return best_ltp, f"ANGEL_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_TOKEN_{best_cand['token']}_LTP_{best_ltp}", True
            return 0, f"NO_LTP_CANDIDATES_{len(candidates)}", False
        except Exception as e:
            return 0, f"LTP_ERROR_{str(e)[:50]}_CAND_{len(candidates)}", False
    except Exception as e:
        return 0, f"EXC_{str(e)[:100]}", False

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

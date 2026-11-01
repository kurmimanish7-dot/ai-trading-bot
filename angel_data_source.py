"""
FILE: Angel_data_source_v2.py
Mobile Ready - Production Hardened Angel One SmartAPI
"""

from __future__ import annotations
import datetime, json, logging, os, time, threading, urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    from SmartApi import SmartConnect
except ImportError:
    try:
        from smartapi import SmartConnect
    except ImportError:
        SmartConnect = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AngelV2")

@dataclass(frozen=True)
class IndexSpec:
    name: str; spot_exchange: str; spot_symbol: str; spot_token: str
    fno_exchange: str; strike_step: float; has_weekly_expiry: bool
    expected_expiry_weekday: int; default_lot_size: int

INDEX_REGISTRY: Dict[str, IndexSpec] = {
    "SENSEX": IndexSpec("SENSEX", "BSE", "SENSEX", "99919000", "BFO", 100.0, True, 3, 20),
    "NIFTY": IndexSpec("NIFTY", "NSE", "Nifty 50", "99926000", "NFO", 50.0, True, 1, 65),
    "BANKNIFTY": IndexSpec("BANKNIFTY", "NSE", "Nifty Bank", "99926009", "NFO", 100.0, False, 1, 30),
    "FINNIFTY": IndexSpec("FINNIFTY", "NSE", "Nifty Fin Service", "99926037", "NFO", 50.0, False, 1, 60),
    "MIDCPNIFTY": IndexSpec("MIDCPNIFTY", "NSE", "NIFTY MID SELECT", "99926074", "NFO", 25.0, False, 1, 120),
    "BANKEX": IndexSpec("BANKEX", "BSE", "BANKEX", "99919012", "BFO", 100.0, False, 3, 30),
}

@dataclass
class OptionContract:
    token: str; symbol: str; name: str; expiry_str: str
    expiry_date: datetime.date; strike: float; option_type: str
    lot_size: int; exchange: str; tick_size: float
    is_monthly: bool = False; ltp: float = 0.0; open: float = 0.0
    high: float = 0.0; low: float = 0.0; close: float = 0.0
    volume: int = 0; open_interest: int = 0; bid: float = 0.0; ask: float = 0.0
    last_updated_ts: float = field(default_factory=time.time)

class TokenBucketRateLimiter:
    def __init__(self, rate_per_sec: float = 3.0, burst: int = 3) -> None:
        self.rate_per_sec = rate_per_sec; self.capacity = float(burst)
        self.tokens = float(burst); self.last_refill = time.monotonic()
        self._lock = threading.Lock()
    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic(); elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
            self.last_refill = now
            if self.tokens < 1.0:
                time.sleep(max(0, (1.0 - self.tokens) / self.rate_per_sec))
                self.tokens = 0.0; self.last_refill = time.monotonic()
            else: self.tokens -= 1.0

class ScripMasterRepository:
    SCRIP_MASTER_URLS = (
        "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json",
        "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
    )
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = cache_dir; os.makedirs(self.cache_dir, exist_ok=True)
        self.contracts_by_index: Dict[str, List[OptionContract]] = {}
        self.expiries_by_index: Dict[str, List[datetime.date]] = {}
        self.monthly_expiries_by_index: Dict[str, List[datetime.date]] = {}

    def _get_cache_filepath(self) -> str:
        return os.path.join(self.cache_dir, f"OpenAPIScripMaster_{datetime.date.today().strftime('%Y%m%d')}.json")

    @staticmethod
    def _parse_expiry_date(expiry_str: str) -> Optional[datetime.date]:
        s = expiry_str.strip()
        for fmt in ["%d%b%Y", "%d-%b-%Y"]:
            try: return datetime.datetime.strptime(s.title(), fmt).date()
            except: 
                try: return datetime.datetime.strptime(s.upper(), fmt).date()
                except: continue
        return None

    def load_or_download(self, force_refresh: bool = False) -> None:
        cache_path = self._get_cache_filepath(); raw_records: List[Dict[str, Any]] = []
        if not force_refresh and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f: raw_records = json.load(f)
        else:
            for url in self.SCRIP_MASTER_URLS:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        payload = resp.read().decode("utf-8"); raw_records = json.loads(payload)
                    with open(cache_path, "w", encoding="utf-8") as f: f.write(payload)
                    break
                except Exception as e: logger.warning(f"Download fail {url}: {e}")
        if not raw_records: raise RuntimeError("ScripMaster download fail")
        self.index_records(raw_records)

    def index_records(self, raw_records: List[Dict[str, Any]]) -> None:
        self.contracts_by_index = {k: [] for k in INDEX_REGISTRY}
        today = datetime.date.today()
        for row in raw_records:
            if str(row.get("instrumenttype","")).upper() != "OPTIDX": continue
            name = str(row.get("name","")).upper()
            if name not in INDEX_REGISTRY: continue
            if str(row.get("exch_seg","")).upper() != INDEX_REGISTRY[name].fno_exchange: continue
            symbol = str(row.get("symbol","")).strip()
            opt_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else None
            if not opt_type: continue
            expiry_date = self._parse_expiry_date(str(row.get("expiry","")))
            if not expiry_date or expiry_date < today: continue
            try:
                strike = round(float(row.get("strike",0))/100.0, 2)
                tick = round(float(row.get("tick_size",5.0))/100.0, 4) or 0.05
                file_lot = int(float(row.get("lotsize", INDEX_REGISTRY[name].default_lot_size)))
                lot = max(file_lot, 25) if name=="SENSEX" and expiry_date >= datetime.date(2027,1,1) else file_lot
            except: continue
            if strike <=0: continue
            self.contracts_by_index[name].append(OptionContract(
                str(row.get("token","")), symbol, name, str(row.get("expiry","")),
                expiry_date, strike, opt_type, lot, INDEX_REGISTRY[name].fno_exchange, tick))
        for name, contracts in self.contracts_by_index.items():
            unique_expiries = sorted({c.expiry_date for c in contracts})
            self.expiries_by_index[name] = unique_expiries
            max_per_month: Dict[Tuple[int,int], datetime.date] = {}
            for d in unique_expiries:
                ym = (d.year, d.month)
                if ym not in max_per_month or d > max_per_month[ym]: max_per_month[ym]=d
            monthly_set = set(max_per_month.values())
            self.monthly_expiries_by_index[name]=sorted(monthly_set)
            for c in contracts: c.is_monthly = c.expiry_date in monthly_set

    def get_target_expiry(self, index_name: str, expiry_preference: str = "WEEKLY", reference_date: Optional[datetime.date]=None):
        idx=index_name.upper(); ref=reference_date or datetime.date.today()
        all_exp=[d for d in self.expiries_by_index.get(idx,[]) if d>=ref]
        monthly_exp=[d for d in self.monthly_expiries_by_index.get(idx,[]) if d>=ref]
        if not all_exp: raise LookupError(f"No expiry for {idx}")
        pref=expiry_preference.upper()
        if pref=="WEEKLY":
            if not INDEX_REGISTRY[idx].has_weekly_expiry: return monthly_exp[0] if monthly_exp else all_exp[0]
            return all_exp[0]
        elif pref=="NEXT_WEEKLY": return all_exp[1] if len(all_exp)>1 else all_exp[0]
        else: return monthly_exp[0] if monthly_exp else all_exp[0]

    def get_option_chain_contracts(self, index_name: str, spot_price: float, expiry_preference: str="WEEKLY", strike_count: int=8, reference_date: Optional[datetime.date]=None):
        idx=index_name.upper(); spec=INDEX_REGISTRY[idx]
        target_expiry=self.get_target_expiry(idx, expiry_preference, reference_date)
        atm=round(spot_price/spec.strike_step)*spec.strike_step
        min_s=atm-(strike_count*spec.strike_step); max_s=atm+(strike_count*spec.strike_step)
        matched=[c for c in self.contracts_by_index.get(idx,[]) if c.expiry_date==target_expiry and min_s-1e-4<=c.strike<=max_s+1e-4]
        matched.sort(key=lambda x:(x.strike, x.option_type))
        return target_expiry, atm, matched

class AngelSmartAPIClient:
    def __init__(self, api_key: str, client_code: str, password_or_pin: str, totp_secret: str, scrip_repo: Optional[ScripMasterRepository]=None):
        self.api_key=api_key; self.client_code=client_code; self.password_or_pin=password_or_pin; self.totp_secret=totp_secret
        self.scrip_repo=scrip_repo or ScripMasterRepository(); self.smart_api=None
        self.rate_limiter=TokenBucketRateLimiter(3.0,3); self.candle_limiter=TokenBucketRateLimiter(0.8,1)

    def authenticate(self, max_attempts: int=5) -> bool:
        if SmartConnect is None or pyotp is None: return False
        self.smart_api=SmartConnect(api_key=self.api_key); totp_gen=pyotp.TOTP(self.totp_secret)
        for attempt in range(1, max_attempts+1):
            try:
                rem=30-(int(time.time())%30)
                if rem<=2: time.sleep(rem+0.5)
                self.rate_limiter.acquire()
                resp=self.smart_api.generateSession(self.client_code, self.password_or_pin, totp_gen.now())
                if isinstance(resp, dict) and resp.get("status") and isinstance(resp.get("data"), dict):
                    logger.info("Login success"); return True
            except Exception as e: logger.warning(f"Login fail {attempt}: {e}")
            time.sleep(2)
        return False

    def fetch_spot_ltp(self, index_name: str) -> float:
        idx=index_name.upper(); spec=INDEX_REGISTRY[idx]
        if not self.smart_api: raise RuntimeError("Not authenticated")
        try:
            self.rate_limiter.acquire()
            resp=self.smart_api.ltpData(spec.spot_exchange, spec.spot_symbol, spec.spot_token)
            if resp.get("status") and resp.get("data"):
                ltp=float(resp["data"].get("ltp",0))
                if ltp>0: return ltp
        except: pass
        self.rate_limiter.acquire()
        resp=self.smart_api.getMarketData("FULL", {spec.spot_exchange: [spec.spot_token]})
        fetched=resp.get("data",{}).get("fetched",[])
        if fetched: return float(fetched[0].get("ltp",0))
        raise RuntimeError(f"Spot fail {idx}")

    def populate_option_chain_ltp(self, contracts: List[OptionContract]):
        if not contracts or not self.smart_api: return contracts
        token_map={(c.exchange,c.token):c for c in contracts}
        by_exch: Dict[str, List[str]]={}
        for c in contracts: by_exch.setdefault(c.exchange,[]).append(c.token)
        for exch, tokens in by_exch.items():
            for i in range(0,len(tokens),50):
                chunk=tokens[i:i+50]
                try:
                    self.rate_limiter.acquire()
                    resp=self.smart_api.getMarketData("FULL", {exch: chunk})
                    for item in resp.get("data",{}).get("fetched",[]):
                        con=token_map.get((item.get("exchange",exch).upper(), str(item.get("symbolToken",""))))
                        if con:
                            con.ltp=float(item.get("ltp",0) or 0)
                            con.bid=float((item.get("depth",{}).get("buy") or [{}])[0].get("price",0) or 0)
                            con.ask=float((item.get("depth",{}).get("sell") or [{}])[0].get("price",0) or 0)
                except Exception as e: logger.warning(f"Batch fail {e}")
        return contracts

    def fetch_weekly_option_chain(self, index_name: str="SENSEX", strike_count: int=6, expiry_preference: str="WEEKLY"):
        spot=self.fetch_spot_ltp(index_name)
        expiry, atm, chain=self.scrip_repo.get_option_chain_contracts(index_name, spot, expiry_preference, strike_count)
        self.populate_option_chain_ltp(chain)
        return spot, expiry, atm, chain

# --- MOBILE SE DIRECT USE ---
if __name__ == "__main__":
    # Yaha apni keys daal de bhai
    API_KEY = "YOUR_API_KEY"
    CLIENT_CODE = "YOUR_CLIENT_CODE"
    PIN = "YOUR_PIN"
    TOTP_SECRET = "YOUR_TOTP_SECRET"

    repo = ScripMasterRepository()
    print("ScripMaster download ho raha hai...")
    repo.load_or_download()
    print(f"SENSEX Expiries: {repo.expiries_by_index.get('SENSEX', [])[:2]}")

    client = AngelSmartAPIClient(API_KEY, CLIENT_CODE, PIN, TOTP_SECRET, repo)
    if client.authenticate():
        spot, expiry, atm, chain = client.fetch_weekly_option_chain("SENSEX", 3, "WEEKLY")
        print(f"Spot: {spot} | Expiry: {expiry} | ATM: {atm}")
        for c in chain[:6]: print(c.symbol, c.strike, c.option_type, c.ltp)
    else:
        print("Login fail - keys check kar")

import requests
import pandas as pd
from datetime import datetime


BASE_URL = "https://apiconnect.angelone.in"

SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)


class OptionsEngine:

    def __init__(
        self,
        jwt_token,
        api_key,
        client_code,
    ):

        self.jwt_token = jwt_token
        self.api_key = api_key
        self.client_code = client_code

        self.headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }

        self._scrip_master = None

    # ========================================================
    # SCRIPT MASTER
    # ========================================================

    def load_scrip_master(self):

        if self._scrip_master is not None:
            return self._scrip_master

        response = requests.get(
            SCRIP_MASTER_URL,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            return []

        self._scrip_master = data

        return data

    # ========================================================
    # OPTION CONTRACTS
    # ========================================================

    def get_option_contracts(
        self,
        underlying,
        expiry_date=None,
    ):

        data = self.load_scrip_master()

        if not data:
            return pd.DataFrame()

        underlying = str(
            underlying
        ).upper().strip()

        rows = []

        for item in data:

            if not isinstance(item, dict):
                continue

            exch_seg = str(
                item.get("exch_seg", "")
            ).lower()

            if exch_seg != "nfo_fo":
                continue

            name = str(
                item.get("name", "")
            ).upper()

            if name != underlying:
                continue

            instrument_type = str(
                item.get("instrumenttype", "")
            ).upper()

            if instrument_type != "OPTIDX":
                continue

            option_symbol = str(
                item.get("symbol", "")
            ).upper()

            if not (
                option_symbol.endswith("CE")
                or option_symbol.endswith("PE")
            ):
                continue

            row = dict(item)

            row["strike"] = pd.to_numeric(
                row.get("strike"),
                errors="coerce",
            )

            row["token"] = str(
                row.get("token", "")
            )

            row["option_type"] = (
                "CE"
                if option_symbol.endswith("CE")
                else "PE"
            )

            rows.append(row)

        df = pd.DataFrame(rows)

        if df.empty:
            return df

        if expiry_date:

            wanted = self.normalize_expiry(
                expiry_date
            )

            if wanted:

                df["expiry_normalized"] = (
                    df["expiry"]
                    .astype(str)
                    .apply(
                        self.normalize_expiry
                    )
                )

                df = df[
                    df["expiry_normalized"]
                    == wanted
                ].copy()

        return df

    # ========================================================
    # EXPIRY NORMALIZATION
    # ========================================================

    @staticmethod
    def normalize_expiry(
        expiry_date
    ):

        if not expiry_date:
            return ""

        value = str(
            expiry_date
        ).strip().upper()

        formats = [
            "%d%b%Y",
            "%d-%b-%Y",
            "%d%b%y",
            "%d-%b-%y",
            "%Y-%m-%d",
        ]

        for fmt in formats:

            try:

                dt = datetime.strptime(
                    value,
                    fmt,
                )

                return dt.strftime(
                    "%Y-%m-%d"
                )

            except ValueError:
                pass

        return ""

    # ========================================================
    # AVAILABLE EXPIRIES
    # ========================================================

    def get_expiries(
        self,
        underlying,
    ):

        df = self.get_option_contracts(
            underlying
        )

        if df.empty:
            return []

        values = []

        for value in df["expiry"].dropna():

            normalized = (
                self.normalize_expiry(
                    value
                )
            )

            if normalized:
                values.append(normalized)

        return sorted(
            list(set(values))
        )

    # ========================================================
    # ATM / NEAR ATM CONTRACTS
    # ========================================================

    def get_near_atm_contracts(
        self,
        underlying,
        expiry_date,
        spot_price,
        strikes_each_side=5,
    ):

        df = self.get_option_contracts(
            underlying,
            expiry_date,
        )

        if df.empty:
            return df

        spot_price = float(
            spot_price
        )

        df["distance"] = (
            df["strike"] - spot_price
        ).abs()

        strikes = (
            df[
                ["strike", "distance"]
            ]
            .drop_duplicates(
                subset=["strike"]
            )
            .sort_values("distance")
            .head(
                strikes_each_side * 2 + 1
            )["strike"]
            .tolist()
        )

        result = df[
            df["strike"].isin(
                strikes
            )
        ].copy()

        return result.sort_values(
            ["strike", "option_type"]
        )

    # ========================================================
    # LIVE MARKET QUOTE
    # ========================================================

    def get_market_quote(
        self,
        contracts_df,
    ):

        if (
            contracts_df is None
            or contracts_df.empty
        ):
            return pd.DataFrame()

        tokens = (
            contracts_df["token"]
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

        if not tokens:
            return pd.DataFrame()

        # SmartAPI market quote supports
        # multiple tokens in one request.

        payload = {
            "mode": "FULL",
            "exchangeTokens": {
                "NFO": tokens[:50]
            },
        }

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "market/v1/quote/"
        )

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=15,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("status"):
            return pd.DataFrame()

        data = result.get(
            "data"
        ) or {}

        fetched = (
            data.get("fetched")
            or []
        )

        if not fetched:
            return pd.DataFrame()

        quote_df = pd.DataFrame(
            fetched
        )

        quote_df["symboltoken"] = (
            quote_df[
                "symbolToken"
            ]
            .astype(str)
        )

        numeric_columns = [
            "ltp",
            "open",
            "high",
            "low",
            "close",
            "tradeVolume",
            "opnInterest",
            "totBuyQuan",
            "totSellQuan",
        ]

        for column in numeric_columns:

            if column in quote_df.columns:

                quote_df[column] = pd.to_numeric(
                    quote_df[column],
                    errors="coerce",
                )

        merged = contracts_df.merge(
            quote_df,
            left_on="token",
            right_on="symboltoken",
            how="left",
        )

        return merged

    # ========================================================
    # OPTION CHAIN
    # ========================================================

    def get_option_chain(
        self,
        underlying,
        expiry_date,
        spot_price,
        strikes_each_side=5,
    ):

        contracts = (
            self.get_near_atm_contracts(
                underlying=underlying,
                expiry_date=expiry_date,
                spot_price=spot_price,
                strikes_each_side=strikes_each_side,
            )
        )

        if contracts.empty:
            return pd.DataFrame()

        return self.get_market_quote(
            contracts
        )

    # ========================================================
    # OPTION GREEKS
    # ========================================================

    def get_option_greeks(
        self,
        underlying,
        expiry_date,
    ):

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "marketData/v1/optionGreek"
        )

        payload = {
            "name": underlying,
            "expirydate": expiry_date,
        }

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("status"):
            return []

        return data.get(
            "data"
        ) or []

    def greeks_dataframe(
        self,
        underlying,
        expiry_date,
    ):

        rows = self.get_option_greeks(
            underlying,
            expiry_date,
        )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            rows
        )

        numeric_columns = [
            "strikePrice",
            "delta",
            "gamma",
            "theta",
            "vega",
            "impliedVolatility",
            "tradeVolume",
        ]

        for column in numeric_columns:

            if column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        return df

    # ========================================================
    # CE / PE SPLIT
    # ========================================================

    def split_calls_puts(
        self,
        df,
    ):

        if (
            df is None
            or df.empty
        ):
            return (
                pd.DataFrame(),
                pd.DataFrame(),
            )

        calls = df[
            df["option_type"]
            .astype(str)
            .str.upper()
            == "CE"
        ].copy()

        puts = df[
            df["option_type"]
            .astype(str)
            .str.upper()
            == "PE"
        ].copy()

        return calls, puts

    # ========================================================
    # PCR
    # ========================================================

    def get_pcr(self):

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "marketData/v1/putCallRatio"
        )

        response = requests.get(
            url,
            headers=self.headers,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("status"):
            return []

        return data.get(
            "data"
        ) or []

    def pcr_dataframe(self):

        rows = self.get_pcr()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            rows
        )

        if "pcr" in df.columns:

            df["pcr"] = pd.to_numeric(
                df["pcr"],
                errors="coerce",
            )

        return df

    # ========================================================
    # OI BUILDUP
    # ========================================================

    def get_oi_buildup(
        self,
        expiry_type="NEAR",
        data_type="Long Built Up",
    ):

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "marketData/v1/OIBuildup"
        )

        payload = {
            "expirytype": expiry_type,
            "datatype": data_type,
        }

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("status"):
            return []

        return data.get(
            "data"
        ) or []

    def get_all_oi_buildup(
        self,
        expiry_type="NEAR",
    ):

        data_types = [
            "Long Built Up",
            "Short Built Up",
            "Short Covering",
            "Long Unwinding",
        ]

        result = {}

        for data_type in data_types:

            result[data_type] = (
                self.get_oi_buildup(
                    expiry_type=expiry_type,
                    data_type=data_type,
                )
            )

        return result

    # ========================================================
    # STRIKE ANALYSIS
    # ========================================================

    def analyze_strikes(
        self,
        df,
        spot_price,
    ):

        if (
            df is None
            or df.empty
        ):
            return {}

        work = df.copy()

        if "strike" not in work.columns:
            return {}

        work["distance"] = (
            work["strike"]
            - float(spot_price)
        ).abs()

        work = work.sort_values(
            "distance"
        )

        return {
            "nearest": work.head(
                20
            )
        }


def create_options_engine(
    jwt_token,
    api_key,
    client_code,
):

    return OptionsEngine(
        jwt_token=jwt_token,
        api_key=api_key,
        client_code=client_code,
    )

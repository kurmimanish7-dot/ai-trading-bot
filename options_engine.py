import requests
import pandas as pd
from datetime import datetime, date


BASE_URL = "https://apiconnect.angelone.in"

SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)


class OptionsEngine:
    """
    Angel One Options Intelligence Engine.

    Supports:
    - NFO index options
    - BFO index options
    - Dynamic future expiries
    - CE / PE contracts
    - Near-ATM option chain
    - LTP / OI / volume
    - Option Greeks
    - PCR
    - OI buildup

    PAPER TRADING ONLY.
    This class does not place orders.
    """

    OPTION_SEGMENTS = {
        "NFO",
        "BFO",
    }

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
    # SAFE NUMBER HELPERS
    # ========================================================

    @staticmethod
    def _to_float(value):
        try:
            if value is None:
                return None

            if isinstance(value, str):
                value = value.strip()

                if not value:
                    return None

            result = float(value)

            if pd.isna(result):
                return None

            return result

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _normalize_token(value):
        """
        Keep Angel One token as a clean string.

        Important:
        Tokens are identifiers, NOT prices.
        Never convert them to float.
        """

        if value is None:
            return ""

        try:
            text = str(value).strip()

            if text.lower() == "nan":
                return ""

            if text.endswith(".0"):
                try:
                    number = float(text)

                    if number.is_integer():
                        return str(
                            int(number)
                        )
                except Exception:
                    pass

            return text

        except Exception:
            return ""

    @staticmethod
    def _normalize_ltp(value):
        """
        Angel One SmartAPI market quote LTP is already
        represented as the actual market price.

        DO NOT divide by 100.
        DO NOT divide by 1000.

        Example:
            156.95 -> 156.95
            103.60 -> 103.60
        """

        result = OptionsEngine._to_float(
            value
        )

        if result is None:
            return None

        if result < 0:
            return None

        return float(result)

    @staticmethod
    def _normalize_strike(value):
        """
        Normalize Angel One option-master strike.

        Angel One scrip master commonly stores option
        strikes in paise/scaled form.

        Examples:
            2600000 -> 26000
            2500000 -> 25000

        Already-normalized values are retained.
        """

        value_float = OptionsEngine._to_float(
            value
        )

        if value_float is None:
            return None

        # Standard Angel One option-master scaling.
        # Index strikes such as 26000 are commonly
        # represented as 2600000.
        if abs(value_float) >= 100000:
            return float(
                value_float / 100.0
            )

        return float(value_float)

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

        if not isinstance(
            data,
            list,
        ):
            return []

        self._scrip_master = data

        return self._scrip_master

    # ========================================================
    # EXPIRY NORMALIZATION
    # ========================================================

    @staticmethod
    def normalize_expiry(expiry_date):

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
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
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
                continue

        return ""

    # ========================================================
    # DISPLAY EXPIRY
    # ========================================================

    @staticmethod
    def display_expiry(expiry_date):

        normalized = (
            OptionsEngine.normalize_expiry(
                expiry_date
            )
        )

        if not normalized:
            return str(expiry_date)

        try:

            dt = datetime.strptime(
                normalized,
                "%Y-%m-%d",
            )

            return dt.strftime(
                "%d %b %Y"
            )

        except ValueError:

            return str(expiry_date)

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

        wanted_name = str(
            underlying
        ).upper().strip()

        rows = []

        for item in data:

            if not isinstance(
                item,
                dict,
            ):
                continue

            segment = str(
                item.get(
                    "exch_seg",
                    "",
                )
            ).upper().strip()

            if segment not in self.OPTION_SEGMENTS:
                continue

            instrument_type = str(
                item.get(
                    "instrumenttype",
                    "",
                )
            ).upper().strip()

            if instrument_type != "OPTIDX":
                continue

            name = str(
                item.get(
                    "name",
                    "",
                )
            ).upper().strip()

            if name != wanted_name:
                continue

            symbol = str(
                item.get(
                    "symbol",
                    "",
                )
            ).upper().strip()

            if not (
                symbol.endswith("CE")
                or symbol.endswith("PE")
            ):
                continue

            row = dict(item)

            row["exch_seg"] = segment

            # ------------------------------------------------
            # FIX 1:
            # Normalize option-master strike.
            # ------------------------------------------------

            row["strike"] = (
                self._normalize_strike(
                    row.get("strike")
                )
            )

            # ------------------------------------------------
            # FIX 2:
            # Token MUST remain string.
            # ------------------------------------------------

            row["token"] = (
                self._normalize_token(
                    row.get("token")
                )
            )

            if not row["token"]:
                continue

            row["symbol"] = symbol

            row["trading_symbol"] = symbol

            row["option_type"] = (
                "CE"
                if symbol.endswith("CE")
                else "PE"
            )

            row["expiry_normalized"] = (
                self.normalize_expiry(
                    row.get("expiry")
                )
            )

            rows.append(row)

        df = pd.DataFrame(
            rows
        )

        if df.empty:
            return df

        # ----------------------------------------------------
        # OPTIONAL EXPIRY FILTER
        # ----------------------------------------------------

        if expiry_date:

            wanted_expiry = (
                self.normalize_expiry(
                    expiry_date
                )
            )

            if wanted_expiry:

                df = df[
                    df[
                        "expiry_normalized"
                    ]
                    == wanted_expiry
                ].copy()

        return df.reset_index(
            drop=True
        )

    # ========================================================
    # ALL FUTURE EXPIRIES
    # ========================================================

    def get_expiries(
        self,
        underlying,
    ):

        df = self.get_option_contracts(
            underlying
        )

        if (
            df.empty
            or "expiry_normalized"
            not in df.columns
        ):
            return []

        today = date.today()

        expiries = []

        for value in (
            df[
                "expiry_normalized"
            ]
            .dropna()
            .unique()
        ):

            try:

                expiry_dt = datetime.strptime(
                    str(value),
                    "%Y-%m-%d",
                ).date()

                if expiry_dt >= today:

                    expiries.append(
                        str(value)
                    )

            except ValueError:

                continue

        return sorted(
            list(
                set(expiries)
            )
        )

    # ========================================================
    # EXPIRY DROPDOWN DATA
    # ========================================================

    def get_expiry_options(
        self,
        underlying,
    ):

        expiries = self.get_expiries(
            underlying
        )

        result = []

        for expiry in expiries:

            result.append(
                {
                    "value": expiry,
                    "label": self.display_expiry(
                        expiry
                    ),
                }
            )

        return result

    # ========================================================
    # NEAR ATM CONTRACTS
    # ========================================================

    def get_near_atm_contracts(
        self,
        underlying,
        expiry_date,
        spot_price,
        strikes_each_side=5,
    ):

        df = self.get_option_contracts(
            underlying=underlying,
            expiry_date=expiry_date,
        )

        if df.empty:
            return df

        try:

            spot = float(
                spot_price
            )

        except (
            TypeError,
            ValueError,
        ):

            return pd.DataFrame()

        if spot <= 0:
            return pd.DataFrame()

        df = df.dropna(
            subset=[
                "strike"
            ]
        ).copy()

        if df.empty:
            return df

        df["distance"] = (
            df["strike"]
            - spot
        ).abs()

        strikes = (
            df[
                [
                    "strike",
                    "distance",
                ]
            ]
            .drop_duplicates(
                subset=[
                    "strike"
                ]
            )
            .sort_values(
                "distance"
            )
            .head(
                strikes_each_side * 2
                + 1
            )[
                "strike"
            ]
            .tolist()
        )

        result = df[
            df["strike"].isin(
                strikes
            )
        ].copy()

        return result.sort_values(
            [
                "strike",
                "option_type",
            ]
        ).reset_index(
            drop=True
        )

    # ========================================================
    # MARKET QUOTE
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

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "market/v1/quote/"
        )

        working_contracts = (
            contracts_df.copy()
        )

        # ----------------------------------------------------
        # Always normalize contract tokens before API call.
        # ----------------------------------------------------

        working_contracts["token"] = (
            working_contracts[
                "token"
            ]
            .map(
                self._normalize_token
            )
        )

        working_contracts = (
            working_contracts[
                working_contracts[
                    "token"
                ] != ""
            ]
            .copy()
        )

        if working_contracts.empty:
            return contracts_df.copy()

        all_quotes = []

        grouped = (
            working_contracts.groupby(
                working_contracts[
                    "exch_seg"
                ]
                .astype(str)
                .str.upper()
            )
        )

        for segment, group in grouped:

            tokens = (
                group[
                    "token"
                ]
                .astype(str)
                .map(
                    self._normalize_token
                )
                .drop_duplicates()
                .tolist()
            )

            tokens = [
                token
                for token in tokens
                if token
            ]

            if not tokens:
                continue

            # SmartAPI batch size.
            for start in range(
                0,
                len(tokens),
                50,
            ):

                batch = tokens[
                    start:start + 50
                ]

                payload = {
                    "mode": "FULL",
                    "exchangeTokens": {
                        segment: batch
                    },
                }

                try:

                    response = requests.post(
                        url,
                        headers=self.headers,
                        json=payload,
                        timeout=15,
                    )

                    response.raise_for_status()

                    result = response.json()

                except Exception:

                    # Keep processing other batches.
                    continue

                if not isinstance(
                    result,
                    dict,
                ):
                    continue

                if not result.get(
                    "status"
                ):
                    continue

                data = (
                    result.get(
                        "data"
                    )
                    or {}
                )

                fetched = (
                    data.get(
                        "fetched"
                    )
                    or []
                )

                if not isinstance(
                    fetched,
                    list,
                ):
                    continue

                if not fetched:
                    continue

                quote_df = pd.DataFrame(
                    fetched
                )

                if quote_df.empty:
                    continue

                # ------------------------------------------------
                # FIX 3:
                # Angel response can expose token using
                # symbolToken. Normalize all possible forms.
                # ------------------------------------------------

                token_source = None

                for candidate in [
                    "symbolToken",
                    "symboltoken",
                    "token",
                ]:

                    if candidate in quote_df.columns:

                        token_source = candidate
                        break

                if token_source is None:
                    continue

                quote_df[
                    "symboltoken"
                ] = (
                    quote_df[
                        token_source
                    ]
                    .map(
                        self._normalize_token
                    )
                )

                # Preserve Angel symbol if available.
                if "tradingSymbol" in quote_df.columns:

                    quote_df[
                        "trading_symbol_quote"
                    ] = (
                        quote_df[
                            "tradingSymbol"
                        ]
                        .astype(str)
                        .str.upper()
                        .str.strip()
                    )

                elif "tradingsymbol" in quote_df.columns:

                    quote_df[
                        "trading_symbol_quote"
                    ] = (
                        quote_df[
                            "tradingsymbol"
                        ]
                        .astype(str)
                        .str.upper()
                        .str.strip()
                    )

                all_quotes.append(
                    quote_df
                )

        if not all_quotes:

            # No quote returned.
            # Return contracts rather than inventing prices.
            result_df = (
                working_contracts.copy()
            )

            result_df["ltp"] = None

            return result_df

        quote_df = pd.concat(
            all_quotes,
            ignore_index=True,
        )

        # --------------------------------------------------------
        # Numeric quote fields.
        # --------------------------------------------------------

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

                quote_df[column] = (
                    pd.to_numeric(
                        quote_df[column],
                        errors="coerce",
                    )
                )

        # --------------------------------------------------------
        # FIX 4:
        # Normalize LTP only as numeric.
        #
        # NEVER divide by 100/1000.
        # --------------------------------------------------------

        if "ltp" in quote_df.columns:

            quote_df["ltp"] = (
                quote_df["ltp"].map(
                    self._normalize_ltp
                )
            )

        # --------------------------------------------------------
        # Remove duplicate quote tokens before merge.
        # This prevents one contract becoming multiple rows.
        # --------------------------------------------------------

        quote_df = (
            quote_df.drop_duplicates(
                subset=[
                    "symboltoken"
                ],
                keep="last",
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------
        # Merge strictly by Angel One token.
        # --------------------------------------------------------

        merged = working_contracts.merge(
            quote_df,
            left_on="token",
            right_on="symboltoken",
            how="left",
            suffixes=(
                "",
                "_quote",
            ),
        )

        # --------------------------------------------------------
        # Ensure LTP column exists even if API did not return it.
        # --------------------------------------------------------

        if "ltp" not in merged.columns:
            merged["ltp"] = None

        # Final LTP normalization.
        merged["ltp"] = (
            merged["ltp"].map(
                self._normalize_ltp
            )
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
    # CE / PE SPLIT
    # ========================================================

    def split_calls_puts(
        self,
        df,
    ):

        if (
            df is None
            or df.empty
            or "option_type"
            not in df.columns
        ):

            return (
                pd.DataFrame(),
                pd.DataFrame(),
            )

        calls = df[
            df[
                "option_type"
            ]
            .astype(str)
            .str.upper()
            == "CE"
        ].copy()

        puts = df[
            df[
                "option_type"
            ]
            .astype(str)
            .str.upper()
            == "PE"
        ].copy()

        return (
            calls,
            puts,
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

        normalized = (
            self.normalize_expiry(
                expiry_date
            )
        )

        if not normalized:
            return []

        payload = {
            "name": str(
                underlying
            ).upper(),
            "expirydate": normalized,
        }

        try:

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

        except Exception:

            return []

        if not isinstance(
            data,
            dict,
        ):
            return []

        if not data.get(
            "status"
        ):
            return []

        return (
            data.get(
                "data"
            )
            or []
        )

    # ========================================================
    # GREEKS DATAFRAME
    # ========================================================

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

                df[column] = (
                    pd.to_numeric(
                        df[column],
                        errors="coerce",
                    )
                )

        return df

    # ========================================================
    # PCR
    # ========================================================

    def get_pcr(self):

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "marketData/v1/putCallRatio"
        )

        try:

            response = requests.get(
                url,
                headers=self.headers,
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

        except Exception:

            return []

        if not isinstance(
            data,
            dict,
        ):
            return []

        if not data.get(
            "status"
        ):
            return []

        return (
            data.get(
                "data"
            )
            or []
        )

    def pcr_dataframe(self):

        rows = self.get_pcr()

        if not rows:

            return pd.DataFrame()

        df = pd.DataFrame(
            rows
        )

        for column in [
            "pcr",
            "putCallRatio",
            "put_call_ratio",
        ]:

            if column in df.columns:

                df[column] = (
                    pd.to_numeric(
                        df[column],
                        errors="coerce",
                    )
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

        try:

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

        except Exception:

            return []

        if not isinstance(
            data,
            dict,
        ):
            return []

        if not data.get(
            "status"
        ):
            return []

        return (
            data.get(
                "data"
            )
            or []
        )

    # ========================================================
    # ALL OI BUILDUP
    # ========================================================

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

            try:

                result[data_type] = (
                    self.get_oi_buildup(
                        expiry_type=expiry_type,
                        data_type=data_type,
                    )
                )

            except Exception:

                result[data_type] = []

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
            or "strike"
            not in df.columns
        ):

            return {}

        try:

            spot = float(
                spot_price
            )

        except (
            TypeError,
            ValueError,
        ):

            return {}

        work = df.copy()

        work["strike"] = (
            pd.to_numeric(
                work["strike"],
                errors="coerce",
            )
        )

        work = work.dropna(
            subset=[
                "strike"
            ]
        )

        if work.empty:
            return {}

        work["distance"] = (
            work["strike"]
            - spot
        ).abs()

        work = work.sort_values(
            "distance"
        )

        return {
            "nearest": work.head(
                20
            )
        }


# ============================================================
# FACTORY
# ============================================================

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

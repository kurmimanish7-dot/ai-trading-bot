import os
import requests
import pandas as pd


# ============================================================
# OPTIONS ENGINE
# PAPER TRADING ONLY
# ============================================================

BASE_URL = "https://apiconnect.angelone.in"


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

    # ========================================================
    # OPTION GREEKS + IV
    # ========================================================

    def get_option_greeks(
        self,
        underlying,
        expiry_date,
    ):
        """
        Returns live option Greeks and IV.

        underlying example:
        NIFTY
        BANKNIFTY
        RELIANCE

        expiry_date example:
        25SEP2026
        """

        url = (
            BASE_URL
            + "/rest/secure/angelbroking/"
            + "marketData/v1/optionGreek"
        )

        payload = {
            "name": str(underlying),
            "expirydate": str(expiry_date),
        }

        try:

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            data = response.json()

            if not data.get("status"):
                return {
                    "status": "ERROR",
                    "message": data.get(
                        "message",
                        "Option Greeks unavailable",
                    ),
                    "data": [],
                }

            rows = data.get(
                "data",
                [],
            )

            return {
                "status": "OK",
                "message": "SUCCESS",
                "data": rows,
            }

        except Exception as e:

            return {
                "status": "ERROR",
                "message": str(e),
                "data": [],
            }

    # ========================================================
    # CONVERT GREEKS TO DATAFRAME
    # ========================================================

    def greeks_dataframe(
        self,
        underlying,
        expiry_date,
    ):

        result = self.get_option_greeks(
            underlying,
            expiry_date,
        )

        if result["status"] != "OK":

            return pd.DataFrame()

        rows = result["data"]

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

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
    # SPLIT CALL / PUT
    # ========================================================

    def split_calls_puts(
        self,
        df,
    ):

        if df is None or df.empty:

            return (
                pd.DataFrame(),
                pd.DataFrame(),
            )

        option_type = (
            df["optionType"]
            .astype(str)
            .str.upper()
        )

        calls = df[
            option_type == "CE"
        ].copy()

        puts = df[
            option_type == "PE"
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

        try:

            response = requests.get(
                url,
                headers=self.headers,
                timeout=10,
            )

            data = response.json()

            if not data.get("status"):

                return {
                    "status": "ERROR",
                    "data": [],
                }

            rows = data.get(
                "data",
                [],
            )

            return {
                "status": "OK",
                "data": rows,
            }

        except Exception as e:

            return {
                "status": "ERROR",
                "message": str(e),
                "data": [],
            }

    # ========================================================
    # PCR DATAFRAME
    # ========================================================

    def pcr_dataframe(self):

        result = self.get_pcr()

        if result["status"] != "OK":

            return pd.DataFrame()

        rows = result.get(
            "data",
            [],
        )

        if not rows:

            return pd.DataFrame()

        return pd.DataFrame(rows)

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

            data = response.json()

            if not data.get("status"):

                return {
                    "status": "ERROR",
                    "data": [],
                }

            return {
                "status": "OK",
                "data": data.get(
                    "data",
                    [],
                ),
            }

        except Exception as e:

            return {
                "status": "ERROR",
                "message": str(e),
                "data": [],
            }

    # ========================================================
    # OI BUILDUP ALL TYPES
    # ========================================================

    def get_all_oi_buildup(
        self,
        expiry_type="NEAR",
    ):

        buildup_types = [
            "Long Built Up",
            "Short Built Up",
            "Short Covering",
            "Long Unwinding",
        ]

        result = {}

        for buildup_type in buildup_types:

            result[buildup_type] = (
                self.get_oi_buildup(
                    expiry_type=expiry_type,
                    data_type=buildup_type,
                )
            )

        return result

    # ========================================================
    # STRIKE ANALYSIS
    # ========================================================

    def analyze_strikes(
        self,
        df,
    ):

        if df is None or df.empty:

            return {
                "status": "NO_DATA",
                "atm": None,
                "call_data": [],
                "put_data": [],
            }

        calls, puts = (
            self.split_calls_puts(df)
        )

        result = {
            "status": "OK",
            "atm": None,
            "call_data": [],
            "put_data": [],
        }

        if not calls.empty:

            result["call_data"] = (
                calls.to_dict(
                    orient="records"
                )
            )

        if not puts.empty:

            result["put_data"] = (
                puts.to_dict(
                    orient="records"
                )
            )

        return result


# ============================================================
# SAFE FACTORY
# ============================================================

def create_options_engine(
    jwt_token,
    api_key,
    client_code,
):

    if not jwt_token:
        return None

    if not api_key:
        return None

    if not client_code:
        return None

    return OptionsEngine(
        jwt_token=jwt_token,
        api_key=api_key,
        client_code=client_code,
    )

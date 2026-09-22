import os
import pytest

from telemetry_engine import TelemetryEngine


def test_market_data_configuration():
    """
    Safe configuration test.
    Does NOT connect to Angel One and does NOT place any order.
    """

    assert os.getenv("SMARTAPI_API_KEY") is not None
    assert os.getenv("SMARTAPI_CLIENT_CODE") is not None
    assert os.getenv("SMARTAPI_PIN") is not None
    assert os.getenv("SMARTAPI_TOTP_SECRET") is not None


def test_paper_trading_is_enabled():
    from config import PAPER_TRADING

    assert PAPER_TRADING is True


def test_telemetry_engine_can_be_imported():
    assert TelemetryEngine is not None

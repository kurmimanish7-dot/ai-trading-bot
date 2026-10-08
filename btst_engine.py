import pandas as pd
import numpy as np

class BTSTMultiTimeframeEngine:
    def __init__(self):
        # 8 timeframes cover honge: 1m (base) + ye 7 resampled intervals
        self.timeframes = ['2min', '5min', '10min', '15min', '30min', '60min', '120min']

    def resample_ohlcv(self, df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """1-minute data ko custom timeframe bars me convert karta hai."""
        agg_rules = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        if 'oi' in df_1m.columns:
            agg_rules['oi'] = 'last'

        df_resampled = df_1m.resample(timeframe, label='right', closed='right').agg(agg_rules)
        df_resampled.dropna(inplace=True)
        return df_resampled

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """EMA, RSI aur Session VWAP calculate karta hai."""
        df = df.copy()

        # EMA 20 & 50
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

        # RSI (14 period)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # Intraday VWAP
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['cum_pv'] = (typical_price * df['volume']).cumsum()
        df['cum_vol'] = df['volume'].cumsum()
        df['vwap'] = df['cum_pv'] / (df['cum_vol'] + 1e-9)

        return df

    def evaluate_btst_confluence(self, df_1m: pd.DataFrame) -> dict:
        """
        Saare 8 timeframes evaluate karke 0 se 100 ke beech confirmation score deta hai.
        Requirement: df_1m ka index pandas DatetimeIndex hona chahiye.
        """
        # Step 1: Base 1m aur sabhi 7 resampled timeframes create karein
        data_store = {'1min': self.compute_indicators(df_1m)}
        for tf in self.timeframes:
            resampled = self.resample_ohlcv(df_1m, tf)
            data_store[tf] = self.compute_indicators(resampled)

        latest_price = df_1m['close'].iloc[-1]
        day_high = df_1m['high'].max()
        day_low = df_1m['low'].min()

        score = 0
        breakdown = {}

        # Metric 1: Macro Trend (120m + 60m) -> 25 Points
        c_120 = data_store['120min']['close'].iloc[-1] > data_store['120min']['ema_20'].iloc[-1]
        c_60 = data_store['60min']['close'].iloc[-1] > data_store['60min']['ema_20'].iloc[-1]
        macro_pass = c_120 and c_60
        breakdown['macro_bullish_120_60m'] = macro_pass
        if macro_pass:
            score += 25

        # Metric 2: Setup Momentum (30m + 15m + 10m) -> 25 Points
        rsi_30m = data_store['30min']['rsi'].iloc[-1]
        vwap_15m = data_store['15min']['close'].iloc[-1] > data_store['15min']['vwap'].iloc[-1]
        ema_10m = data_store['10min']['close'].iloc[-1] > data_store['10min']['ema_20'].iloc[-1]
        setup_pass = (rsi_30m >= 55) and vwap_15m and ema_10m
        breakdown['setup_momentum_pass'] = setup_pass
        if setup_pass:
            score += 25

        # Metric 3: Micro Trigger (5m + 2m + 1m) -> 20 Points
        vol_surge_2m = data_store['2min']['volume'].iloc[-1] > (data_store['2min']['volume'].tail(10).mean() * 1.5)
        vwap_1m = data_store['1min']['close'].iloc[-1] > data_store['1min']['vwap'].iloc[-1]
        trigger_pass = vol_surge_2m and vwap_1m
        breakdown['micro_trigger_pass'] = trigger_pass
        if trigger_pass:
            score += 20

        # Metric 4: Day High Proximity (Within 0.75% of High) -> 15 Points
        pct_from_high = ((day_high - latest_price) / day_high) * 100
        near_high = pct_from_high <= 0.75
        breakdown['near_day_high'] = near_high
        if near_high:
            score += 15

        # Metric 5: OI Long Build-up ya Volume Surge -> 15 Points
        if 'oi' in df_1m.columns:
            day_open_oi = df_1m['oi'].iloc[0]
            current_oi = df_1m['oi'].iloc[-1]
            oi_change_pct = ((current_oi - day_open_oi) / (day_open_oi + 1e-9)) * 100
            price_change_pct = ((latest_price - df_1m['open'].iloc[0]) / df_1m['open'].iloc[0]) * 100
            oi_pass = (price_change_pct > 0.5) and (oi_change_pct > 3.0)
            breakdown['oi_long_buildup'] = oi_pass
            if oi_pass:
                score += 15
        else:
            vol_spike = df_1m['volume'].iloc[-1] > (df_1m['volume'].rolling(30).mean().iloc[-1] * 2.0)
            breakdown['volume_spike'] = vol_spike
            if vol_spike:
                score += 15

        # Decision Output
        is_confirmed = score >= 80
        return {
            'timestamp': str(df_1m.index[-1]),
            'cmp': latest_price,
            'total_score': score,
            'trade_decision': "HIGH CONVICTION BUY" if is_confirmed else "NO TRADE",
            'entry_price': latest_price if is_confirmed else None,
            'stop_loss': round(min(latest_price * 0.985, day_low), 2) if is_confirmed else None,
            'target': round(latest_price * 1.015, 2) if is_confirmed else None,
            'breakdown': breakdown
        }

# backend/tests/test_indicators.py
# Tests for the indicator engine — RSI, MACD, EMA, BB, ATR, Supertrend.

import pytest
import pandas as pd
import numpy as np
from indicators.engine import (
    calculate_ema, calculate_sma, calculate_rsi, calculate_macd,
    calculate_bollinger_bands, calculate_atr, build_features
)

class TestIndicatorEngine:
    @pytest.fixture
    def sample_data(self):
        # Create a simple trend then reverse it
        close_prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11]
        high_prices = [p + 1 for p in close_prices]
        low_prices = [p - 1 for p in close_prices]
        df = pd.DataFrame({
            "close": close_prices,
            "high": high_prices,
            "low": low_prices,
            "volume": [100] * 20
        })
        return df

    def test_calculate_ema(self, sample_data):
        ema = calculate_ema(sample_data, "close", period=5)
        assert len(ema) == 20
        assert not ema.isna().all()

    def test_calculate_rsi(self, sample_data):
        rsi = calculate_rsi(sample_data, "close", period=14)
        assert len(rsi) == 20
        # The first few values should be exactly 100 since it is a pure uptrend
        assert rsi.iloc[14] > 50

    def test_calculate_macd(self, sample_data):
        macd_line, signal_line, histogram = calculate_macd(sample_data, "close", fast=12, slow=26, signal=9)
        assert len(macd_line) == 20
        assert len(signal_line) == 20
        assert len(histogram) == 20

    def test_calculate_bollinger_bands(self, sample_data):
        ub, mb, lb = calculate_bollinger_bands(sample_data, "close", period=10, std_dev=2.0)
        assert len(ub) == 20
        # Wait for rolling window to fill
        assert not np.isnan(mb.iloc[10])

    def test_calculate_atr(self, sample_data):
        atr = calculate_atr(sample_data, period=14)
        assert len(atr) == 20

    def test_build_features(self, sample_data):
        # build_features returns unchanged df if length < 20. Our sample is exactly 20.
        features = build_features(sample_data)
        assert "ema_9" in features.columns
        assert "rsi_14" in features.columns
        assert "supertrend" in features.columns

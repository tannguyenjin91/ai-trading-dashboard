# backend/data/feature_store.py
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from shared.models import MarketBar, FeatureVector
from data.store import DiskDataStore

class FeatureStoreService:
    """
    Pipeline 1: Research / Data Platform
    Calculates and stores technical factors (features) for strategy training and backtesting.
    """
    def __init__(self, store: DiskDataStore):
        self.store = store

    async def calculate_features(self, symbol: str, timeframe: str = "1m") -> Optional[FeatureVector]:
        """Calculates features from recent historical data."""
        df = await self.store.get_recent_candles(symbol, limit=200, timeframe=timeframe)
        if df.empty or len(df) < 50:
            return None

        features = {}
        
        # Simple Moving Averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        
        # RSI (Relative Strength Index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Volatility (ATR-like)
        df['volatility_20'] = df['close'].pct_change().rolling(window=20).std()
        
        latest = df.iloc[-1]
        timestamp = df.index[-1] if hasattr(df.index, 'max') else datetime.now()

        if pd.isna(latest['sma_20']) or pd.isna(latest['rsi_14']):
            return None

        features = {
            "sma_20": float(latest['sma_20']),
            "sma_50": float(latest['sma_50']),
            "rsi_14": float(latest['rsi_14']),
            "volatility": float(latest['volatility_20']),
            "price_to_sma20": float(latest['close'] / latest['sma_20'])
        }

        return FeatureVector(
            symbol=symbol,
            timestamp=timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp,
            features=features
        )

    async def get_feature_at(self, symbol: str, timestamp: datetime) -> Optional[FeatureVector]:
        """Recalculates or retrieves a feature vector for a specific point in time."""
        # For simplicity, we just recalculate from store.
        # In a real system, we'd store these in a dedicated DB.
        return await self.calculate_features(symbol)

# backend/indicators/signals.py
# Generator of deterministic deterministic trading signals using basic technical rules.

import pandas as pd
from typing import Dict, Any, Optional
from loguru import logger

def generate_signals(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Evaluates the most recent row of a feature-enriched DataFrame to produce a signal.
    Returns None if there is no strong signal, or a dict describing the signal (BUY/SELL).
    """
    if df is None or len(df) < 2:
        return None
        
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    # We require indicators to be present
    required_cols = ["ema_9", "ema_21", "rsi_14", "macd_hist", "supertrend_dir"]
    if not all(col in df.columns for col in required_cols):
        return None
        
    # Example logic: Supertrend + MACD crossover combination
    is_supertrend_bullish = last_row["supertrend_dir"] == 1
    is_supertrend_bearish = last_row["supertrend_dir"] == -1
    
    # MACD Zero-line or Signal-line crossovers
    macd_bullish_cross = prev_row["macd_hist"] < 0 and last_row["macd_hist"] > 0
    macd_bearish_cross = prev_row["macd_hist"] > 0 and last_row["macd_hist"] < 0
    
    # Setup Signal Structure
    signal = None
    
    # 1. LONG SIGNAL
    if is_supertrend_bullish and macd_bullish_cross:
        if last_row["rsi_14"] < 70:  # Not overbought
            signal = {
                "action": "LONG",
                "confidence": 80,
                "reason": "MACD Bullish Cross + Supertrend Uplift",
                "price": last_row["close"]
            }
            
    # 2. SHORT SIGNAL
    elif is_supertrend_bearish and macd_bearish_cross:
        if last_row["rsi_14"] > 30:  # Not oversold
            signal = {
                "action": "SHORT",
                "confidence": 80,
                "reason": "MACD Bearish Cross + Supertrend Drop",
                "price": last_row["close"]
            }
            
    if signal:
        logger.info(f"⚡ Signal Generated: {signal['action']} at {signal['price']} ({signal['reason']})")
        
    return signal

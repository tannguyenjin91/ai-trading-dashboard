import pandas as pd
from datetime import time
from typing import Dict, Any, Optional
from loguru import logger
from agent.strategies.base import Strategy, StrategyConfig


class OpeningRangeBreakoutStrategy(Strategy):
    """
    Opening Range Breakout for VN30F futures.
    Captures the directional move following the first 15 mins of the continuous session.
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.or_start = time(9, 15)
        self.or_end = time(9, 30)
        self.or_high: Optional[float] = None
        self.or_low: Optional[float] = None

    @property
    def name(self) -> str:
        return "orb"

    async def generate_signal(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyzes the market state (dataframe) for an ORB signal.
        """
        df = market_state.get("df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            return None

        # 1. Identify today's date and the Opening Range (09:15 - 09:30)
        try:
            today = df.index[-1].date()
            day_data = df[df.index.date == today]
            
            or_data = day_data.between_time(self.or_start, self.or_end)
            
            if or_data.empty:
                return None
                
            self.or_high = float(or_data['high'].max())
            self.or_low = float(or_data['low'].min())
            or_width = self.or_high - self.or_low
        except (AttributeError, IndexError, KeyError) as e:
            logger.error(f"Error calculating ORB range: {e}")
            return None

        # 2. Check for breakout after 09:30
        last_bar = day_data.iloc[-1]
        last_time = last_bar.name.time()
        
        if last_time <= self.or_end:
            return None # Still in the range or before it
            
        # 3. Entry Logic with Volume Confirmation
        avg_volume = day_data['volume'].rolling(20).mean().iloc[-1]
        volume_confirmed = last_bar['volume'] > (avg_volume * 1.5)
        
        # Long Breakout
        if last_bar['close'] > self.or_high and volume_confirmed:
            return {
                "symbol": market_state.get("symbol"),
                "direction": "BUY",
                "action": "LONG",
                "entry": last_bar['close'],
                "stop_loss": self.or_low,
                "take_profit": last_bar['close'] + (or_width * 1.5),
                "confluence_score": 0.8,
                "confluence_factors": ["ORB_BREAKOUT_UP", "VOLUME_CONFIRMED"],
                "rationale": f"Price broke OR High ({self.or_high}) with confirmed volume surge."
            }
            
        # Short Breakout
        if last_bar['close'] < self.or_low and volume_confirmed:
            return {
                "symbol": market_state.get("symbol"),
                "direction": "SELL",
                "action": "SHORT",
                "entry": last_bar['close'],
                "stop_loss": self.or_high,
                "take_profit": last_bar['close'] - (or_width * 1.5),
                "confluence_score": 0.8,
                "confluence_factors": ["ORB_BREAKOUT_DOWN", "VOLUME_CONFIRMED"],
                "rationale": f"Price broke OR Low ({self.or_low}) with confirmed volume surge."
            }

        return None

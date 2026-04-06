# backend/indicators/engine.py
# Pure-Pandas technical indicators engine designed for high performance and no strict library dependencies.

import pandas as pd
import numpy as np


def calculate_ema(df: pd.DataFrame, column: str = "close", period: int = 14) -> pd.Series:
    return df[column].ewm(span=period, adjust=False).mean()


def calculate_sma(df: pd.DataFrame, column: str = "close", period: int = 20) -> pd.Series:
    return df[column].rolling(window=period).mean()


def calculate_rsi(df: pd.DataFrame, column: str = "close", period: int = 14) -> pd.Series:
    delta = df[column].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    # Safe division to avoid infinite RSI
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # Fill cases where loss was 0 with 100
    rsi = rsi.fillna(100)
    
    return rsi


def calculate_macd(df: pd.DataFrame, column: str = "close", fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns MACD line, Signal line, and Histogram."""
    ema_fast = calculate_ema(df, column, fast)
    ema_slow = calculate_ema(df, column, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(df: pd.DataFrame, column: str = "close", period: int = 20, std_dev: float = 2.0):
    sma = calculate_sma(df, column, period)
    std = df[column].rolling(window=period).std()
    
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    return upper_band, sma, lower_band


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    
    atr = true_range.rolling(window=period).mean()
    return atr


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculates Volume Weighted Average Price."""
    v = df["volume"]
    p = (df["high"] + df["low"] + df["close"]) / 3
    return (p * v).cumsum() / v.cumsum()


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Average Directional Index (ADX)."""
    plus_dm = df["high"].diff()
    minus_dm = df["low"].diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = abs(minus_dm)
    
    atr = calculate_atr(df, period)
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period).mean()
    
    return adx


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """
    Calculates the Supertrend indicator line.
    Returns the Supertrend line and the Trend Direction (+1 for uptrend, -1 for downtrend).
    The iterative seed starts from the first bar where ATR is available so a 73-bar window
    still produces a usable last-value instead of reporting Supertrend as missing.
    """
    hl2 = (df["high"] + df["low"]) / 2
    atr = calculate_atr(df, period)

    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)

    final_upperband = basic_upperband.copy()
    final_lowerband = basic_lowerband.copy()

    supertrend = pd.Series(np.nan, index=df.index, dtype=float)
    trend_direction = pd.Series(0, index=df.index, dtype=int)

    first_valid_idx = atr.first_valid_index()
    if first_valid_idx is None:
        return supertrend, trend_direction

    start = df.index.get_loc(first_valid_idx)
    initial_direction = 1 if df["close"].iloc[start] >= hl2.iloc[start] else -1
    trend_direction.iloc[start] = initial_direction
    supertrend.iloc[start] = final_lowerband.iloc[start] if initial_direction == 1 else final_upperband.iloc[start]

    for i in range(start + 1, len(df)):
        prev_upper = final_upperband.iloc[i - 1]
        prev_lower = final_lowerband.iloc[i - 1]
        prev_close = df["close"].iloc[i - 1]

        if pd.isna(prev_upper):
            prev_upper = basic_upperband.iloc[i - 1]
        if pd.isna(prev_lower):
            prev_lower = basic_lowerband.iloc[i - 1]

        if basic_upperband.iloc[i] < prev_upper or prev_close > prev_upper:
            final_upperband.iloc[i] = basic_upperband.iloc[i]
        else:
            final_upperband.iloc[i] = prev_upper

        if basic_lowerband.iloc[i] > prev_lower or prev_close < prev_lower:
            final_lowerband.iloc[i] = basic_lowerband.iloc[i]
        else:
            final_lowerband.iloc[i] = prev_lower

        prev_supertrend = supertrend.iloc[i - 1]
        prev_direction = int(trend_direction.iloc[i - 1] or initial_direction)
        if pd.isna(prev_supertrend):
            prev_supertrend = final_lowerband.iloc[i - 1] if prev_direction == 1 else final_upperband.iloc[i - 1]

        if prev_supertrend == final_upperband.iloc[i - 1]:
            trend_direction.iloc[i] = -1 if df["close"].iloc[i] < final_upperband.iloc[i] else 1
        elif prev_supertrend == final_lowerband.iloc[i - 1]:
            trend_direction.iloc[i] = 1 if df["close"].iloc[i] > final_lowerband.iloc[i] else -1
        else:
            trend_direction.iloc[i] = prev_direction

        supertrend.iloc[i] = final_lowerband.iloc[i] if trend_direction.iloc[i] == 1 else final_upperband.iloc[i]

    return supertrend, trend_direction


def calculate_support_resistance(df: pd.DataFrame, lookback: int = 20, min_touches: int = 2) -> dict:
    """
    Identifies key support and resistance levels from swing highs and lows.
    Uses a pivot point approach scanning for local highs/lows within 'lookback' bars.
    Returns dict with 'supports' and 'resistances' as sorted lists of price levels.
    """
    if len(df) < lookback + 2:
        return {"supports": [], "resistances": []}

    window = df.tail(lookback * 2)
    
    swing_highs = []
    swing_lows = []
    
    # Scan for pivot highs/lows with a 2-bar window on each side
    for i in range(2, len(window) - 2):
        h = window["high"].iloc[i]
        l = window["low"].iloc[i]
        
        # Swing high: highest of 5 bars centered on i
        if h == window["high"].iloc[i-2:i+3].max():
            swing_highs.append(h)
        
        # Swing low: lowest of 5 bars centered on i
        if l == window["low"].iloc[i-2:i+3].min():
            swing_lows.append(l)

    current_price = df["close"].iloc[-1]
    
    # Cluster nearby levels within 0.3% tolerance
    def cluster_levels(levels: list, tol_pct: float = 0.003) -> list:
        if not levels:
            return []
        sorted_levels = sorted(set(levels))
        clustered = []
        base = sorted_levels[0]
        cluster = [base]
        for level in sorted_levels[1:]:
            if abs(level - base) / base < tol_pct:
                cluster.append(level)
            else:
                clustered.append(round(sum(cluster) / len(cluster), 1))
                base = level
                cluster = [level]
        clustered.append(round(sum(cluster) / len(cluster), 1))
        return clustered

    resistances = sorted([l for l in cluster_levels(swing_highs) if l > current_price])[:3]
    supports = sorted([l for l in cluster_levels(swing_lows) if l < current_price], reverse=True)[:3]

    return {"supports": supports, "resistances": resistances}


def calculate_fibonacci(df: pd.DataFrame, lookback: int = 30) -> dict:
    """
    Tính Fibonacci Thoái Lui (Retracement) từ swing high và swing low trong lookback window.

    Quy tắc chuẩn:
    - UPTREND (move từ đáy lên đỉnh): thoái lui ĐI XUỐNG từ đỉnh
        level price = swing_high - ratio × range
        → 0% = đỉnh, 23.6%/38.2%/50%/61.8%/78.6% = vùng hỗ trợ, 100% = đáy

    - DOWNTREND (move từ đỉnh xuống đáy): hồi phục ĐI LÊN từ đáy
        level price = swing_low + ratio × range
        → 0% = đáy, 23.6%/38.2%/50%/61.8%/78.6% = vùng kháng cự, 100% = đỉnh
    """
    if len(df) < lookback:
        return {}

    window = df.tail(lookback)
    swing_high = float(window["high"].max())
    swing_low = float(window["low"].min())
    current_price = float(df["close"].iloc[-1])

    price_range = swing_high - swing_low
    if price_range < 0.01:
        return {}

    # Xác định trend từ hướng di chuyển giá trong lookback (first close vs last close)
    first_close = float(window["close"].iloc[0])
    last_close = float(window["close"].iloc[-1])
    trend = "UP" if last_close > first_close else "DOWN"

    # Fibonacci Thoái Lui chuẩn
    fib_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

    levels = []
    for ratio in fib_ratios:
        if trend == "UP":
            # Uptrend: thoái lui từ ĐỈNH đi xuống — đây là các vùng hỗ trợ khi pull back
            price = round(swing_high - price_range * ratio, 1)
        else:
            # Downtrend: hồi phục từ ĐÁY đi lên — đây là các vùng kháng cự khi bounce
            price = round(swing_low + price_range * ratio, 1)
        levels.append({"level": ratio, "price": price})

    # Vùng Fibonacci gần giá hiện tại nhất
    nearest = min(levels, key=lambda x: abs(x["price"] - current_price))

    return {
        "swing_high": round(swing_high, 1),
        "swing_low": round(swing_low, 1),
        "trend": trend,
        "levels": levels,
        "nearest_level": f"{nearest['level']:.3f} tại {nearest['price']:,.1f}"
    }



def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends all required indicators to the provided OHLCV DataFrame.
    """
    features = df.copy()
    if len(features) < 20:
        return features
        
    features["ema_9"] = calculate_ema(features, "close", 9)
    features["ema_21"] = calculate_ema(features, "close", 21)
    features["rsi_14"] = calculate_rsi(features, "close", 14)
    
    macd_line, signal_line, hist = calculate_macd(features, "close", 12, 26, 9)
    features["macd_line"] = macd_line
    features["macd_signal"] = signal_line
    features["macd_hist"] = hist
    
    ub, mb, lb = calculate_bollinger_bands(features, "close", 20, 2.0)
    features["bb_upper"] = ub
    features["bb_middle"] = mb
    features["bb_lower"] = lb
    
    features["atr_14"] = calculate_atr(features, 14)
    features["vwap"] = calculate_vwap(features)
    features["adx_14"] = calculate_adx(features, 14)
    
    st, st_dir = calculate_supertrend(features, 10, 3.0)
    features["supertrend"] = st
    features["supertrend_dir"] = st_dir
    
    return features


def validate_technical_data(df: pd.DataFrame) -> dict:
    """
    Validates whether the DataFrame has sufficient computed indicators.
    Returns a dict with data_quality level and list of missing indicator groups.
    """
    if df is None or df.empty:
        return {"data_quality": "price_action_only", "missing_indicators": ["all"]}

    last = df.iloc[-1]
    missing = []

    # Check each indicator group
    indicator_checks = {
        "ema": ["ema_9", "ema_21"],
        "rsi": ["rsi_14"],
        "macd": ["macd_line", "macd_signal", "macd_hist"],
        "bollinger": ["bb_upper", "bb_middle", "bb_lower"],
        "atr": ["atr_14"],
        "adx": ["adx_14"],
        "vwap": ["vwap"],
        "supertrend": ["supertrend", "supertrend_dir"],
    }

    for group_name, columns in indicator_checks.items():
        for col in columns:
            if col not in df.columns:
                missing.append(group_name)
                break
            val = last.get(col)
            if val is None or pd.isna(val):
                missing.append(group_name)
                break

    # Remove duplicates
    missing = list(dict.fromkeys(missing))

    if not missing:
        return {"data_quality": "full", "missing_indicators": []}
    elif len(missing) <= 3:
        return {"data_quality": "partial", "missing_indicators": missing}
    else:
        return {"data_quality": "price_action_only", "missing_indicators": missing}

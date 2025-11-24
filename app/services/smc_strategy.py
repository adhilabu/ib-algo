import pandas as pd
import numpy as np
from typing import List, Optional, Tuple, Dict
from enum import Enum
from dataclasses import dataclass, field

class Trend(Enum):
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0

class StructureType(Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"

@dataclass
class Pivot:
    index: int
    price: float
    is_high: bool
    time: pd.Timestamp
    crossed: bool = False
    
@dataclass
class Structure:
    index: int
    price: float
    type: StructureType
    trend: Trend
    time: pd.Timestamp

@dataclass
class OrderBlock:
    top: float
    bottom: float
    mitigation_index: Optional[int]
    bias: Trend
    time: pd.Timestamp
    index: int

@dataclass
class FVG:
    top: float
    bottom: float
    bias: Trend
    time: pd.Timestamp
    index: int
    mitigated: bool = False

@dataclass
class StructureState:
    """Tracks the current state of market structure"""
    # Trend state
    internal_trend: Trend = Trend.NEUTRAL
    swing_trend: Trend = Trend.NEUTRAL
    
    # Internal structure pivots (5-bar)
    last_internal_high: Optional[float] = None
    last_internal_low: Optional[float] = None
    last_internal_high_index: Optional[int] = None
    last_internal_low_index: Optional[int] = None
    internal_high_crossed: bool = False
    internal_low_crossed: bool = False
    
    # Swing structure pivots
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    last_swing_high_index: Optional[int] = None
    last_swing_low_index: Optional[int] = None
    swing_high_crossed: bool = False
    swing_low_crossed: bool = False
    
    # New structures detected (for current bar)
    new_structures: List[Structure] = field(default_factory=list)

class SMCStrategy:
    def __init__(self, swing_length: int = 50, internal_length: int = 5, enable_confluence_filter: bool = True):
        self.swing_length = swing_length
        self.internal_length = internal_length
        self.enable_confluence_filter = enable_confluence_filter
        self.state = StructureState()
        
    def _get_pivots(self, df: pd.DataFrame, length: int) -> Tuple[List[Pivot], List[Pivot]]:
        """
        Detect pivot highs and lows using the LuxAlgo leg logic.
        A pivot high at index i means high[i] is the highest in the range [i+1, i+length].
        This matches: high[size] > ta.highest(size)
        """
        highs = []
        lows = []
        
        if len(df) < length + 1:
            return highs, lows

        for i in range(length, len(df)):
            candidate_idx = i - length
            
            # Check High
            current_window_highs = df['high'].iloc[candidate_idx+1 : i+1]
            candidate_high = df['high'].iloc[candidate_idx]
            
            if candidate_high > current_window_highs.max():
                highs.append(Pivot(
                    candidate_idx, 
                    candidate_high, 
                    True, 
                    df.index[candidate_idx],
                    crossed=False
                ))

            # Check Low
            current_window_lows = df['low'].iloc[candidate_idx+1 : i+1]
            candidate_low = df['low'].iloc[candidate_idx]
            
            if candidate_low < current_window_lows.min():
                lows.append(Pivot(
                    candidate_idx, 
                    candidate_low, 
                    False, 
                    df.index[candidate_idx],
                    crossed=False
                ))
                
        return highs, lows

    def _is_bullish_bar(self, candle: pd.Series) -> bool:
        """
        Confluence filter: Check if candle has bullish bias.
        bullishBar := high - math.max(close, open) > math.min(close, open - low)
        """
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        return upper_wick > lower_wick

    def _is_bearish_bar(self, candle: pd.Series) -> bool:
        """
        Confluence filter: Check if candle has bearish bias.
        bearishBar := high - math.max(close, open) < math.min(close, open - low)
        """
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        return upper_wick < lower_wick

    def update_structure_state(self, df: pd.DataFrame) -> None:
        """
        Update the structure state with the latest bar data.
        This tracks pivots and trend for both internal and swing structures.
        """
        if len(df) < max(self.internal_length, self.swing_length) + 1:
            return
        
        # Clear new structures
        self.state.new_structures = []
        
        # Update internal structure (5-bar)
        self._update_internal_structure(df)
        
        # Update swing structure
        self._update_swing_structure(df)
    
    def _update_internal_structure(self, df: pd.DataFrame) -> None:
        """Update internal structure state (5-bar pivots)"""
        internal_highs, internal_lows = self._get_pivots(df, self.internal_length)
        
        # Check if we have a new internal pivot
        if internal_highs:
            latest_high = internal_highs[-1]
            # Only update if this is a NEW pivot (not previously tracked)
            if (self.state.last_internal_high_index is None or 
                latest_high.index > self.state.last_internal_high_index):
                self.state.last_internal_high = latest_high.price
                self.state.last_internal_high_index = latest_high.index
                self.state.internal_high_crossed = False
        
        if internal_lows:
            latest_low = internal_lows[-1]
            if (self.state.last_internal_low_index is None or 
                latest_low.index > self.state.last_internal_low_index):
                self.state.last_internal_low = latest_low.price
                self.state.last_internal_low_index = latest_low.index
                self.state.internal_low_crossed = False
    
    def _update_swing_structure(self, df: pd.DataFrame) -> None:
        """Update swing structure state"""
        swing_highs, swing_lows = self._get_pivots(df, self.swing_length)
        
        if swing_highs:
            latest_high = swing_highs[-1]
            if (self.state.last_swing_high_index is None or 
                latest_high.index > self.state.last_swing_high_index):
                self.state.last_swing_high = latest_high.price
                self.state.last_swing_high_index = latest_high.index
                self.state.swing_high_crossed = False
        
        if swing_lows:
            latest_low = swing_lows[-1]
            if (self.state.last_swing_low_index is None or 
                latest_low.index > self.state.last_swing_low_index):
                self.state.last_swing_low = latest_low.price
                self.state.last_swing_low_index = latest_low.index
                self.state.swing_low_crossed = False

    def detect_structure_realtime(self, df: pd.DataFrame, use_internal: bool = True) -> List[Structure]:
        """
        Detect structure breaks in real-time on the latest bar.
        Returns list of new Structure objects if CHoCH or BOS is detected.
        
        This matches the PineScript logic:
        - Crossover of pivot level triggers structure detection
        - CHoCH when trend reverses
        - BOS when trend continues
        """
        structures = []
        
        if len(df) < 2:
            return structures
        
        current_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]
        current_close = current_bar['close']
        prev_close = prev_bar['close']
        
        # Apply confluence filter if enabled and using internal structure
        if use_internal and self.enable_confluence_filter:
            bullish_bar = self._is_bullish_bar(current_bar)
            bearish_bar = self._is_bearish_bar(current_bar)
        else:
            bullish_bar = True
            bearish_bar = True
        
        # Select which structure to use
        if use_internal:
            trend = self.state.internal_trend
            last_high = self.state.last_internal_high
            last_low = self.state.last_internal_low
            high_crossed = self.state.internal_high_crossed
            low_crossed = self.state.internal_low_crossed
        else:
            trend = self.state.swing_trend
            last_high = self.state.last_swing_high
            last_low = self.state.last_swing_low
            high_crossed = self.state.swing_high_crossed
            low_crossed = self.state.swing_low_crossed
        
        # Check for Bullish Break (crossover of high)
        if (last_high is not None and 
            not high_crossed and 
            current_close > last_high and 
            prev_close <= last_high and
            bullish_bar):
            
            # Determine structure type
            if trend == Trend.BEARISH:
                struct_type = StructureType.CHOCH
            else:
                struct_type = StructureType.BOS
            
            structure = Structure(
                index=len(df) - 1,
                price=last_high,
                type=struct_type,
                trend=Trend.BULLISH,
                time=df.index[-1]
            )
            structures.append(structure)
            
            # Update state
            if use_internal:
                self.state.internal_trend = Trend.BULLISH
                self.state.internal_high_crossed = True
            else:
                self.state.swing_trend = Trend.BULLISH
                self.state.swing_high_crossed = True
        
        # Check for Bearish Break (crossunder of low)
        if (last_low is not None and 
            not low_crossed and 
            current_close < last_low and 
            prev_close >= last_low and
            bearish_bar):
            
            # Determine structure type
            if trend == Trend.BULLISH:
                struct_type = StructureType.CHOCH
            else:
                struct_type = StructureType.BOS
            
            structure = Structure(
                index=len(df) - 1,
                price=last_low,
                type=struct_type,
                trend=Trend.BEARISH,
                time=df.index[-1]
            )
            structures.append(structure)
            
            # Update state
            if use_internal:
                self.state.internal_trend = Trend.BEARISH
                self.state.internal_low_crossed = True
            else:
                self.state.swing_trend = Trend.BEARISH
                self.state.swing_low_crossed = True
        
        return structures

    def detect_structure(self, df: pd.DataFrame) -> List[Structure]:
        """
        Historical structure detection (for backtesting/analysis).
        This is the original method, kept for compatibility.
        """
        structures = []
        
        swing_highs, swing_lows = self._get_pivots(df, self.swing_length)
        
        if not swing_highs or not swing_lows:
            return structures
        
        is_pivot_high = pd.Series(False, index=df.index)
        is_pivot_low = pd.Series(False, index=df.index)
        
        for p in swing_highs: 
            is_pivot_high.iloc[p.index] = True
        for p in swing_lows: 
            is_pivot_low.iloc[p.index] = True
        
        leg = 0
        trend = Trend.NEUTRAL
        last_swing_high = None
        last_swing_low = None
        
        for i in range(self.swing_length, len(df)):
            pivot_idx = i - self.swing_length
            
            new_leg_high = is_pivot_high.iloc[pivot_idx]
            new_leg_low = is_pivot_low.iloc[pivot_idx]
            
            if new_leg_high:
                leg = -1
                last_swing_high = df['high'].iloc[pivot_idx]
            elif new_leg_low:
                leg = 1
                last_swing_low = df['low'].iloc[pivot_idx]
            
            curr_close = df['close'].iloc[i]
            prev_close = df['close'].iloc[i-1]
            
            # Bullish Break
            if last_swing_high is not None and curr_close > last_swing_high and prev_close <= last_swing_high:
                if trend == Trend.BEARISH:
                    structures.append(Structure(i, last_swing_high, StructureType.CHOCH, Trend.BULLISH, df.index[i]))
                    trend = Trend.BULLISH
                elif trend == Trend.BULLISH or trend == Trend.NEUTRAL:
                    structures.append(Structure(i, last_swing_high, StructureType.BOS, Trend.BULLISH, df.index[i]))
                    trend = Trend.BULLISH
                last_swing_high = None
            
            # Bearish Break
            if last_swing_low is not None and curr_close < last_swing_low and prev_close >= last_swing_low:
                if trend == Trend.BULLISH:
                    structures.append(Structure(i, last_swing_low, StructureType.CHOCH, Trend.BEARISH, df.index[i]))
                    trend = Trend.BEARISH
                elif trend == Trend.BEARISH or trend == Trend.NEUTRAL:
                    structures.append(Structure(i, last_swing_low, StructureType.BOS, Trend.BEARISH, df.index[i]))
                    trend = Trend.BEARISH
                last_swing_low = None
                    
        return structures

    def detect_order_blocks(self, df: pd.DataFrame, structures: List[Structure]) -> List[OrderBlock]:
        """
        Detect Order Blocks based on Structure breaks.
        """
        obs = []
        
        swing_highs, swing_lows = self._get_pivots(df, self.swing_length)
        
        high_pivots = {p.index: p for p in swing_highs}
        low_pivots = {p.index: p for p in swing_lows}
        
        for struct in structures:
            break_index = struct.index
            
            relevant_pivots = []
            if struct.trend == Trend.BULLISH:
                relevant_pivots = [p for p in swing_lows if p.index < break_index]
            else:
                relevant_pivots = [p for p in swing_highs if p.index < break_index]
                
            if not relevant_pivots:
                continue
                
            last_pivot = relevant_pivots[-1]
            leg_range = df.iloc[last_pivot.index : break_index + 1]
            
            if struct.trend == Trend.BULLISH:
                min_idx_rel = leg_range['low'].argmin()
                ob_index = last_pivot.index + min_idx_rel
                ob_candle = df.iloc[ob_index]
                obs.append(OrderBlock(
                    top=ob_candle['high'],
                    bottom=ob_candle['low'],
                    mitigation_index=None,
                    bias=Trend.BULLISH,
                    time=df.index[ob_index],
                    index=ob_index
                ))
            else:
                max_idx_rel = leg_range['high'].argmax()
                ob_index = last_pivot.index + max_idx_rel
                ob_candle = df.iloc[ob_index]
                obs.append(OrderBlock(
                    top=ob_candle['high'],
                    bottom=ob_candle['low'],
                    mitigation_index=None,
                    bias=Trend.BEARISH,
                    time=df.index[ob_index],
                    index=ob_index
                ))
                
        return obs

    def detect_fvg(self, df: pd.DataFrame, auto_threshold: bool = True) -> List[FVG]:
        """
        Detect Fair Value Gaps with enhanced logic matching PineScript.
        
        Bullish FVG: currentLow > last2High AND lastClose > last2High AND barDelta > threshold
        Bearish FVG: currentHigh < last2Low AND lastClose < last2Low AND barDelta > threshold
        """
        fvgs = []
        
        if len(df) < 3:
            return fvgs
        
        # Calculate bar delta percentage for threshold
        if auto_threshold:
            bar_deltas = []
            for i in range(1, len(df)):
                bar_open = df['open'].iloc[i]
                bar_close = df['close'].iloc[i]
                if bar_open != 0:
                    delta_pct = abs((bar_close - bar_open) / bar_open * 100)
                    bar_deltas.append(delta_pct)
            
            if bar_deltas:
                threshold = np.mean(bar_deltas) * 2
            else:
                threshold = 0
        else:
            threshold = 0
            
        for i in range(2, len(df)):
            curr_low = df['low'].iloc[i]
            curr_high = df['high'].iloc[i]
            
            prev_close = df['close'].iloc[i-1]
            prev_open = df['open'].iloc[i-1]
            
            prev2_low = df['low'].iloc[i-2]
            prev2_high = df['high'].iloc[i-2]
            
            # Calculate bar delta for current formation
            if prev_open != 0:
                bar_delta_pct = abs((prev_close - prev_open) / prev_open * 100)
            else:
                bar_delta_pct = 0
            
            # Bullish FVG
            if (curr_low > prev2_high and 
                prev_close > prev2_high and 
                bar_delta_pct > threshold):
                fvgs.append(FVG(
                    top=curr_low,
                    bottom=prev2_high,
                    bias=Trend.BULLISH,
                    time=df.index[i],
                    index=i
                ))
                
            # Bearish FVG
            if (curr_high < prev2_low and 
                prev_close < prev2_low and 
                bar_delta_pct > threshold):
                fvgs.append(FVG(
                    top=prev2_low,
                    bottom=curr_high,
                    bias=Trend.BEARISH,
                    time=df.index[i],
                    index=i
                ))
                
        return fvgs

    def detect_equal_highs_lows(self, df: pd.DataFrame, threshold_atr: float = 0.1) -> Tuple[List[Pivot], List[Pivot]]:
        """
        Detect Equal Highs (EQH) and Equal Lows (EQL).
        """
        eqh = []
        eql = []
        
        swing_highs, swing_lows = self._get_pivots(df, self.swing_length)
        
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().fillna(0)
        
        for i in range(self.swing_length, len(df)):
            current_atr = atr.iloc[i]
            threshold = threshold_atr * current_atr
            
            curr_high = df['high'].iloc[i]
            curr_low = df['low'].iloc[i]
            
            # EQH
            for p in swing_highs:
                if p.index < i and abs(curr_high - p.price) < threshold:
                    eqh.append(Pivot(i, curr_high, True, df.index[i]))
                    break
            
            # EQL
            for p in swing_lows:
                if p.index < i and abs(curr_low - p.price) < threshold:
                    eql.append(Pivot(i, curr_low, False, df.index[i]))
                    break
                    
        return eqh, eql

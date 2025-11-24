import pandas as pd
import numpy as np
from app.services.smc_strategy import SMCStrategy, Trend, StructureType
from datetime import datetime, timedelta

def generate_test_data_with_structure():
    """
    Generate synthetic price data with clear CHoCH and BOS patterns.
    """
    dates = [datetime.now() + timedelta(minutes=i) for i in range(200)]
    prices = []
    
    # Pattern 1: Establish bearish trend
    # Down from 2000 to 1980
    for i in range(30):
        prices.append(2000 - i * 0.7)
    
    # Pattern 2: Small rally (LL - Lower Low still bearish)
    for i in range(15):
        prices.append(1980 + i * 0.4)
    
    # Pattern 3: Continue down (BOS Bearish - break previous low)
    for i in range(25):
        prices.append(1986 - i * 0.5)
    
    # Pattern 4: Strong rally breaking previous high (CHoCH - Bullish)
    for i in range(35):
        prices.append(1973.5 + i * 0.6)
    
    # Pattern 5: Small pullback (HH - Higher High, still bullish)
    for i in range(20):
        prices.append(1994.5 - i * 0.3)
    
    # Pattern 6: Continue up (BOS Bullish)
    for i in range(30):
        prices.append(1988.5 + i * 0.5)
    
    # Pattern 7: Sharp reversal breaking low (CHoCH - Bearish)
    for i in range(25):
        prices.append(2003.5 - i * 0.8)
    
    # Add some noise
    noise = np.random.normal(0, 0.1, len(prices))
    prices = [p + n for p, n in zip(prices, noise)]
    
    df = pd.DataFrame({
        'open': prices,
        'high': [p + abs(np.random.normal(0, 0.3)) for p in prices],
        'low': [p - abs(np.random.normal(0, 0.3)) for p in prices],
        'close': [p + np.random.normal(0, 0.15) for p in prices]
    }, index=dates[:len(prices)])
    
    return df

def test_pivot_detection():
    """Test pivot detection logic"""
    print("="*80)
    print("TEST 1: Pivot Detection")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy(swing_length=10, internal_length=5)
    
    # Test swing pivots
    swing_highs, swing_lows = strategy._get_pivots(df, 10)
    print(f"\n✓ Swing Pivots (10-bar): {len(swing_highs)} Highs, {len(swing_lows)} Lows")
    
    # Test internal pivots
    internal_highs, internal_lows = strategy._get_pivots(df, 5)
    print(f"✓ Internal Pivots (5-bar): {len(internal_highs)} Highs, {len(internal_lows)} Lows")
    
    if swing_highs:
        print(f"\nSample Swing High: Price={swing_highs[0].price:.2f}, Index={swing_highs[0].index}")
    if swing_lows:
        print(f"Sample Swing Low: Price={swing_lows[0].price:.2f}, Index={swing_lows[0].index}")

def test_structure_detection():
    """Test CHoCH and BOS detection"""
    print("\n" + "="*80)
    print("TEST 2: Structure Detection (CHoCH & BOS)")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy(swing_length=10, internal_length=5)
    
    # Historical structure detection
    structures = strategy.detect_structure(df)
    
    print(f"\n✓ Total Structures Detected: {len(structures)}")
    print("\nStructure Breakdown:")
    
    choch_count = sum(1 for s in structures if s.type == StructureType.CHOCH)
    bos_count = sum(1 for s in structures if s.type == StructureType.BOS)
    bullish_count = sum(1 for s in structures if s.trend == Trend.BULLISH)
    bearish_count = sum(1 for s in structures if s.trend == Trend.BEARISH)
    
    print(f"  - CHoCH: {choch_count}")
    print(f"  - BOS: {bos_count}")
    print(f"  - Bullish: {bullish_count}")
    print(f"  - Bearish: {bearish_count}")
    
    print("\nFirst 5 Structures:")
    for i, s in enumerate(structures[:5]):
        print(f"  {i+1}. {s.type.value:5} {s.trend.name:7} @ ${s.price:7.2f} (Bar {s.index})")

def test_realtime_structure():
    """Test real-time structure detection"""
    print("\n" + "="*80)
    print("TEST 3: Real-Time Structure Detection")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy(swing_length=10, internal_length=5, enable_confluence_filter=True)
    
    print("\nSimulating bar-by-bar detection (last 50 bars):")
    structure_count = 0
    
    for i in range(len(df) - 50, len(df)):
        current_df = df.iloc[:i+1]
        
        # Update state
        strategy.update_structure_state(current_df)
        
        # Detect structures on latest bar
        structures = strategy.detect_structure_realtime(current_df, use_internal=True)
        
        if structures:
            for struct in structures:
                structure_count += 1
                current_price = current_df['close'].iloc[-1]
                print(
                    f"  Bar {i}: {struct.type.value} {struct.trend.name} @ ${struct.price:.2f} "
                    f"(Current: ${current_price:.2f})"
                )
    
    print(f"\n✓ Total Structures Detected in Real-Time: {structure_count}")

def test_confluence_filter():
    """Test confluence filter"""
    print("\n" + "="*80)
    print("TEST 4: Confluence Filter")
    print("="*80)
    
    df = generate_test_data_with_structure()
    
    # Test with filter ON
    strategy_filtered = SMCStrategy(swing_length=10, internal_length=5, enable_confluence_filter=True)
    strategy_filtered.update_structure_state(df)
    structures_filtered = strategy_filtered.detect_structure_realtime(df, use_internal=True)
    
    # Test with filter OFF
    strategy_unfiltered = SMCStrategy(swing_length=10, internal_length=5, enable_confluence_filter=False)
    strategy_unfiltered.update_structure_state(df)
    structures_unfiltered = strategy_unfiltered.detect_structure_realtime(df, use_internal=True)
    
    print(f"\n✓ Structures WITH Confluence Filter: {len(structures_filtered)}")
    print(f"✓ Structures WITHOUT Confluence Filter: {len(structures_unfiltered)}")
    print(f"\nFilter removed {len(structures_unfiltered) - len(structures_filtered)} false signals")

def test_order_blocks():
    """Test order block detection"""
    print("\n" + "="*80)
    print("TEST 5: Order Block Detection")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy(swing_length=10, internal_length=5)
    
    structures = strategy.detect_structure(df)
    order_blocks = strategy.detect_order_blocks(df, structures)
    
    print(f"\n✓ Order Blocks Detected: {len(order_blocks)}")
    
    bullish_obs = [ob for ob in order_blocks if ob.bias == Trend.BULLISH]
    bearish_obs = [ob for ob in order_blocks if ob.bias == Trend.BEARISH]
    
    print(f"  - Bullish OBs: {len(bullish_obs)}")
    print(f"  - Bearish OBs: {len(bearish_obs)}")
    
    if order_blocks:
        print("\nFirst 3 Order Blocks:")
        for i, ob in enumerate(order_blocks[:3]):
            print(f"  {i+1}. {ob.bias.name:7} OB: Top=${ob.top:.2f}, Bottom=${ob.bottom:.2f}")

def test_fvg():
    """Test Fair Value Gap detection"""
    print("\n" + "="*80)
    print("TEST 6: Fair Value Gap Detection")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy()
    
    fvgs = strategy.detect_fvg(df, auto_threshold=True)
    
    print(f"\n✓ Fair Value Gaps Detected: {len(fvgs)}")
    
    bullish_fvgs = [f for f in fvgs if f.bias == Trend.BULLISH]
    bearish_fvgs = [f for f in fvgs if f.bias == Trend.BEARISH]
    
    print(f"  - Bullish FVGs: {len(bullish_fvgs)}")
    print(f"  - Bearish FVGs: {len(bearish_fvgs)}")
    
    if fvgs:
        print("\nFirst 3 FVGs:")
        for i, fvg in enumerate(fvgs[:3]):
            gap_size = fvg.top - fvg.bottom
            print(f"  {i+1}. {fvg.bias.name:7} FVG: ${fvg.bottom:.2f} - ${fvg.top:.2f} (Gap: ${gap_size:.2f})")

def test_state_tracking():
    """Test structure state tracking"""
    print("\n" + "="*80)
    print("TEST 7: Structure State Tracking")
    print("="*80)
    
    df = generate_test_data_with_structure()
    strategy = SMCStrategy(swing_length=10, internal_length=5)
    
    # Update with full data
    strategy.update_structure_state(df)
    
    print("\n✓ Current Structure State:")
    print(f"  Internal Trend: {strategy.state.internal_trend.name}")
    print(f"  Swing Trend: {strategy.state.swing_trend.name}")
    
    if strategy.state.last_internal_high:
        print(f"\n  Last Internal High: ${strategy.state.last_internal_high:.2f}")
        print(f"    Crossed: {strategy.state.internal_high_crossed}")
    
    if strategy.state.last_internal_low:
        print(f"  Last Internal Low: ${strategy.state.last_internal_low:.2f}")
        print(f"    Crossed: {strategy.state.internal_low_crossed}")
    
    if strategy.state.last_swing_high:
        print(f"\n  Last Swing High: ${strategy.state.last_swing_high:.2f}")
        print(f"    Crossed: {strategy.state.swing_high_crossed}")
    
    if strategy.state.last_swing_low:
        print(f"  Last Swing Low: ${strategy.state.last_swing_low:.2f}")
        print(f"    Crossed: {strategy.state.swing_low_crossed}")

def run_all_tests():
    """Run all verification tests"""
    print("\n" + "█"*80)
    print("  SMC STRATEGY VERIFICATION TEST SUITE")
    print("█"*80 + "\n")
    
    test_pivot_detection()
    test_structure_detection()
    test_realtime_structure()
    test_confluence_filter()
    test_order_blocks()
    test_fvg()
    test_state_tracking()
    
    print("\n" + "█"*80)
    print("  ALL TESTS COMPLETED")
    print("█"*80 + "\n")

if __name__ == "__main__":
    run_all_tests()

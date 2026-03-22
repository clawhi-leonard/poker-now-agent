"""
Test PLO betting logic
"""

from plo_betting import calculate_pot_limit_max_bet, plo_bet_sizing, plo_preflop_strength, plo_fold_call_thresholds, is_wet_plo_board

def test_pot_limit_calculations():
    """Test pot limit max bet calculations"""
    print("🎯 Testing Pot Limit Calculations")
    print("=" * 40)
    
    scenarios = [
        {"pot": 100, "call": 0, "desc": "Simple pot bet"},
        {"pot": 100, "call": 20, "desc": "Pot bet with call"},
        {"pot": 50, "call": 30, "desc": "Big call vs small pot"},
        {"pot": 200, "call": 50, "stack": 150, "desc": "Stack limited"},
    ]
    
    for scenario in scenarios:
        max_bet = calculate_pot_limit_max_bet(
            scenario["pot"], 
            scenario.get("call", 0),
            scenario.get("stack", None)
        )
        
        print(f"   {scenario['desc']}: pot={scenario['pot']}, call={scenario.get('call', 0)} -> max bet={max_bet}")

def test_plo_bet_sizing():
    """Test PLO bet sizing for different contexts"""
    print("\n🎲 Testing PLO Bet Sizing")
    print("=" * 40)
    
    pot = 100
    bb = 10
    my_stack = 1000
    
    contexts = [
        ("value", 75, "Strong value hand"),
        ("value", 60, "Medium value hand"), 
        ("bluff", 25, "Bluff attempt"),
        ("cbet", 45, "Continuation bet"),
        ("protection", 65, "Protection bet"),
    ]
    
    for context, equity, desc in contexts:
        bet_size = plo_bet_sizing(context, equity, pot, ["As", "Kc", "2h"], "TAG", bb, 0, my_stack)
        pot_percentage = (bet_size / pot) * 100
        
        print(f"   {desc}: {context} with {equity}% equity -> bet {bet_size} ({pot_percentage:.0f}% pot)")

def test_plo_preflop_hands():
    """Test PLO preflop hand evaluation"""
    print("\n🃏 Testing PLO Preflop Hand Evaluation")
    print("=" * 40)
    
    test_hands = [
        (["As", "Ad", "Kh", "Kc"], "Premium double suited aces"),
        (["As", "Ah", "2s", "3h"], "Aces unsuited with trash"),
        (["Ts", "Js", "Qd", "Kc"], "Broadway straight potential"),
        (["9s", "9h", "Td", "Jc"], "Pair with straight cards"),
        (["2s", "3d", "7h", "Kc"], "Random trash hand"),
        (["Ts", "Js", "Ts", "9s"], "Double suited rundown"),  # Error: duplicate card
    ]
    
    for hand, desc in test_hands:
        try:
            strength = plo_preflop_strength(hand)
            print(f"   {' '.join(hand):>15} | {strength:2d}/100 | {desc}")
        except Exception as e:
            print(f"   {' '.join(hand):>15} | ERROR | {desc} ({e})")

def test_board_wetness():
    """Test PLO board wetness evaluation"""
    print("\n💧 Testing PLO Board Wetness")
    print("=" * 40)
    
    boards = [
        (["2h", "7c", "Ks"], "Rainbow dry board"),
        (["9h", "8s", "7c"], "Straight draws"),
        (["Th", "9h", "2s"], "Flush + straight draws"),
        (["As", "Ah", "2d"], "Paired aces (dry)"),
        (["Kh", "Qc", "Jh"], "High connected flush draw"),
    ]
    
    for board, desc in boards:
        is_wet = is_wet_plo_board(board)
        status = "WET" if is_wet else "DRY"
        print(f"   {' '.join(board):>12} | {status:>3} | {desc}")

def test_plo_thresholds():
    """Test PLO fold/call thresholds"""
    print("\n📊 Testing PLO Fold/Call Thresholds")
    print("=" * 40)
    
    positions = ["early", "middle", "late"]
    
    for pos in positions:
        for opponents in [1, 2, 3]:
            fold_thresh, call_thresh = plo_fold_call_thresholds(pos, opponents)
            print(f"   {pos:>6} vs {opponents} opp: fold<{fold_thresh}%, call>{call_thresh}%")

def main():
    """Run all PLO betting tests"""
    test_pot_limit_calculations()
    test_plo_bet_sizing()
    test_plo_preflop_hands()
    test_board_wetness()
    test_plo_thresholds()
    
    print("\n" + "=" * 50)
    print("✅ PLO BETTING LOGIC TESTS COMPLETE")
    print("🎯 Ready to integrate into main bot system")
    print("=" * 50)

if __name__ == "__main__":
    main()
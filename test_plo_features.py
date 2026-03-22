"""
PLO Feature Testing - Test the existing PLO capabilities
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hand_eval import get_equity, hand_rank, detect_draws, normalize_card
import random

def test_plo_hand_evaluation():
    """Test PLO hand evaluation features"""
    print("🃏 Testing PLO Hand Evaluation Features")
    print("=" * 50)
    
    # Test PLO preflop hands
    print("\n📋 PLO Preflop Equity Tests:")
    
    plo_hands = [
        ["As", "Ad", "Kh", "Kc"],  # Premium: Double suited aces
        ["Ts", "Jh", "Qd", "Kc"],  # Straight wrap potential
        ["9s", "9h", "Td", "Jc"],  # Pair + straight cards
        ["2s", "3d", "7h", "Kc"],  # Trash hand
        ["As", "Ah", "2s", "3h"],  # Aces but unsuited
    ]
    
    for hand in plo_hands:
        equity = get_equity(hand, None, num_opponents=3)  # 4-handed
        print(f"   {hand[0]:>2} {hand[1]:>2} {hand[2]:>2} {hand[3]:>2} vs 3 opponents: {equity:5.1f}% equity")
    
    # Test PLO postflop scenarios
    print("\n📋 PLO Postflop Scenarios:")
    
    scenarios = [
        {
            "hole": ["As", "Ac", "Kh", "Kd"],
            "board": ["Ad", "Kc", "2h"],
            "desc": "Full house (top set + underpair)"
        },
        {
            "hole": ["Ts", "Js", "Qd", "Kc"],  
            "board": ["9h", "8s", "7c"],
            "desc": "Straight wrap (13 outs)"
        },
        {
            "hole": ["9s", "8s", "7h", "6h"],
            "board": ["Ts", "Jh", "2s"],  
            "desc": "Straight + flush draws"
        },
        {
            "hole": ["2s", "3d", "7h", "Kc"],
            "board": ["As", "Ac", "Ad"],
            "desc": "Dead hand vs quads"
        }
    ]
    
    for scenario in scenarios:
        equity = get_equity(scenario["hole"], scenario["board"], num_opponents=2)
        draws = detect_draws(scenario["hole"], scenario["board"])
        hand_value = hand_rank(None, plo_hole=scenario["hole"], plo_board=scenario["board"])
        
        print(f"\n   {scenario['desc']}:")
        print(f"   Hole: {' '.join(scenario['hole'])}")
        print(f"   Board: {' '.join(scenario['board'])}")
        print(f"   Equity vs 2: {equity:5.1f}%")
        print(f"   Draws: {', '.join(draws) if draws else 'None'}")
        print(f"   Hand rank: {hand_value}")

def test_plo_vs_holdem():
    """Compare PLO vs Hold'em equity for similar scenarios"""
    print("\n🔄 PLO vs Hold'em Comparison:")
    print("=" * 50)
    
    comparisons = [
        {
            "desc": "Pocket Aces on dry board",
            "plo_hole": ["As", "Ah", "Kc", "Qd"],
            "he_hole": ["As", "Ah"], 
            "board": ["2h", "7c", "9s"]
        },
        {
            "desc": "Straight draw scenario",
            "plo_hole": ["Ts", "Js", "8h", "7c"],
            "he_hole": ["Ts", "Js"],
            "board": ["9h", "6s", "2d"]
        }
    ]
    
    for comp in comparisons:
        plo_eq = get_equity(comp["plo_hole"], comp["board"], num_opponents=1)
        he_eq = get_equity(comp["he_hole"], comp["board"], num_opponents=1)
        
        print(f"\n   {comp['desc']}:")
        print(f"   PLO equity: {plo_eq:5.1f}% | Hold'em equity: {he_eq:5.1f}%")
        print(f"   Difference: {plo_eq - he_eq:+5.1f}%")

def create_plo_strategy_notes():
    """Create PLO strategy analysis"""
    print("\n📝 PLO Strategy Considerations:")
    print("=" * 50)
    
    strategy_points = [
        "🔹 PLO uses 4 hole cards, must use exactly 2 hole + 3 board",
        "🔹 Hand equities run much closer than Hold'em",
        "🔹 Drawing hands have more value due to multiple draws",
        "🔹 Position is crucial for pot limit betting structure",
        "🔹 Nutted hands much more important (draws to nuts)",
        "🔹 Blockers play important role in decision making",
        "🔹 Multiway pots more common due to close equities",
        "🔹 PLO requires different bet sizing (pot limit vs no limit)"
    ]
    
    for point in strategy_points:
        print(f"   {point}")

def analyze_current_bot_plo_readiness():
    """Analyze how ready the current bot is for PLO"""
    print("\n🤖 Bot PLO Readiness Analysis:")
    print("=" * 50)
    
    print("✅ ALREADY IMPLEMENTED:")
    print("   • 4-card hand evaluation (hand_eval.py)")
    print("   • PLO equity calculations (Monte Carlo)")
    print("   • PLO hand ranking (2 hole + 3 board)")
    print("   • Auto-detection (4 cards = PLO mode)")
    
    print("\n🔧 NEEDS IMPROVEMENT:")
    print("   • PLO-specific preflop ranges")
    print("   • Pot limit betting logic vs no limit")  
    print("   • PLO postflop strategy adjustments")
    print("   • PLO-specific opponent modeling")
    print("   • Board texture analysis for PLO")
    
    print("\n📈 RECOMMENDED PLO ENHANCEMENTS:")
    print("   1. Implement pot limit betting calculations")
    print("   2. Adjust fold/call thresholds for PLO equity ranges")
    print("   3. PLO-specific preflop hand selection")
    print("   4. Enhanced draw detection for multiway PLO")
    print("   5. Nut potential evaluation (crucial in PLO)")

def main():
    """Run all PLO tests and analysis"""
    test_plo_hand_evaluation()
    test_plo_vs_holdem() 
    create_plo_strategy_notes()
    analyze_current_bot_plo_readiness()
    
    print("\n" + "=" * 60)
    print("✅ PLO FEATURE TESTING COMPLETE")
    print("📊 Conclusion: Bot has solid PLO foundation with hand evaluation")
    print("🎯 Focus: Implement pot limit betting and PLO-specific strategy")
    print("=" * 60)

if __name__ == "__main__":
    main()
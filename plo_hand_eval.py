"""
PLO Hand Evaluation Engine
Pot Limit Omaha uses 4 hole cards, must use exactly 2 hole + 3 board
"""
import random
from itertools import combinations

# Rank ordering for card evaluation
RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}

def normalize_card(card_str):
    """Convert card string to standard format"""
    card_str = card_str.strip().upper()
    if len(card_str) == 2:
        return card_str
    if len(card_str) == 3 and card_str[:2] == "10":
        return "T" + card_str[2]
    return card_str

def plo_preflop_strength(hole_cards):
    """
    Evaluate PLO preflop hand strength (4 cards)
    Returns strength score 0-100
    """
    if len(hole_cards) != 4:
        return 0
    
    cards = [normalize_card(c) for c in hole_cards]
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]
    
    strength = 0
    
    # 1. Pairs (most important in PLO preflop)
    rank_counts = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    
    pairs = [rank for rank, count in rank_counts.items() if count >= 2]
    if pairs:
        for pair_rank in pairs:
            if pair_rank == 'A':
                strength += 35  # Pocket Aces
            elif pair_rank == 'K':
                strength += 25  # Pocket Kings  
            elif pair_rank in ['Q', 'J']:
                strength += 15  # Premium pairs
            elif pair_rank in ['T', '9']:
                strength += 10  # Medium pairs
            else:
                strength += 5   # Small pairs
    
    # 2. Suited combinations (flush potential)
    suit_counts = {}
    for suit in suits:
        suit_counts[suit] = suit_counts.get(suit, 0) + 1
    
    # Double suited (two 2-card suited combos)
    suited_combos = sum(1 for count in suit_counts.values() if count >= 2)
    if suited_combos >= 2:
        strength += 20  # Double suited
    elif max(suit_counts.values()) >= 2:
        strength += 10  # Single suited
    
    # 3. Connected cards (straight potential)
    rank_values = []
    for rank in ranks:
        if rank.isdigit():
            rank_values.append(int(rank))
        else:
            rank_values.append(RANK_ORDER.get(rank, 0))
    
    rank_values.sort()
    
    # Check for connectivity (cards within range for straights)
    if len(rank_values) >= 4:
        span = rank_values[-1] - rank_values[0]
        if span <= 4:  # All cards within 5-card straight range
            strength += 25
        elif span <= 6:  # Good connectivity
            strength += 15
        elif span <= 8:  # Some connectivity  
            strength += 8
    
    # 4. High card strength
    high_count = sum(1 for r in rank_values if r >= 10)
    strength += high_count * 3
    
    # 5. Aces bonus (very important in PLO)
    ace_count = ranks.count('A')
    if ace_count >= 2:
        strength += 15  # Double aces
    elif ace_count == 1:
        strength += 5   # Single ace
    
    return min(strength, 100)

def plo_best_hand(hole_cards, board_cards):
    """
    Find best 5-card poker hand using exactly 2 hole + 3 board cards
    Returns hand strength score and description
    """
    if len(hole_cards) != 4 or len(board_cards) < 3:
        return 0, "insufficient cards"
    
    hole = [normalize_card(c) for c in hole_cards]
    board = [normalize_card(c) for c in board_cards]
    
    best_strength = 0
    best_description = ""
    
    # Try all combinations of 2 hole cards with 3 board cards
    for hole_combo in combinations(hole, 2):
        for board_combo in combinations(board, 3):
            hand = list(hole_combo) + list(board_combo)
            strength, desc = evaluate_5card_hand(hand)
            if strength > best_strength:
                best_strength = strength
                best_description = desc
    
    return best_strength, best_description

def evaluate_5card_hand(hand):
    """Evaluate a 5-card poker hand, return (strength, description)"""
    if len(hand) != 5:
        return 0, "invalid hand"
    
    # Parse ranks and suits
    ranks = []
    suits = []
    for card in hand:
        rank = card[0]
        suit = card[1]
        ranks.append(RANK_ORDER.get(rank, 0))
        suits.append(suit)
    
    ranks.sort(reverse=True)
    
    # Count rank frequencies
    rank_counts = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    
    counts = sorted(rank_counts.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight = is_straight_check(ranks)
    
    # Hand rankings (higher = better)
    if is_straight and is_flush:
        if ranks == [14, 13, 12, 11, 10]:  # Royal flush
            return 900 + max(ranks), "Royal Flush"
        else:
            return 800 + max(ranks), "Straight Flush"
    elif counts == [4, 1]:
        return 700 + max(ranks), "Four of a Kind"
    elif counts == [3, 2]:
        return 600 + max(ranks), "Full House"
    elif is_flush:
        return 500 + max(ranks), "Flush"
    elif is_straight:
        return 400 + max(ranks), "Straight"
    elif counts == [3, 1, 1]:
        return 300 + max(ranks), "Three of a Kind"
    elif counts == [2, 2, 1]:
        return 200 + max(ranks), "Two Pair"
    elif counts == [2, 1, 1, 1]:
        return 100 + max(ranks), "One Pair"
    else:
        return max(ranks), "High Card"

def is_straight_check(ranks):
    """Check if sorted ranks form a straight"""
    if len(ranks) != 5:
        return False
    
    # Check regular straight
    if ranks == sorted(ranks, reverse=True) and ranks[0] - ranks[4] == 4:
        return True
    
    # Check wheel straight (A-2-3-4-5)
    if set(ranks) == {14, 5, 4, 3, 2}:
        return True
    
    return False

def plo_equity_vs_random(my_hole, board, num_opponents=1, iterations=1000):
    """
    Calculate PLO equity against random opponent hands
    """
    if len(my_hole) != 4:
        return 0.0
    
    # Create deck without known cards
    deck = []
    for rank in "23456789TJQKA":
        for suit in "hdsc":
            deck.append(rank + suit)
    
    # Remove known cards
    my_normalized = [normalize_card(c) for c in my_hole]
    board_normalized = [normalize_card(c) for c in board]
    for card in my_normalized + board_normalized:
        if card in deck:
            deck.remove(card)
    
    wins = 0
    total = 0
    
    for _ in range(iterations):
        # Simulate random opponent hands and complete board
        random.shuffle(deck)
        deck_copy = deck.copy()
        
        # Deal opponent hands (4 cards each)
        opp_hands = []
        for _ in range(num_opponents):
            opp_hand = deck_copy[:4]
            deck_copy = deck_copy[4:]
            opp_hands.append(opp_hand)
        
        # Complete the board if needed
        complete_board = board_normalized.copy()
        cards_needed = 5 - len(complete_board)
        if cards_needed > 0:
            complete_board.extend(deck_copy[:cards_needed])
        
        # Evaluate all hands
        my_strength, _ = plo_best_hand(my_normalized, complete_board)
        
        best_opp_strength = 0
        for opp_hand in opp_hands:
            opp_strength, _ = plo_best_hand(opp_hand, complete_board)
            best_opp_strength = max(best_opp_strength, opp_strength)
        
        if my_strength > best_opp_strength:
            wins += 1
        total += 1
    
    return wins / total if total > 0 else 0.0

def plo_position_strategy(position, hole_cards):
    """
    PLO position-based strategy recommendations
    """
    strength = plo_preflop_strength(hole_cards)
    
    if position in ["UTG", "UTG+1"]:  # Early position - tighter
        if strength >= 75:
            return "raise"
        elif strength >= 55:
            return "call"
        else:
            return "fold"
    elif position in ["MP", "MP+1"]:  # Middle position
        if strength >= 70:
            return "raise"  
        elif strength >= 45:
            return "call"
        else:
            return "fold"
    else:  # Late position (CO, BTN) - looser
        if strength >= 65:
            return "raise"
        elif strength >= 35:
            return "call"
        else:
            return "fold"

def plo_pot_limit_max_bet(pot_size, call_amount, my_stack):
    """Calculate maximum pot limit bet"""
    # In pot limit: max bet = pot size + call amount + call amount again
    max_bet = pot_size + (2 * call_amount)
    return min(max_bet, my_stack)

# Quick test
if __name__ == "__main__":
    # Test with sample PLO hand
    hole = ["As", "Ah", "Kd", "Qc"]  # Premium PLO hand
    strength = plo_preflop_strength(hole)
    print(f"PLO preflop strength: {strength}/100")
    
    board = ["Ac", "7h", "2d"]
    best_strength, desc = plo_best_hand(hole, board)
    print(f"Best hand: {desc} (strength: {best_strength})")
    
    equity = plo_equity_vs_random(hole, board, num_opponents=1, iterations=500)
    print(f"Equity vs 1 opponent: {equity:.1%}")
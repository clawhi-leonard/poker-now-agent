"""
PLO Betting Logic - Pot Limit Omaha specific betting calculations
"""

def calculate_pot_limit_max_bet(pot_size, call_amount=0, my_stack=None):
    """
    Calculate maximum pot limit bet amount
    In PLO: Max bet = Size of pot after calling + any call amount required
    """
    # In pot limit: max bet = pot after calling + call needed
    # Example: pot=100, call=20 -> can bet up to 140 (100+20+20)
    max_pot_limit_bet = pot_size + (2 * call_amount)
    
    # Can't bet more than stack
    if my_stack is not None:
        max_pot_limit_bet = min(max_pot_limit_bet, my_stack)
    
    return max_pot_limit_bet

def plo_bet_sizing(context, equity, pot_size, board, style, bb, call_amount=0, my_stack=None):
    """
    PLO-specific bet sizing that respects pot limit rules
    """
    
    max_bet = calculate_pot_limit_max_bet(pot_size, call_amount, my_stack)
    
    # PLO betting strategy adjustments
    if context == "value":
        # PLO: Value betting tends to be larger due to close equities
        if equity >= 70:  # Strong value
            target_size = pot_size * 0.8  # 80% pot
        else:  # Medium value
            target_size = pot_size * 0.6  # 60% pot
            
    elif context == "bluff":
        # PLO: Smaller bluffs often work due to multiway nature
        target_size = pot_size * 0.5  # 50% pot
        
    elif context == "cbet":
        # PLO: C-bets need to be bigger on wet boards (more draws possible)
        if board and len(board) >= 3:
            # Estimate board wetness for PLO (more draws possible)
            is_wet = is_wet_plo_board(board)
            target_size = pot_size * (0.7 if is_wet else 0.5)
        else:
            target_size = pot_size * 0.6
            
    elif context == "protection":
        # PLO: Protection bets need to be larger (more draws)
        target_size = pot_size * 0.9
        
    else:  # Default
        target_size = pot_size * 0.6
    
    # Apply pot limit restriction
    final_bet = min(target_size, max_bet)
    
    # Minimum bet (can't bet less than big blind)
    final_bet = max(final_bet, bb)
    
    return int(final_bet)

def is_wet_plo_board(board):
    """
    Determine if board is wet for PLO (more loose than Hold'em)
    PLO has more drawing combinations, so boards are "wetter"
    """
    if len(board) < 3:
        return False
        
    # Extract ranks and suits
    ranks = [card[0] for card in board]
    suits = [card[1] for card in board]
    
    # Convert face cards to numbers
    rank_map = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
    numeric_ranks = []
    for r in ranks:
        if r.isdigit():
            numeric_ranks.append(int(r))
        else:
            numeric_ranks.append(rank_map.get(r, 0))
    
    # Check for wet conditions
    # 1. Two suited cards (more flush draws in PLO)
    suit_counts = {}
    for suit in suits:
        suit_counts[suit] = suit_counts.get(suit, 0) + 1
    if max(suit_counts.values()) >= 2:
        return True
    
    # 2. Connected ranks (more straight draws in PLO)
    sorted_ranks = sorted(numeric_ranks)
    for i in range(len(sorted_ranks) - 1):
        if sorted_ranks[i+1] - sorted_ranks[i] <= 2:  # Within 2 ranks
            return True
    
    # 3. Medium ranks (7-T) create more action
    medium_count = sum(1 for r in numeric_ranks if 7 <= r <= 10)
    if medium_count >= 2:
        return True
    
    return False

def plo_preflop_strength(hole_cards):
    """
    Evaluate PLO preflop hand strength
    Returns strength score 0-100
    """
    if len(hole_cards) != 4:
        return 0
    
    strength = 0
    
    # Check for pairs
    ranks = [card[0] for card in hole_cards]
    rank_counts = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    
    # Premium pairs (AA, KK)
    if 'A' in rank_counts and rank_counts['A'] >= 2:
        strength += 40
    elif 'K' in rank_counts and rank_counts['K'] >= 2:
        strength += 30
    elif any(count >= 2 for count in rank_counts.values()):
        # Other pairs
        strength += 15
    
    # Check for suited cards
    suits = [card[1] for card in hole_cards]
    suit_counts = {}
    for suit in suits:
        suit_counts[suit] = suit_counts.get(suit, 0) + 1
    
    # Double suited (best)
    if len([s for s in suit_counts.values() if s >= 2]) >= 2:
        strength += 25
    # Single suited
    elif max(suit_counts.values()) >= 2:
        strength += 15
    
    # Check for connectedness
    rank_values = []
    for rank in ranks:
        if rank.isdigit():
            rank_values.append(int(rank))
        elif rank == 'T':
            rank_values.append(10)
        elif rank == 'J':
            rank_values.append(11)
        elif rank == 'Q':
            rank_values.append(12)
        elif rank == 'K':
            rank_values.append(13)
        elif rank == 'A':
            rank_values.append(14)
    
    rank_values.sort()
    
    # Connected hands get bonuses
    if len(rank_values) >= 4:
        if rank_values[3] - rank_values[0] <= 4:  # Within 5 ranks
            strength += 20
        elif rank_values[3] - rank_values[0] <= 6:  # Within 7 ranks
            strength += 10
    
    # High cards bonus
    high_count = sum(1 for r in rank_values if r >= 10)
    strength += high_count * 3
    
    return min(strength, 100)

def plo_fold_call_thresholds(position, num_opponents):
    """
    PLO-specific fold/call thresholds (tighter than Hold'em due to close equities)
    """
    base_fold = 35  # Higher than Hold'em (was ~30)
    base_call = 45  # Higher than Hold'em (was ~40)
    
    # Position adjustments (smaller than Hold'em)
    if position == "early":
        fold_threshold = base_fold + 5
        call_threshold = base_call + 5
    elif position == "middle":
        fold_threshold = base_fold + 2
        call_threshold = base_call + 2
    else:  # late/button
        fold_threshold = base_fold - 2
        call_threshold = base_call - 2
    
    # Multi-way adjustments (more important in PLO)
    if num_opponents > 2:
        fold_threshold += 3 * (num_opponents - 2)
        call_threshold += 3 * (num_opponents - 2)
    
    return fold_threshold, call_threshold
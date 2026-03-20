"""
Strategy v27.0 Integration - Enhanced GTO Concepts
Key improvements to integrate into multi_bot.py

1. Position-based 3-betting frequencies
2. Advanced board texture granularity  
3. Stack depth awareness
4. Opponent-specific exploitative adjustments
5. ICM-aware tournament concepts
"""

def enhanced_bot_decide_v27(state, profile, opponent_model=None):
    """
    Enhanced decision engine with v27 improvements:
    - Position-specific opening and 3-bet ranges
    - Granular board texture analysis 
    - Stack depth considerations
    - Advanced opponent exploitation
    """
    
    # Core state extraction (same as v24)
    my_stack = 1000
    actions_str = " ".join(state.get("actions", []))
    can_check = "Check" in actions_str
    can_raise = "Raise" in actions_str or "Bet" in actions_str
    can_call = "Call" in actions_str
    street = state.get("street", "preflop")
    pot = int(state.get("pot_total") or state.get("pot") or 0)
    bb = detect_big_blind(state)
    
    my_cards = state.get("my_cards", [])
    board = state.get("board", [])
    if not my_cards:
        return ("check" if can_check else "fold", None)
    
    # Get actual stack
    for p in state.get("players", []):
        if p.get("is_me"):
            try: my_stack = int(p["stack"])
            except: my_stack = 1000
    
    # Calculate key metrics
    num_opps = max(1, sum(1 for p in state.get("players", [])
                          if not p.get("is_me") and p.get("status","active") == "active"))
    equity = get_equity(my_cards, board if board else None, num_opps)
    
    my_pos = state.get("my_position", "")
    style = profile["style"]
    stack_depth_bb = my_stack / bb if bb > 0 else 100
    
    # v27.1: Enhanced position mapping for 4-handed
    POSITION_RANKS_4H = {
        "UTG": 1,      # Tightest
        "CO": 2,       # Medium-tight  
        "BTN": 3,      # Loose
        "SB": 2.5,     # Medium (OOP but cheap)
        "BB": 1.5      # Medium-tight (already invested)
    }
    
    position_rank = POSITION_RANKS_4H.get(my_pos, 2)
    
    # v27.2: Advanced board texture analysis
    texture_analysis = get_enhanced_board_texture(board) if board else "preflop"
    
    # v27.3: Opponent-specific adjustments (enhanced from v23)
    opponent_factor = 1.0
    primary_opponent_type = "unknown"
    
    if opponent_model and num_opps > 0:
        active_opponents = [p for p in state.get("players", []) 
                           if not p.get("is_me") and p.get("status","active") == "active"]
        
        if active_opponents:
            # Get most threatening opponent
            primary_opp = max(active_opponents, 
                             key=lambda p: (int(p.get("stack", 0)), int(p.get("bet", 0))))
            opp_name = primary_opp.get("name", "").strip()
            
            if opp_name:
                primary_opponent_type = opponent_model.classify(opp_name)
                
                # v27: Enhanced opponent adjustments
                if primary_opponent_type == "NIT":
                    opponent_factor = 0.8   # Tighter vs nits
                elif primary_opponent_type == "LAG":
                    opponent_factor = 1.2   # Wider vs LAGs
                elif primary_opponent_type == "STATION":
                    opponent_factor = 1.1   # Slightly wider vs stations
    
    # v27.4: PREFLOP DECISION TREE (Enhanced)
    if street == "preflop":
        return enhanced_preflop_decision_v27(
            my_cards, equity, position_rank, style, 
            actions_str, opponent_factor, primary_opponent_type,
            stack_depth_bb, bb, pot
        )
    
    # v27.5: POSTFLOP DECISION TREE (Enhanced)  
    else:
        return enhanced_postflop_decision_v27(
            my_cards, board, equity, position_rank, style,
            actions_str, texture_analysis, opponent_factor,
            stack_depth_bb, bb, pot, street
        )

def enhanced_preflop_decision_v27(cards, equity, pos_rank, style, actions_str, 
                                  opp_factor, opp_type, stack_bb, bb, pot):
    """Enhanced preflop decisions with position-based ranges"""
    
    # v27: Position-based opening thresholds (4-handed)
    OPENING_THRESHOLDS = {
        1: 52,     # UTG - tight (top 15% hands)
        1.5: 50,   # BB - medium-tight
        2: 48,     # CO - medium  
        2.5: 46,   # SB - medium-loose
        3: 42      # BTN - loose (top 35% hands)
    }
    
    # v27: 3-bet thresholds by position
    THREBET_THRESHOLDS = {
        1: 70,     # UTG - only premiums
        1.5: 68,   # BB - tight
        2: 65,     # CO - medium
        2.5: 62,   # SB - medium-loose  
        3: 58      # BTN - wider 3-bet range
    }
    
    # Style adjustments
    style_adjustments = {
        "NIT": {"open": +8, "3bet": +12},      # Much tighter
        "TAG": {"open": 0, "3bet": 0},         # Baseline
        "LAG": {"open": -6, "3bet": -8},       # Looser
        "STATION": {"open": -3, "3bet": +15}   # Loose open, tight 3bet
    }
    
    adj = style_adjustments.get(style, {"open": 0, "3bet": 0})
    open_threshold = OPENING_THRESHOLDS.get(pos_rank, 48) + adj["open"]
    threbet_threshold = THREBET_THRESHOLDS.get(pos_rank, 65) + adj["3bet"]
    
    # Apply opponent factor
    open_threshold *= opp_factor
    threbet_threshold *= opp_factor
    
    # v27: Stack depth adjustments
    if stack_bb < 30:      # Short stack - tighter
        open_threshold += 5
        threbet_threshold += 8
    elif stack_bb > 150:   # Deep stack - can play more speculative
        open_threshold -= 3
        threbet_threshold -= 5
    
    # Decision logic
    facing_raise = "raise" in actions_str.lower() or "bet" in actions_str.lower()
    
    if facing_raise:
        if equity >= threbet_threshold:
            # v27: Enhanced 3-bet sizing by position and opponent
            threbet_size = get_threbet_sizing_v27(pos_rank, opp_type, stack_bb, bb)
            return ("raise", threbet_size)
        elif equity >= (open_threshold - 8):  # Call range wider than open range
            return ("call", None)
        else:
            return ("fold", None)
    
    else:  # First to act
        if equity >= open_threshold:
            # v27: Position-based opening sizing
            open_size = get_open_sizing_v27(pos_rank, stack_bb, bb)
            return ("raise", open_size)
        else:
            return ("fold" if pos_rank <= 2 else "check", None)

def enhanced_postflop_decision_v27(cards, board, equity, pos_rank, style,
                                   actions_str, texture, opp_factor, 
                                   stack_bb, bb, pot, street):
    """Enhanced postflop with advanced texture and stack depth analysis"""
    
    # v27: Granular texture-based thresholds
    TEXTURE_THRESHOLDS = {
        "bone_dry": {"value": 60, "bluff": 45, "cbet": 70},       # A72 rainbow
        "dry": {"value": 65, "bluff": 50, "cbet": 65},           # K83 rainbow  
        "semi_wet": {"value": 68, "bluff": 55, "cbet": 60},      # QJ4 two-tone
        "wet": {"value": 70, "bluff": 60, "cbet": 55},           # T98 two-tone
        "very_wet": {"value": 75, "bluff": 65, "cbet": 50},      # JT9 rainbow
        "soaking": {"value": 80, "bluff": 70, "cbet": 45}        # 987 two-tone
    }
    
    thresholds = TEXTURE_THRESHOLDS.get(texture, TEXTURE_THRESHOLDS["wet"])
    
    # Style and opponent adjustments
    if style == "LAG":
        thresholds = {k: v-5 for k, v in thresholds.items()}     # More aggressive
    elif style == "NIT":
        thresholds = {k: v+5 for k, v in thresholds.items()}     # More conservative
    elif style == "STATION":
        thresholds["value"] -= 8  # Value bet more liberally vs stations
    
    # v27: Stack depth impact
    if stack_bb < 40:     # Short stack - more committed
        thresholds = {k: v-8 for k, v in thresholds.items()}
    elif stack_bb > 150:  # Deep stack - more selective
        thresholds = {k: v+3 for k, v in thresholds.items()}
    
    # Apply opponent factor
    for key in thresholds:
        thresholds[key] *= opp_factor
    
    # Decision logic
    facing_bet = "call" in actions_str.lower()
    can_check = "check" in actions_str.lower()
    
    if facing_bet:
        if equity >= thresholds["value"]:
            # v27: Advanced raise sizing
            raise_size = get_value_raise_sizing_v27(equity, texture, stack_bb, pot, bb)
            return ("raise", raise_size)
        elif equity >= (thresholds["value"] - 15):  # Call range
            return ("call", None)
        else:
            return ("fold", None)
    
    elif can_check:
        if equity >= thresholds["value"]:
            bet_size = get_value_bet_sizing_v27(equity, texture, stack_bb, pot, bb)
            return ("raise", bet_size)
        elif equity >= thresholds["bluff"] and should_bluff_v27(texture, pos_rank):
            bluff_size = get_bluff_sizing_v27(texture, stack_bb, pot, bb)
            return ("raise", bluff_size)
        else:
            return ("check", None)
    
    else:  # Must call or fold
        if equity >= thresholds["value"] - 10:
            return ("call", None)
        else:
            return ("fold", None)

def get_enhanced_board_texture(board):
    """Enhanced board texture analysis with 6 categories"""
    if not board or len(board) < 3:
        return "preflop"
    
    # Analyze connectivity, suits, ranks
    ranks = [card[:-1] for card in board]
    suits = [card[-1] for card in board]
    
    rank_counts = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    
    suit_counts = {}
    for suit in suits:
        suit_counts[suit] = suit_counts.get(suit, 0) + 1
    
    # Check for draws
    max_suit_count = max(suit_counts.values()) if suit_counts else 0
    has_flush_draw = max_suit_count >= 3
    
    # Check connectivity (simplified)
    rank_values = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}
    numeric_ranks = sorted([rank_values.get(r, 0) for r in ranks])
    
    straight_draws = 0
    for i in range(len(numeric_ranks)-1):
        if numeric_ranks[i+1] - numeric_ranks[i] <= 2:
            straight_draws += 1
    
    has_straight_draw = straight_draws >= 2 or (max(numeric_ranks) - min(numeric_ranks) <= 4)
    
    # Classify texture
    draw_count = int(has_flush_draw) + int(has_straight_draw)
    is_paired = max(rank_counts.values()) >= 2
    
    if is_paired and draw_count == 0:
        return "dry"
    elif draw_count == 0:
        return "bone_dry"
    elif draw_count == 1:
        return "semi_wet" if not is_paired else "wet"
    elif draw_count == 2:
        return "very_wet"
    else:
        return "soaking"

# Sizing helper functions (simplified implementations)
def get_threbet_sizing_v27(pos_rank, opp_type, stack_bb, bb):
    base_size = 2.5 * bb  # 2.5x original raise
    if pos_rank >= 3: base_size += 0.5 * bb  # Larger from position
    if opp_type == "LAG": base_size += 0.5 * bb  # Larger vs LAGs
    return min(int(base_size), int(stack_bb * bb * 0.3))  # Cap at 30% stack

def get_open_sizing_v27(pos_rank, stack_bb, bb):
    base_size = 2.2 * bb if pos_rank >= 3 else 2.5 * bb  # Smaller from position
    return min(int(base_size), int(stack_bb * bb * 0.15))  # Cap at 15% stack

def get_value_bet_sizing_v27(equity, texture, stack_bb, pot, bb):
    base_pct = 0.65 + (equity - 70) * 0.01  # 65-85% pot based on equity
    
    texture_mults = {
        "bone_dry": 0.85, "dry": 0.9, "semi_wet": 0.95,
        "wet": 1.0, "very_wet": 1.1, "soaking": 1.2
    }
    
    multiplier = texture_mults.get(texture, 1.0)
    if stack_bb < 50: multiplier *= 1.15  # Size up when short
    
    return max(int(pot * base_pct * multiplier), bb)

def get_bluff_sizing_v27(texture, stack_bb, pot, bb):
    texture_sizes = {
        "bone_dry": 0.5, "dry": 0.6, "semi_wet": 0.65,
        "wet": 0.7, "very_wet": 0.8, "soaking": 0.9
    }
    
    size_pct = texture_sizes.get(texture, 0.65)
    if stack_bb < 50: size_pct *= 1.2  # Bigger bluffs when short
    
    return max(int(pot * size_pct), bb)

def should_bluff_v27(texture, pos_rank):
    """Simple bluff frequency based on texture and position"""
    base_freq = 0.3  # 30% baseline bluff frequency
    
    if texture in ["very_wet", "soaking"]: base_freq += 0.1
    if pos_rank >= 3: base_freq += 0.05  # Bluff more from position
    
    return random.random() < base_freq

# Import required functions (would be imported from existing modules)
def get_equity(cards, board, num_opps):
    """Placeholder - use existing equity calculation"""
    return 50  # Simplified for demo

def detect_big_blind(state):
    """Placeholder - use existing BB detection"""
    return 10  # Simplified for demo

import random
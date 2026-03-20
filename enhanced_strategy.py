"""
Enhanced Poker Strategy Module v27.0
Advanced GTO concepts with position-based ranges and exploitative adjustments

Key improvements:
1. Position-specific opening ranges (tighter UTG, looser BTN)
2. 3-bet/4-bet frequency targets
3. Opponent-specific adjustments
4. Advanced board texture analysis
5. ICM-aware stack depth decisions
"""

import math
from hand_eval import preflop_equity

# Position-based opening ranges (% of hands to play)
OPENING_RANGES = {
    'UTG': 0.15,      # 15% - tight range (77+, AQ+, KQs)
    'UTG+1': 0.18,    # 18% 
    'MP': 0.22,       # 22%
    'MP+1': 0.25,     # 25%
    'CO': 0.30,       # 30%
    'BTN': 0.45,      # 45% - wide range
    'SB': 0.35,       # 35% - complete more liberally
    'BB': 1.0         # 100% - already invested
}

# 3-bet ranges by position (when facing raise)
THREBET_RANGES = {
    'UTG': 0.06,      # 6% - only premiums (QQ+, AKs, AKo)
    'UTG+1': 0.07,    
    'MP': 0.08,       
    'MP+1': 0.09,     
    'CO': 0.11,       
    'BTN': 0.15,      # 15% - wider 3-bet range
    'SB': 0.12,       
    'BB': 0.14        
}

# Continuation bet frequencies by board texture
CBET_FREQUENCIES = {
    'dry': 0.75,        # 75% on A72 rainbow
    'wet': 0.65,        # 65% on T98 two-tone  
    'very_wet': 0.55,   # 55% on JT9 rainbow
    'paired': 0.80      # 80% on AA2, 772, etc
}

class AdvancedStrategy:
    def __init__(self, bot_style='TAG'):
        self.bot_style = bot_style
        self.style_modifiers = self._get_style_modifiers()
    
    def _get_style_modifiers(self):
        """Get style-specific adjustments to base ranges"""
        if self.bot_style == 'NIT':
            return {
                'opening_mult': 0.7,      # 30% tighter
                'threbet_mult': 0.6,      # 40% fewer 3-bets  
                'cbet_mult': 0.85,        # 15% fewer cbets
                'fold_threshold': 0.48    # Fold more marginally
            }
        elif self.bot_style == 'LAG':
            return {
                'opening_mult': 1.3,      # 30% looser
                'threbet_mult': 1.5,      # 50% more 3-bets
                'cbet_mult': 1.2,         # 20% more cbets  
                'fold_threshold': 0.42    # Call lighter
            }
        elif self.bot_style == 'STATION':
            return {
                'opening_mult': 1.1,      # Slightly looser
                'threbet_mult': 0.4,      # Much fewer 3-bets
                'cbet_mult': 0.9,         # Fewer cbets
                'fold_threshold': 0.35    # Call very light
            }
        else:  # TAG
            return {
                'opening_mult': 1.0,      # Baseline ranges
                'threbet_mult': 1.0,      
                'cbet_mult': 1.0,
                'fold_threshold': 0.45    
            }
    
    def should_open_raise(self, position, hand_strength_percentile):
        """Determine if we should open raise based on position and hand strength"""
        base_range = OPENING_RANGES.get(position, 0.25)
        adjusted_range = base_range * self.style_modifiers['opening_mult']
        
        return hand_strength_percentile >= (1.0 - adjusted_range)
    
    def should_threbet(self, position, hand_strength_percentile, vs_position='UTG'):
        """Determine 3-bet decision based on position and opponents"""
        base_range = THREBET_RANGES.get(position, 0.10)
        adjusted_range = base_range * self.style_modifiers['threbet_mult']
        
        # Adjust based on opponent position (tighter vs UTG, looser vs BTN)
        if vs_position in ['UTG', 'UTG+1']:
            adjusted_range *= 0.8  # Respect early position
        elif vs_position in ['CO', 'BTN']:
            adjusted_range *= 1.2  # Attack late position
            
        return hand_strength_percentile >= (1.0 - adjusted_range)
    
    def get_cbet_frequency(self, board_texture, position, num_opponents):
        """Get continuation bet frequency based on board and position"""
        base_freq = CBET_FREQUENCIES.get(board_texture, 0.65)
        adjusted_freq = base_freq * self.style_modifiers['cbet_mult']
        
        # Position adjustments
        if position in ['UTG', 'UTG+1']:
            adjusted_freq *= 1.1  # More cbets from early position
        elif position == 'BTN':
            adjusted_freq *= 0.95  # Slightly fewer from button
            
        # Multi-way adjustments
        if num_opponents > 1:
            adjusted_freq *= (0.85 ** (num_opponents - 1))
            
        return min(adjusted_freq, 0.95)  # Cap at 95%
    
    def get_value_bet_sizing(self, equity, board_texture, stack_depth_bb):
        """Advanced value bet sizing based on multiple factors"""
        base_size = 0.65  # 65% pot as baseline
        
        # Equity adjustments
        if equity > 0.85:      # Nuts
            base_size = 0.80
        elif equity > 0.75:    # Strong value  
            base_size = 0.70
        elif equity > 0.65:    # Medium value
            base_size = 0.60
        else:                  # Thin value
            base_size = 0.50
            
        # Board texture adjustments
        texture_mults = {
            'dry': 0.9,         # Smaller on dry boards
            'wet': 1.0,         # Standard
            'very_wet': 1.15,   # Larger for protection
            'paired': 1.05      # Slightly larger
        }
        base_size *= texture_mults.get(board_texture, 1.0)
        
        # Stack depth adjustments
        if stack_depth_bb < 30:      # Short stack
            base_size *= 1.2         # Size up (commitment)
        elif stack_depth_bb > 150:   # Deep stack
            base_size *= 0.9         # Size down (room to play)
            
        return min(base_size, 1.0)  # Cap at pot size

    def get_bluff_sizing(self, board_texture, fold_equity_target=0.6):
        """Get optimal bluff sizing to achieve target fold equity"""
        # Rough estimation: 60% pot gets ~60% folds on average
        base_size = fold_equity_target
        
        texture_adjustments = {
            'dry': 0.85,        # Smaller bluffs work on dry boards
            'wet': 1.0,         # Standard sizing  
            'very_wet': 1.2,    # Bigger bluffs on scary boards
            'paired': 0.9       # Medium sizing on pairs
        }
        
        return base_size * texture_adjustments.get(board_texture, 1.0)

def analyze_hand_strength_percentile(card1, card2):
    """Convert hand to percentile strength (0.0 to 1.0)"""
    equity = preflop_equity(card1, card2, num_opponents=3)  # vs 3 opponents
    
    # Convert equity to approximate percentile
    # This is a rough mapping: 84% (AA) ≈ 99th percentile, 30% (72o) ≈ 5th percentile
    if equity >= 80:
        return 0.95 + (equity - 80) * 0.05 / 20  # 95-100th percentile
    elif equity >= 60:
        return 0.75 + (equity - 60) * 0.20 / 20  # 75-95th percentile  
    elif equity >= 45:
        return 0.50 + (equity - 45) * 0.25 / 15  # 50-75th percentile
    elif equity >= 35:
        return 0.25 + (equity - 35) * 0.25 / 10  # 25-50th percentile
    else:
        return (equity - 20) * 0.25 / 15        # 0-25th percentile
    
def get_position_from_seat(seat_num, num_players=4):
    """Convert seat number to position string"""
    # For 4-handed: seat 1=UTG, 2=CO, 3=BTN, 4=SB
    position_map = {
        1: 'UTG',
        2: 'CO', 
        3: 'BTN',
        4: 'SB'
    }
    return position_map.get(seat_num, 'MP')

# Example usage functions for integration with main bot
def enhanced_preflop_decision(bot_style, position, hand1, hand2, action_history, stack_bb):
    """Make enhanced preflop decision using advanced strategy"""
    strategy = AdvancedStrategy(bot_style)
    hand_percentile = analyze_hand_strength_percentile(hand1, hand2)
    
    # Check if facing a raise
    if 'raise' in action_history.lower() or 'bet' in action_history.lower():
        if strategy.should_threbet(position, hand_percentile):
            return 'threbet'
        elif hand_percentile >= strategy.style_modifiers['fold_threshold']:
            return 'call'
        else:
            return 'fold'
    
    # First to act - check if we should open
    if strategy.should_open_raise(position, hand_percentile):
        return 'raise'
    else:
        return 'fold'

def enhanced_postflop_sizing(bot_style, equity, board_texture, position, stack_bb, action='value'):
    """Get optimal bet sizing for postflop situations"""
    strategy = AdvancedStrategy(bot_style)
    
    if action == 'value':
        return strategy.get_value_bet_sizing(equity/100, board_texture, stack_bb)
    elif action == 'bluff':
        return strategy.get_bluff_sizing(board_texture)
    else:
        return 0.65  # Default 65% pot

if __name__ == "__main__":
    # Test the enhanced strategy
    strategy = AdvancedStrategy('TAG')
    
    print("Testing Enhanced Strategy:")
    print(f"AA UTG open: {strategy.should_open_raise('UTG', 0.99)}")
    print(f"72o BTN open: {strategy.should_open_raise('BTN', 0.05)}")
    print(f"AK 3bet vs UTG: {strategy.should_threbet('CO', 0.85, 'UTG')}")
    print(f"Value sizing 80% equity dry board: {strategy.get_value_bet_sizing(0.8, 'dry', 100)}")
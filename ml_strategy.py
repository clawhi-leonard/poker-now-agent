"""
Machine Learning Strategy Module v29.0
Adaptive poker strategy using opponent modeling and hand history analysis

Features:
1. Opponent clustering based on betting patterns
2. Dynamic range adjustment based on observed play
3. Exploitative sizing vs different player types
4. Session-based strategy adaptation
5. Hand strength prediction using historical data
"""

import json
import os
import time
from collections import defaultdict, deque
import numpy as np
from typing import Dict, List, Tuple, Optional

class OpponentCluster:
    """Statistical clustering of opponent play styles"""
    
    CLUSTER_NAMES = {
        'ULTRA_NIT': {'vpip': (0, 15), 'pfr': (0, 10), 'aggr': (0, 1.5)},
        'NIT': {'vpip': (15, 25), 'pfr': (10, 20), 'aggr': (1.5, 2.5)},
        'TAG': {'vpip': (20, 30), 'pfr': (15, 25), 'aggr': (2.0, 3.5)},
        'LAG': {'vpip': (30, 45), 'pfr': (20, 35), 'aggr': (2.5, 4.0)},
        'MANIAC': {'vpip': (45, 100), 'pfr': (30, 100), 'aggr': (3.5, 10)},
        'WHALE': {'vpip': (50, 100), 'pfr': (5, 15), 'aggr': (1.0, 2.0)}  # Loose-passive
    }
    
    @staticmethod
    def classify_opponent(vpip: float, pfr: float, aggression: float) -> str:
        """Classify opponent into cluster based on statistics"""
        for cluster, ranges in OpponentCluster.CLUSTER_NAMES.items():
            if (ranges['vpip'][0] <= vpip <= ranges['vpip'][1] and
                ranges['pfr'][0] <= pfr <= ranges['pfr'][1] and
                ranges['aggr'][0] <= aggression <= ranges['aggr'][1]):
                return cluster
        return 'TAG'  # Default fallback

class MLStrategy:
    """Machine learning enhanced poker strategy"""
    
    def __init__(self, bot_name: str, bot_style: str):
        self.bot_name = bot_name
        self.bot_style = bot_style
        self.session_start = time.time()
        
        # Opponent modeling
        self.opponent_stats = defaultdict(lambda: {
            'hands_seen': 0,
            'vpip_count': 0,
            'pfr_count': 0,
            'aggr_points': 0,
            'aggr_opps': 0,
            'fold_to_cbet': {'count': 0, 'opps': 0},
            'call_3bet': {'count': 0, 'opps': 0},
            'recent_actions': deque(maxlen=20)
        })
        
        # Strategy adaptation tracking
        self.exploitation_adjustments = defaultdict(float)
        self.successful_adjustments = defaultdict(int)
        
        # Hand history for pattern recognition
        self.hand_history = []
        self.win_rates_by_context = defaultdict(lambda: {'wins': 0, 'total': 0})
        
    def update_opponent_action(self, opponent: str, action: str, position: str, 
                             street: str, bet_size: float = None):
        """Update opponent statistics with new action"""
        stats = self.opponent_stats[opponent]
        stats['hands_seen'] += 1
        
        # VPIP tracking
        if street == 'preflop' and action in ['call', 'raise']:
            stats['vpip_count'] += 1
            
        # PFR tracking  
        if street == 'preflop' and action == 'raise':
            stats['pfr_count'] += 1
            
        # Aggression tracking
        if action in ['raise', 'bet']:
            stats['aggr_points'] += 1
            stats['aggr_opps'] += 1
        elif action in ['call', 'check']:
            stats['aggr_opps'] += 1
            
        # Store recent action pattern
        stats['recent_actions'].append({
            'action': action,
            'position': position,
            'street': street,
            'bet_size': bet_size,
            'timestamp': time.time()
        })
        
    def get_opponent_cluster(self, opponent: str) -> str:
        """Get opponent's current cluster classification"""
        stats = self.opponent_stats[opponent]
        if stats['hands_seen'] < 10:
            return 'UNKNOWN'
            
        vpip = (stats['vpip_count'] / stats['hands_seen']) * 100
        pfr = (stats['pfr_count'] / stats['hands_seen']) * 100
        aggr = stats['aggr_points'] / max(stats['aggr_opps'], 1)
        
        return OpponentCluster.classify_opponent(vpip, pfr, aggr)
        
    def calculate_exploitative_sizing(self, base_size: float, opponent: str, 
                                    context: str) -> float:
        """Calculate exploitative bet sizing based on opponent tendencies"""
        cluster = self.get_opponent_cluster(opponent)
        
        # Size adjustments by opponent type
        if cluster == 'ULTRA_NIT':
            if context == 'value_bet':
                return base_size * 0.7  # Smaller value bets for extraction
            elif context == 'bluff':
                return base_size * 1.3  # Larger bluffs (they fold too much)
                
        elif cluster == 'WHALE':
            if context == 'value_bet':
                return base_size * 1.2  # Larger value bets (they call light)
            elif context == 'bluff':
                return base_size * 0.8  # Smaller bluffs (they don't fold)
                
        elif cluster == 'MANIAC':
            if context == 'value_bet':
                return base_size * 0.9  # Medium sizing for balance
            elif context == 'bluff':
                return base_size * 1.4  # Very large bluffs needed
                
        return base_size  # No adjustment for unknown/balanced opponents
        
    def get_preflop_range_adjustment(self, position: str, opponent_actions: List[str]) -> float:
        """Adjust preflop range based on table dynamics and opponents"""
        base_tightness = 1.0
        
        # Tighten up against multiple opponents
        if len([a for a in opponent_actions if a in ['call', 'raise']]) >= 2:
            base_tightness *= 0.8
            
        # Loosen up against nits
        nit_count = sum(1 for opp in self.opponent_stats 
                       if self.get_opponent_cluster(opp) in ['NIT', 'ULTRA_NIT'])
        if nit_count >= 2:
            base_tightness *= 1.2
            
        # Tighten against maniacs
        maniac_count = sum(1 for opp in self.opponent_stats
                          if self.get_opponent_cluster(opp) == 'MANIAC')
        if maniac_count >= 1:
            base_tightness *= 0.9
            
        return base_tightness
        
    def record_hand_result(self, hand_data: Dict):
        """Record hand result for pattern recognition"""
        self.hand_history.append({
            'timestamp': time.time(),
            'position': hand_data.get('position'),
            'cards': hand_data.get('cards'),
            'actions': hand_data.get('actions', []),
            'result': hand_data.get('result', 0),
            'opponents': hand_data.get('opponents', []),
            'board_texture': hand_data.get('board_texture')
        })
        
        # Update win rate by context
        context = f"{hand_data.get('position')}_{hand_data.get('board_texture', 'unknown')}"
        wr_data = self.win_rates_by_context[context]
        wr_data['total'] += 1
        if hand_data.get('result', 0) > 0:
            wr_data['wins'] += 1
            
    def get_session_adjustments(self) -> Dict[str, float]:
        """Get current session-based strategy adjustments"""
        session_duration = time.time() - self.session_start
        
        adjustments = {}
        
        # Early session: play tighter
        if session_duration < 300:  # First 5 minutes
            adjustments['preflop_tightness'] = 0.9
            adjustments['cbet_frequency'] = 0.95
            
        # Late session: adapt to identified patterns
        elif session_duration > 1800:  # After 30 minutes
            # Calculate overall table aggression
            total_aggression = sum(
                stats['aggr_points'] / max(stats['aggr_opps'], 1)
                for stats in self.opponent_stats.values()
                if stats['hands_seen'] >= 5
            )
            avg_aggression = total_aggression / max(len(self.opponent_stats), 1)
            
            if avg_aggression > 3.0:  # Aggressive table
                adjustments['preflop_tightness'] = 0.85
                adjustments['value_bet_sizing'] = 1.1
            elif avg_aggression < 1.5:  # Passive table
                adjustments['preflop_looseness'] = 1.15
                adjustments['bluff_frequency'] = 1.2
                
        return adjustments
        
    def save_session_data(self, filepath: str):
        """Save session data for future learning"""
        session_data = {
            'bot_name': self.bot_name,
            'bot_style': self.bot_style,
            'session_start': self.session_start,
            'session_duration': time.time() - self.session_start,
            'opponent_stats': dict(self.opponent_stats),
            'hand_count': len(self.hand_history),
            'win_rates_by_context': dict(self.win_rates_by_context),
            'final_adjustments': self.get_session_adjustments()
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)
            
    @staticmethod
    def load_historical_data(directory: str) -> Dict:
        """Load historical session data for meta-learning"""
        historical_data = {
            'total_sessions': 0,
            'successful_patterns': defaultdict(int),
            'opponent_clusters_seen': defaultdict(int),
            'avg_win_rates': defaultdict(list)
        }
        
        if not os.path.exists(directory):
            return historical_data
            
        for filename in os.listdir(directory):
            if filename.startswith('ml_session_') and filename.endswith('.json'):
                try:
                    with open(os.path.join(directory, filename), 'r') as f:
                        session_data = json.load(f)
                        
                    historical_data['total_sessions'] += 1
                    
                    # Aggregate successful patterns
                    for context, win_data in session_data.get('win_rates_by_context', {}).items():
                        if win_data['total'] >= 3:  # Minimum sample size
                            win_rate = win_data['wins'] / win_data['total']
                            historical_data['avg_win_rates'][context].append(win_rate)
                            
                except Exception as e:
                    continue
                    
        return historical_data

# Integration functions for multi_bot.py

def initialize_ml_strategy(bot_name: str, bot_style: str) -> MLStrategy:
    """Initialize ML strategy for a bot"""
    ml_strategy = MLStrategy(bot_name, bot_style)
    
    # Load historical patterns
    historical = MLStrategy.load_historical_data('logs/ml_data/')
    
    return ml_strategy

def apply_ml_adjustments(ml_strategy: MLStrategy, base_decision: Dict, 
                        context: Dict) -> Dict:
    """Apply ML-based adjustments to a poker decision"""
    adjusted_decision = base_decision.copy()
    
    # Get session-based adjustments
    session_adj = ml_strategy.get_session_adjustments()
    
    # Adjust bet sizing based on opponents
    if 'bet_size' in adjusted_decision and 'primary_opponent' in context:
        opponent = context['primary_opponent']
        bet_context = context.get('bet_type', 'value_bet')
        
        exploitative_size = ml_strategy.calculate_exploitative_sizing(
            adjusted_decision['bet_size'], opponent, bet_context
        )
        adjusted_decision['bet_size'] = exploitative_size
        
    # Adjust action probabilities based on session learning
    if 'action' in adjusted_decision:
        action = adjusted_decision['action']
        
        # Apply session-based modifications
        if action == 'fold' and session_adj.get('preflop_looseness', 1.0) > 1.1:
            # Consider calling more in loose sessions
            if context.get('street') == 'preflop' and context.get('equity', 0) > 35:
                adjusted_decision['action'] = 'call'
                
        elif action in ['bet', 'raise'] and session_adj.get('value_bet_sizing'):
            # Adjust bet sizing for session conditions
            adjusted_decision['bet_size'] *= session_adj['value_bet_sizing']
            
    return adjusted_decision
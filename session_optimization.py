"""
Session Optimization Module v29.0
Real-time strategy optimization based on live session performance

Features:
1. Live performance monitoring with automatic adjustments
2. Opponent exploitation detection and response
3. Table dynamics analysis and adaptation
4. Real-time EV calculation and strategy shifts
5. Bankroll protection with risk management
"""

import time
import json
import math
from collections import deque, defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

class SessionOptimizer:
    """Real-time session optimization and adaptation"""
    
    def __init__(self, bot_name: str, starting_stack: float, big_blind: float):
        self.bot_name = bot_name
        self.starting_stack = starting_stack
        self.big_blind = big_blind
        self.session_start = time.time()
        
        # Performance tracking
        self.hand_results = deque(maxlen=100)  # Recent hand outcomes
        self.position_performance = defaultdict(lambda: {'bb': 0, 'hands': 0})
        self.stack_history = deque(maxlen=50)
        
        # Dynamic adjustments
        self.current_adjustments = {
            'aggression_modifier': 1.0,
            'tightness_modifier': 1.0,
            'bluff_frequency': 1.0,
            'value_sizing': 1.0
        }
        
        # Table dynamics
        self.table_aggression = deque(maxlen=20)
        self.pot_size_history = deque(maxlen=30)
        self.showdown_results = []
        
        # Risk management
        self.max_loss_threshold = starting_stack * 0.4  # Stop at 40% loss
        self.profit_protection = starting_stack * 0.2   # Protect 20% profit
        
    def record_hand_outcome(self, hand_data: Dict):
        """Record the outcome of a completed hand"""
        result = hand_data.get('stack_change', 0) / self.big_blind  # Convert to BB
        position = hand_data.get('position', 'unknown')
        action_count = len(hand_data.get('actions', []))
        pot_size = hand_data.get('final_pot', 0) / self.big_blind
        
        # Store hand result
        self.hand_results.append({
            'bb_result': result,
            'position': position,
            'actions': action_count,
            'pot_size': pot_size,
            'timestamp': time.time(),
            'equity_realization': hand_data.get('equity_realization', None)
        })
        
        # Update position performance
        pos_data = self.position_performance[position]
        pos_data['bb'] += result
        pos_data['hands'] += 1
        
        # Track pot sizes for table dynamics
        self.pot_size_history.append(pot_size)
        
        # Update stack history
        current_stack = hand_data.get('current_stack', self.starting_stack)
        self.stack_history.append((time.time(), current_stack))
        
    def calculate_recent_performance(self, hands_back: int = 20) -> Dict:
        """Calculate performance over recent hands"""
        if not self.hand_results:
            return {'bb_rate': 0, 'win_rate': 0, 'hands': 0}
            
        recent_hands = list(self.hand_results)[-hands_back:]
        
        total_bb = sum(h['bb_result'] for h in recent_hands)
        winning_hands = sum(1 for h in recent_hands if h['bb_result'] > 0)
        
        return {
            'bb_rate': total_bb,
            'win_rate': winning_hands / len(recent_hands),
            'hands': len(recent_hands),
            'avg_pot': statistics.mean([h['pot_size'] for h in recent_hands]) if recent_hands else 0
        }
        
    def detect_table_dynamics(self) -> Dict:
        """Analyze current table characteristics"""
        dynamics = {
            'aggression_level': 'medium',
            'pot_sizes': 'medium',
            'table_type': 'balanced'
        }
        
        if len(self.pot_size_history) >= 10:
            avg_pot = statistics.mean(self.pot_size_history)
            
            # Classify pot sizes
            if avg_pot > 8 * self.big_blind:
                dynamics['pot_sizes'] = 'large'
                dynamics['table_type'] = 'action'
            elif avg_pot < 3 * self.big_blind:
                dynamics['pot_sizes'] = 'small'
                dynamics['table_type'] = 'tight'
                
        # Analyze aggression from hand action counts
        if len(self.hand_results) >= 10:
            avg_actions = statistics.mean([h['actions'] for h in self.hand_results[-10:]])
            
            if avg_actions > 8:
                dynamics['aggression_level'] = 'high'
            elif avg_actions < 4:
                dynamics['aggression_level'] = 'low'
                
        return dynamics
        
    def calculate_position_edge(self) -> Dict:
        """Calculate edge/disadvantage by position"""
        position_edges = {}
        
        for position, data in self.position_performance.items():
            if data['hands'] >= 3:  # Minimum sample size
                bb_per_hand = data['bb'] / data['hands']
                position_edges[position] = bb_per_hand
                
        return position_edges
        
    def suggest_strategy_adjustments(self) -> Dict:
        """Suggest real-time strategy adjustments based on performance"""
        suggestions = {}
        
        # Recent performance analysis
        recent_perf = self.calculate_recent_performance(15)
        table_dynamics = self.detect_table_dynamics()
        position_edges = self.calculate_position_edge()
        
        # Adjust based on recent results
        if recent_perf['bb_rate'] < -10:  # Losing >10BB recently
            suggestions['tightness_increase'] = 1.2
            suggestions['aggression_decrease'] = 0.85
            suggestions['risk_reduction'] = True
            
        elif recent_perf['bb_rate'] > 15:  # Winning >15BB recently
            suggestions['aggression_increase'] = 1.15
            suggestions['value_sizing_increase'] = 1.1
            
        # Adjust based on table dynamics
        if table_dynamics['aggression_level'] == 'high':
            suggestions['tightness_increase'] = getattr(suggestions, 'tightness_increase', 1.0) * 1.1
            suggestions['value_bet_larger'] = True
            
        elif table_dynamics['aggression_level'] == 'low':
            suggestions['bluff_frequency_increase'] = 1.3
            suggestions['steal_more'] = True
            
        # Position-specific adjustments
        if 'BTN' in position_edges and position_edges['BTN'] > 5:
            suggestions['button_play_wider'] = True
        if 'UTG' in position_edges and position_edges['UTG'] < -3:
            suggestions['early_position_tighter'] = True
            
        return suggestions
        
    def apply_adjustments(self, suggestions: Dict):
        """Apply suggested adjustments to current strategy modifiers"""
        
        # Aggression adjustments
        if 'aggression_increase' in suggestions:
            self.current_adjustments['aggression_modifier'] *= suggestions['aggression_increase']
        if 'aggression_decrease' in suggestions:
            self.current_adjustments['aggression_modifier'] *= suggestions['aggression_decrease']
            
        # Tightness adjustments  
        if 'tightness_increase' in suggestions:
            self.current_adjustments['tightness_modifier'] *= suggestions['tightness_increase']
            
        # Bet sizing adjustments
        if 'value_sizing_increase' in suggestions:
            self.current_adjustments['value_sizing'] *= suggestions['value_sizing_increase']
            
        # Bluff frequency adjustments
        if 'bluff_frequency_increase' in suggestions:
            self.current_adjustments['bluff_frequency'] *= suggestions['bluff_frequency_increase']
            
        # Keep modifiers within reasonable bounds
        for key in self.current_adjustments:
            self.current_adjustments[key] = max(0.7, min(1.5, self.current_adjustments[key]))
            
    def check_risk_management(self, current_stack: float) -> Dict:
        """Check if risk management actions are needed"""
        stack_bb = current_stack / self.big_blind
        starting_bb = self.starting_stack / self.big_blind
        
        risk_status = {
            'action_needed': False,
            'recommendation': 'continue',
            'risk_level': 'normal'
        }
        
        # Check for significant losses
        loss_amount = starting_bb - stack_bb
        if loss_amount > self.max_loss_threshold / self.big_blind:
            risk_status['action_needed'] = True
            risk_status['recommendation'] = 'quit_session'
            risk_status['risk_level'] = 'high'
            risk_status['reason'] = f'Loss limit reached: -{loss_amount:.1f}BB'
            
        # Check profit protection
        elif stack_bb > starting_bb + self.profit_protection / self.big_blind:
            if len(self.hand_results) >= 5:
                recent_trend = sum(h['bb_result'] for h in list(self.hand_results)[-5:])
                if recent_trend < -5:  # Losing trend while in profit
                    risk_status['action_needed'] = True
                    risk_status['recommendation'] = 'play_tighter'
                    risk_status['risk_level'] = 'medium'
                    risk_status['reason'] = 'Protecting profit during downswing'
                    
        return risk_status
        
    def generate_session_report(self, current_stack: float) -> Dict:
        """Generate comprehensive session performance report"""
        duration = time.time() - self.session_start
        duration_hours = duration / 3600
        
        stack_bb = current_stack / self.big_blind
        starting_bb = self.starting_stack / self.big_blind
        profit_bb = stack_bb - starting_bb
        
        report = {
            'session_duration_hours': duration_hours,
            'hands_played': len(self.hand_results),
            'bb_won': profit_bb,
            'bb_per_hour': profit_bb / duration_hours if duration_hours > 0 else 0,
            'current_adjustments': self.current_adjustments.copy(),
            'table_dynamics': self.detect_table_dynamics(),
            'position_performance': dict(self.position_performance),
            'recent_performance': self.calculate_recent_performance(),
            'risk_assessment': self.check_risk_management(current_stack)
        }
        
        # Calculate additional metrics
        if len(self.hand_results) >= 10:
            recent_variance = statistics.stdev([h['bb_result'] for h in self.hand_results[-20:]])
            report['recent_variance'] = recent_variance
            
            winning_sessions = sum(1 for h in self.hand_results if h['bb_result'] > 0)
            report['win_rate'] = winning_sessions / len(self.hand_results)
            
        return report
        
    def save_session_optimization_data(self, filepath: str):
        """Save optimization data for future analysis"""
        current_stack = self.stack_history[-1][1] if self.stack_history else self.starting_stack
        optimization_data = {
            'session_report': self.generate_session_report(current_stack),
            'hand_results': list(self.hand_results),
            'adjustment_history': self.current_adjustments,
            'timestamp': time.time()
        }
        
        with open(filepath, 'w') as f:
            json.dump(optimization_data, f, indent=2, default=str)

# Integration functions for multi_bot.py

def initialize_session_optimizer(bot_name: str, starting_stack: float, big_blind: float) -> SessionOptimizer:
    """Initialize session optimizer for a bot"""
    return SessionOptimizer(bot_name, starting_stack, big_blind)

def update_optimizer_with_hand(optimizer: SessionOptimizer, hand_data: Dict):
    """Update optimizer with completed hand data"""
    optimizer.record_hand_outcome(hand_data)
    
    # Check for strategy adjustments every 5 hands
    if len(optimizer.hand_results) % 5 == 0:
        suggestions = optimizer.suggest_strategy_adjustments()
        if suggestions:
            optimizer.apply_adjustments(suggestions)
            
def get_optimized_decision_modifiers(optimizer: SessionOptimizer) -> Dict:
    """Get current decision modifiers from optimizer"""
    return optimizer.current_adjustments

def check_session_risk_management(optimizer: SessionOptimizer, current_stack: float) -> Dict:
    """Check if risk management actions are needed"""
    return optimizer.check_risk_management(current_stack)
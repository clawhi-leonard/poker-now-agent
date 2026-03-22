"""
Advanced Integration Module v29.0
Seamless integration of ML strategy and session optimization into existing poker bot

Integration points:
1. ML strategy initialization and decision enhancement
2. Session optimization with real-time adjustments  
3. Advanced opponent modeling with clustering
4. Risk management and bankroll protection
5. Performance analytics with machine learning insights
"""

import time
import os
import json
from typing import Dict, List, Optional, Any
from ml_strategy import MLStrategy, initialize_ml_strategy, apply_ml_adjustments
from session_optimization import SessionOptimizer, initialize_session_optimizer, update_optimizer_with_hand, get_optimized_decision_modifiers, check_session_risk_management

class AdvancedBotController:
    """Controller for advanced bot features"""
    
    def __init__(self, bot_name: str, bot_style: str, starting_stack: float, big_blind: float):
        self.bot_name = bot_name
        self.bot_style = bot_style
        
        # Initialize advanced modules
        self.ml_strategy = initialize_ml_strategy(bot_name, bot_style)
        self.session_optimizer = initialize_session_optimizer(bot_name, starting_stack, big_blind)
        
        # Integration state
        self.last_hand_data = None
        self.performance_log = []
        
    def enhance_decision(self, base_decision: Dict, game_state: Dict, hand_context: Dict) -> Dict:
        """Enhance a poker decision with ML and optimization insights"""
        
        # Prepare context for ML analysis
        ml_context = {
            'street': hand_context.get('street', 'preflop'),
            'position': game_state.get('position'),
            'equity': hand_context.get('equity', 0),
            'board_texture': hand_context.get('board_texture'),
            'bet_type': self._classify_bet_type(base_decision, hand_context),
            'primary_opponent': self._identify_primary_opponent(game_state)
        }
        
        # Apply ML adjustments
        ml_enhanced_decision = apply_ml_adjustments(self.ml_strategy, base_decision, ml_context)
        
        # Apply session optimization modifiers
        optimization_modifiers = get_optimized_decision_modifiers(self.session_optimizer)
        final_decision = self._apply_optimization_modifiers(ml_enhanced_decision, optimization_modifiers, hand_context)
        
        # Log decision enhancement for analysis
        self._log_decision_enhancement(base_decision, final_decision, ml_context)
        
        return final_decision
        
    def update_with_opponent_action(self, opponent_name: str, action: str, position: str, 
                                  street: str, bet_size: float = None):
        """Update opponent modeling with new action"""
        self.ml_strategy.update_opponent_action(opponent_name, action, position, street, bet_size)
        
    def complete_hand(self, hand_result: Dict):
        """Process completed hand for learning and optimization"""
        
        # Update ML strategy with hand result
        self.ml_strategy.record_hand_result(hand_result)
        
        # Update session optimizer
        update_optimizer_with_hand(self.session_optimizer, hand_result)
        
        # Check risk management
        current_stack = hand_result.get('current_stack', 0)
        risk_status = check_session_risk_management(self.session_optimizer, current_stack)
        
        if risk_status.get('action_needed'):
            self._handle_risk_management(risk_status)
            
        # Store hand data for pattern analysis
        self.last_hand_data = hand_result
        self.performance_log.append({
            'timestamp': time.time(),
            'hand_result': hand_result,
            'ml_adjustments': self.ml_strategy.get_session_adjustments(),
            'optimizer_state': self.session_optimizer.current_adjustments.copy()
        })
        
    def get_current_insights(self) -> Dict:
        """Get current AI insights and recommendations"""
        
        insights = {
            'timestamp': time.time(),
            'bot_name': self.bot_name,
            'session_duration': time.time() - self.session_optimizer.session_start,
        }
        
        # ML insights
        insights['opponent_clusters'] = {}
        for opponent in self.ml_strategy.opponent_stats:
            cluster = self.ml_strategy.get_opponent_cluster(opponent)
            if cluster != 'UNKNOWN':
                insights['opponent_clusters'][opponent] = cluster
                
        # Session optimization insights  
        if len(self.session_optimizer.hand_results) >= 5:
            insights['performance'] = self.session_optimizer.calculate_recent_performance()
            insights['table_dynamics'] = self.session_optimizer.detect_table_dynamics()
            insights['position_edges'] = self.session_optimizer.calculate_position_edge()
            
        # Current strategy adjustments
        insights['ml_adjustments'] = self.ml_strategy.get_session_adjustments()
        insights['optimization_modifiers'] = self.session_optimizer.current_adjustments.copy()
        
        return insights
        
    def save_session_data(self, log_directory: str):
        """Save all session data for future analysis"""
        timestamp = time.strftime('%Y-%m-%d_%H-%M')
        
        # Save ML strategy data
        ml_filepath = os.path.join(log_directory, f'ml_session_{self.bot_name}_{timestamp}.json')
        self.ml_strategy.save_session_data(ml_filepath)
        
        # Save optimization data
        opt_filepath = os.path.join(log_directory, f'optimization_{self.bot_name}_{timestamp}.json')
        self.session_optimizer.save_session_optimization_data(opt_filepath)
        
        # Save integrated performance log
        integrated_filepath = os.path.join(log_directory, f'integrated_{self.bot_name}_{timestamp}.json')
        with open(integrated_filepath, 'w') as f:
            json.dump({
                'bot_name': self.bot_name,
                'bot_style': self.bot_style,
                'performance_log': self.performance_log,
                'final_insights': self.get_current_insights()
            }, f, indent=2, default=str)
            
    def _classify_bet_type(self, decision: Dict, context: Dict) -> str:
        """Classify the type of bet being made"""
        action = decision.get('action', 'check')
        equity = context.get('equity', 0)
        
        if action in ['bet', 'raise']:
            if equity > 65:
                return 'value_bet'
            elif equity < 35:
                return 'bluff'
            else:
                return 'protection_bet'
        return 'passive'
        
    def _identify_primary_opponent(self, game_state: Dict) -> Optional[str]:
        """Identify the primary opponent for this decision"""
        players = game_state.get('players', [])
        active_players = [p for p in players if not p.get('folded', False) and not p.get('is_me', False)]
        
        if len(active_players) == 1:
            return active_players[0].get('name')
        elif len(active_players) > 1:
            # Return the most aggressive player or largest stack
            return max(active_players, key=lambda p: p.get('stack', 0)).get('name')
        return None
        
    def _apply_optimization_modifiers(self, decision: Dict, modifiers: Dict, context: Dict) -> Dict:
        """Apply session optimization modifiers to a decision"""
        modified_decision = decision.copy()
        
        # Apply aggression modifier
        if 'bet_size' in modified_decision:
            modified_decision['bet_size'] *= modifiers.get('aggression_modifier', 1.0)
            modified_decision['bet_size'] *= modifiers.get('value_sizing', 1.0)
            
        # Apply tightness modifier to preflop decisions
        if context.get('street') == 'preflop' and 'action' in modified_decision:
            tightness = modifiers.get('tightness_modifier', 1.0)
            
            if tightness > 1.1 and modified_decision['action'] == 'call':
                equity_threshold = context.get('equity', 0)
                if equity_threshold < 45:  # Marginal hand
                    modified_decision['action'] = 'fold'
                    
        return modified_decision
        
    def _log_decision_enhancement(self, original: Dict, enhanced: Dict, context: Dict):
        """Log decision enhancement for analysis"""
        if original != enhanced:
            enhancement_log = {
                'timestamp': time.time(),
                'original': original,
                'enhanced': enhanced,
                'context': context,
                'bot_name': self.bot_name
            }
            
            # Could save to a separate enhancement log file for detailed analysis
            
    def _handle_risk_management(self, risk_status: Dict):
        """Handle risk management recommendations"""
        recommendation = risk_status.get('recommendation')
        
        if recommendation == 'quit_session':
            # Could set a flag to quit after current hand
            print(f"🚨 {self.bot_name}: Risk management triggered - {risk_status.get('reason')}")
            
        elif recommendation == 'play_tighter':
            # Increase tightness modifier significantly
            self.session_optimizer.current_adjustments['tightness_modifier'] *= 1.3
            print(f"⚠️ {self.bot_name}: Playing tighter - {risk_status.get('reason')}")

# Factory function for multi_bot.py integration
def create_advanced_bot_controller(bot_name: str, bot_style: str, starting_stack: float, big_blind: float) -> AdvancedBotController:
    """Factory function to create advanced bot controller"""
    return AdvancedBotController(bot_name, bot_style, starting_stack, big_blind)

# Helper function for decision enhancement in existing bot loops
def enhance_poker_decision(controller: AdvancedBotController, base_decision: Dict, 
                          game_state: Dict, hand_context: Dict) -> Dict:
    """Helper function to enhance poker decisions with advanced AI"""
    return controller.enhance_decision(base_decision, game_state, hand_context)

# Helper function for opponent action tracking
def track_opponent_action(controller: AdvancedBotController, opponent: str, action: str, 
                         position: str, street: str, bet_size: float = None):
    """Helper function to track opponent actions"""
    controller.update_with_opponent_action(opponent, action, position, street, bet_size)

# Helper function for hand completion
def complete_hand_with_learning(controller: AdvancedBotController, hand_data: Dict):
    """Helper function to complete hand with learning updates"""
    controller.complete_hand(hand_data)
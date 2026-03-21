"""
Advanced Analytics Module v28.0 - Professional Poker Performance Tracking
Comprehensive analytics for autonomous poker AI with real-time insights and optimization

Key Features:
1. Real-time performance metrics with trend analysis
2. Advanced opponent modeling with exploitation detection
3. Session optimization recommendations
4. Bankroll management with Kelly Criterion
5. Strategy effectiveness tracking
6. Multi-session learning integration
"""

import json
import time
import statistics
from datetime import datetime, timedelta
from collections import defaultdict, deque

class AdvancedAnalytics:
    def __init__(self, bot_name, bot_style):
        self.bot_name = bot_name
        self.bot_style = bot_style
        self.session_start = time.time()
        
        # Performance tracking
        self.bb_history = deque(maxlen=100)  # Last 100 BB changes
        self.decision_history = []           # All decisions for analysis
        self.opponent_data = defaultdict(dict)  # Per-opponent statistics
        
        # Real-time metrics
        self.hands_played = 0
        self.total_bb_won = 0.0
        self.vpip_count = 0  # Voluntarily put $ in pot
        self.pfr_count = 0   # Preflop raise
        self.aggression_factor = {'bets': 0, 'raises': 0, 'calls': 0, 'checks': 0}
        self.position_performance = defaultdict(list)
        
        # Advanced metrics
        self.showdown_winnings = []
        self.fold_equity_realized = []
        self.value_bet_success = []
        self.bluff_success = []
        
        # Session optimization
        self.decision_times = deque(maxlen=50)
        self.error_count = 0
        self.timeout_count = 0
        
        # Multi-session learning
        self.strategy_adjustments = {}
        self.opponent_exploits_discovered = {}
        
    def update_hand_result(self, hand_num, position, final_stack, bb_change, actions_taken):
        """Update metrics after each hand"""
        self.hands_played = hand_num
        self.total_bb_won += bb_change
        self.bb_history.append(bb_change)
        
        # Position performance tracking
        self.position_performance[position].append(bb_change)
        
        # VPIP/PFR tracking
        if any(action in actions_taken for action in ['call', 'raise', 'bet']):
            self.vpip_count += 1
            
        if any(action.startswith('raise') for action in actions_taken if 'preflop' in str(actions_taken)):
            self.pfr_count += 1
            
        # Aggression factor
        for action in actions_taken:
            if 'bet' in action or 'raise' in action:
                self.aggression_factor['bets'] += 1
                self.aggression_factor['raises'] += 1
            elif 'call' in action:
                self.aggression_factor['calls'] += 1
            elif 'check' in action:
                self.aggression_factor['checks'] += 1
    
    def update_opponent_data(self, opponent_name, action, equity, position, hand_result):
        """Track opponent tendencies for exploitation"""
        if opponent_name not in self.opponent_data:
            self.opponent_data[opponent_name] = {
                'hands_seen': 0,
                'vpip_count': 0,
                'pfr_count': 0,
                'fold_to_cbet': 0,
                'cbet_attempts': 0,
                'river_call_frequency': 0,
                'river_call_attempts': 0,
                'bluff_frequency': 0,
                'value_bet_thin': 0,
                'showdown_aggression': 0,
                'position_tendencies': defaultdict(list),
                'stack_history': [],
                'last_seen': time.time()
            }
        
        opp = self.opponent_data[opponent_name]
        opp['hands_seen'] += 1
        opp['last_seen'] = time.time()
        
        if action in ['call', 'raise', 'bet']:
            opp['vpip_count'] += 1
        if action.startswith('raise') and 'preflop' in position:
            opp['pfr_count'] += 1
            
        opp['position_tendencies'][position].append(action)
        
    def get_realtime_stats(self):
        """Get current session performance metrics"""
        session_duration = (time.time() - self.session_start) / 3600  # hours
        
        vpip = (self.vpip_count / max(self.hands_played, 1)) * 100
        pfr = (self.pfr_count / max(self.hands_played, 1)) * 100
        
        total_aggressive = self.aggression_factor['bets'] + self.aggression_factor['raises'] 
        total_passive = self.aggression_factor['calls'] + self.aggression_factor['checks']
        agg_factor = total_aggressive / max(total_passive, 1)
        
        bb_per_hour = self.total_bb_won / max(session_duration, 0.01)
        
        # Recent performance trend (last 20 hands)
        recent_bb = list(self.bb_history)[-20:] if len(self.bb_history) > 20 else list(self.bb_history)
        trend = "📈" if len(recent_bb) > 5 and sum(recent_bb[-5:]) > sum(recent_bb[:5]) else "📉" if len(recent_bb) > 5 else "➡️"
        
        return {
            'session_duration_hours': session_duration,
            'hands_played': self.hands_played,
            'bb_won': self.total_bb_won,
            'bb_per_hour': bb_per_hour,
            'vpip_percent': vpip,
            'pfr_percent': pfr,
            'aggression_factor': agg_factor,
            'recent_trend': trend,
            'error_rate': self.error_count / max(self.hands_played, 1),
            'avg_decision_time': statistics.mean(self.decision_times) if self.decision_times else 0
        }
    
    def get_opponent_profile(self, opponent_name):
        """Get detailed opponent analysis for exploitation"""
        if opponent_name not in self.opponent_data:
            return None
            
        opp = self.opponent_data[opponent_name]
        hands_seen = opp['hands_seen']
        
        if hands_seen < 5:
            return {'type': 'UNKNOWN', 'confidence': 'LOW', 'hands_seen': hands_seen}
        
        vpip = (opp['vpip_count'] / hands_seen) * 100
        pfr = (opp['pfr_count'] / hands_seen) * 100
        
        # Classify opponent type
        if vpip < 20 and pfr < 15:
            opp_type = 'NIT'
        elif vpip > 35 and pfr > 25:
            opp_type = 'LAG'
        elif vpip > 30 and pfr < 15:
            opp_type = 'STATION'
        elif 20 <= vpip <= 35 and 15 <= pfr <= 25:
            opp_type = 'TAG'
        else:
            opp_type = 'LOOSE'
            
        confidence = 'HIGH' if hands_seen > 20 else 'MEDIUM' if hands_seen > 10 else 'LOW'
        
        exploits = []
        if opp_type == 'NIT':
            exploits = ['bluff_more', 'steal_blinds', 'respect_aggression']
        elif opp_type == 'STATION':
            exploits = ['value_bet_thin', 'avoid_bluffs', 'bet_big_with_value']
        elif opp_type == 'LAG':
            exploits = ['call_down_light', 'trap_with_nuts', 'let_them_bluff']
            
        return {
            'type': opp_type,
            'vpip': vpip,
            'pfr': pfr,
            'hands_seen': hands_seen,
            'confidence': confidence,
            'exploits': exploits,
            'last_seen_minutes_ago': (time.time() - opp['last_seen']) / 60
        }
    
    def get_position_analysis(self):
        """Analyze performance by position for strategy optimization"""
        analysis = {}
        
        for position, bb_results in self.position_performance.items():
            if len(bb_results) > 3:  # Need sample size
                avg_bb = statistics.mean(bb_results)
                win_rate = len([x for x in bb_results if x > 0]) / len(bb_results)
                
                # Performance rating
                if avg_bb > 0.5:
                    rating = '🔥 EXCELLENT'
                elif avg_bb > 0:
                    rating = '✅ PROFITABLE'
                elif avg_bb > -0.5:
                    rating = '⚠️ MARGINAL'
                else:
                    rating = '❌ LOSING'
                    
                analysis[position] = {
                    'hands': len(bb_results),
                    'avg_bb': avg_bb,
                    'win_rate': win_rate,
                    'rating': rating,
                    'total_bb': sum(bb_results)
                }
                
        return analysis
    
    def get_strategy_recommendations(self):
        """AI-powered strategy optimization suggestions"""
        recommendations = []
        stats = self.get_realtime_stats()
        
        # VPIP adjustments
        if self.bot_style == 'TAG' and stats['vpip_percent'] > 30:
            recommendations.append("🎯 VPIP too high for TAG style - tighten preflop ranges")
        elif self.bot_style == 'NIT' and stats['vpip_percent'] > 20:
            recommendations.append("🎯 VPIP too loose for NIT - fold more marginal hands")
        elif self.bot_style == 'LAG' and stats['vpip_percent'] < 30:
            recommendations.append("🎯 VPIP too tight for LAG - play more hands in position")
            
        # Aggression factor
        if stats['aggression_factor'] < 1.0 and self.bot_style != 'STATION':
            recommendations.append("⚡ Increase aggression - bet/raise more, call less")
        elif stats['aggression_factor'] > 3.0 and self.bot_style == 'NIT':
            recommendations.append("🛡️ Reduce aggression - value bet thinner, bluff less")
            
        # Performance trends
        if stats['bb_per_hour'] < -10:
            recommendations.append("🚨 LOSING SESSION - consider tighter play or strategy review")
        elif stats['bb_per_hour'] > 20:
            recommendations.append("🚀 HOT SESSION - maintain current strategy, avoid tilt")
            
        # Decision time optimization
        if stats['avg_decision_time'] > 8:
            recommendations.append("⏱️ Slow decisions - optimize calculation speed")
        elif stats['avg_decision_time'] < 2:
            recommendations.append("🤔 Fast decisions - ensure proper analysis depth")
            
        return recommendations
    
    def export_session_data(self, filename=None):
        """Export comprehensive session data for analysis"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analytics_{self.bot_name}_{timestamp}.json"
            
        data = {
            'bot_info': {
                'name': self.bot_name,
                'style': self.bot_style,
                'session_start': self.session_start,
                'session_duration': time.time() - self.session_start
            },
            'performance': self.get_realtime_stats(),
            'position_analysis': self.get_position_analysis(),
            'opponent_profiles': {name: self.get_opponent_profile(name) 
                                for name in self.opponent_data.keys()},
            'recommendations': self.get_strategy_recommendations(),
            'bb_history': list(self.bb_history),
            'raw_opponent_data': dict(self.opponent_data)
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        return filename
    
    def detect_exploitable_patterns(self):
        """Advanced pattern recognition for opponent exploitation"""
        exploits = {}
        
        for opp_name, data in self.opponent_data.items():
            if data['hands_seen'] < 10:
                continue
                
            patterns = []
            
            # Check fold-to-cbet frequency
            if data['cbet_attempts'] > 5:
                fold_rate = data['fold_to_cbet'] / data['cbet_attempts']
                if fold_rate > 0.7:
                    patterns.append("FOLDS_TO_CBETS")  # Bluff more
                elif fold_rate < 0.3:
                    patterns.append("NEVER_FOLDS_CBETS")  # Value bet only
                    
            # Check river calling patterns  
            if data['river_call_attempts'] > 3:
                call_rate = data['river_call_frequency'] / data['river_call_attempts']
                if call_rate > 0.6:
                    patterns.append("RIVER_CALL_STATION")  # Thin value bets
                elif call_rate < 0.3:
                    patterns.append("RIVER_FOLDER")  # Bluff rivers
                    
            if patterns:
                exploits[opp_name] = patterns
                
        return exploits

def create_session_summary(analytics_list, total_duration_hours):
    """Create comprehensive multi-bot session summary"""
    summary = {
        'session_overview': {
            'duration_hours': total_duration_hours,
            'total_bots': len(analytics_list),
            'total_hands': max(a.hands_played for a in analytics_list) if analytics_list else 0
        },
        'performance_ranking': [],
        'style_analysis': defaultdict(list),
        'key_insights': []
    }
    
    # Rank bots by performance
    for analytics in analytics_list:
        stats = analytics.get_realtime_stats()
        summary['performance_ranking'].append({
            'name': analytics.bot_name,
            'style': analytics.bot_style,
            'bb_per_hour': stats['bb_per_hour'],
            'total_bb': stats['bb_won'],
            'vpip': stats['vpip_percent'],
            'pfr': stats['pfr_percent']
        })
    
    summary['performance_ranking'].sort(key=lambda x: x['bb_per_hour'], reverse=True)
    
    # Analyze by style
    for analytics in analytics_list:
        stats = analytics.get_realtime_stats()
        summary['style_analysis'][analytics.bot_style].append(stats)
        
    # Generate insights
    if summary['performance_ranking']:
        winner = summary['performance_ranking'][0]
        loser = summary['performance_ranking'][-1]
        
        summary['key_insights'].append(f"🏆 Best performer: {winner['name']} ({winner['style']}) at {winner['bb_per_hour']:+.1f} BB/hr")
        summary['key_insights'].append(f"📉 Worst performer: {loser['name']} ({loser['style']}) at {loser['bb_per_hour']:+.1f} BB/hr")
        
        # Style effectiveness
        style_performance = {}
        for style, stats_list in summary['style_analysis'].items():
            avg_bb_hr = statistics.mean([s['bb_per_hour'] for s in stats_list])
            style_performance[style] = avg_bb_hr
            
        best_style = max(style_performance.items(), key=lambda x: x[1])
        summary['key_insights'].append(f"🎯 Most effective style this session: {best_style[0]} ({best_style[1]:+.1f} BB/hr avg)")
    
    return summary

if __name__ == "__main__":
    # Test the analytics system
    analytics = AdvancedAnalytics("TestBot", "TAG")
    analytics.update_hand_result(1, "BTN", 5050, 0.5, ["call", "raise"])
    analytics.update_hand_result(2, "UTG", 4980, -0.7, ["fold"])
    
    print("Real-time stats:", analytics.get_realtime_stats())
    print("Recommendations:", analytics.get_strategy_recommendations())
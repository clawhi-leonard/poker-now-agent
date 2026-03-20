"""
Real-time Performance Analytics for Poker Bots
Tracks win rates, decision quality, and strategic effectiveness
"""
import json
import time
import os
from collections import defaultdict

PERFORMANCE_FILE = os.path.join(os.path.dirname(__file__), "performance_stats.json")

class PerformanceTracker:
    def __init__(self):
        self.session_start = time.time()
        self.bot_stats = defaultdict(lambda: {
            "hands_played": 0,
            "total_winnings": 0,
            "bb_won": 0.0,
            "vpip_count": 0,
            "pfr_count": 0,
            "aggression_actions": 0,
            "passive_actions": 0,
            "showdowns": 0,
            "showdown_wins": 0,
            "big_pots_won": 0,   # pots > 10 BB
            "big_pots_lost": 0,
            "texture_decisions": defaultdict(int),  # track decisions by board texture
            "position_performance": defaultdict(lambda: {"hands": 0, "winnings": 0}),
            "session_high": 0,
            "session_low": 0,
            "starting_stack": 5000
        })
        self.hand_number = 0
        self.current_pot_size = 0
        self.current_hand_active = {}
        
    def new_hand(self):
        """Call at start of each hand"""
        self.hand_number += 1
        self.current_hand_active = {}
        self.current_pot_size = 0
        
    def track_decision(self, bot_name, action, amount, equity, board_texture, position, stack):
        """Track each decision made by a bot"""
        stats = self.bot_stats[bot_name]
        
        # Basic action tracking
        if action in ["raise", "bet"]:
            stats["aggression_actions"] += 1
        elif action in ["call", "check"]:
            stats["passive_actions"] += 1
            
        # Track VPIP (voluntarily put money in pot preflop)
        if position in ["preflop"] and action in ["call", "raise"]:
            stats["vpip_count"] += 1
            
        # Track PFR (preflop raise)
        if position in ["preflop"] and action == "raise":
            stats["pfr_count"] += 1
            
        # Track texture-based decisions
        if board_texture:
            stats["texture_decisions"][board_texture] += 1
            
        # Track position performance
        pos_key = position if position in ["UTG", "BTN", "SB", "BB"] else "other"
        stats["position_performance"][pos_key]["hands"] += 1
        
        # Update session high/low
        if stack > stats["session_high"]:
            stats["session_high"] = stack
        if stack < stats["session_low"] or stats["session_low"] == 0:
            stats["session_low"] = stack
            
        self.current_hand_active[bot_name] = True
        
    def track_hand_result(self, bot_name, winnings, final_stack):
        """Track the result of a completed hand"""
        stats = self.bot_stats[bot_name]
        
        if bot_name in self.current_hand_active:
            stats["hands_played"] += 1
            
        if winnings != 0:
            stats["total_winnings"] += winnings
            stats["bb_won"] = stats["total_winnings"] / 10.0  # Convert to big blinds
            
            # Track big pot performance
            if abs(winnings) > 100:  # > 10 BB
                if winnings > 0:
                    stats["big_pots_won"] += 1
                else:
                    stats["big_pots_lost"] += 1
                    
            # Track position performance
            pos_key = "other"  # Would need to track position better
            stats["position_performance"][pos_key]["winnings"] += winnings
            
    def get_session_summary(self):
        """Get current session performance summary"""
        summary = {
            "session_duration_minutes": (time.time() - self.session_start) / 60,
            "hands_played": self.hand_number,
            "bot_performance": {}
        }
        
        for bot_name, stats in self.bot_stats.items():
            if stats["hands_played"] > 0:
                vpip = (stats["vpip_count"] / max(stats["hands_played"], 1)) * 100
                pfr = (stats["pfr_count"] / max(stats["hands_played"], 1)) * 100
                aggression = stats["aggression_actions"] / max(
                    stats["aggression_actions"] + stats["passive_actions"], 1)
                
                bb_per_hour = 0
                if summary["session_duration_minutes"] > 0:
                    bb_per_hour = stats["bb_won"] / (summary["session_duration_minutes"] / 60)
                
                summary["bot_performance"][bot_name] = {
                    "bb_won": round(stats["bb_won"], 1),
                    "bb_per_hour": round(bb_per_hour, 1),
                    "hands_played": stats["hands_played"],
                    "vpip": round(vpip, 1),
                    "pfr": round(pfr, 1),
                    "aggression": round(aggression * 100, 1),
                    "session_high": stats["session_high"],
                    "session_low": stats["session_low"],
                    "roi": round((stats["total_winnings"] / stats["starting_stack"]) * 100, 1),
                    "big_pots": f"{stats['big_pots_won']}-{stats['big_pots_lost']}",
                    "texture_decisions": dict(stats["texture_decisions"])
                }
                
        return summary
        
    def log_performance(self, log_func):
        """Log current performance to the provided log function"""
        summary = self.get_session_summary()
        
        log_func(f"📊 PERFORMANCE ({summary['hands_played']}h, {summary['session_duration_minutes']:.1f}m)")
        
        for bot_name, perf in summary["bot_performance"].items():
            log_func(f"   {bot_name}: {perf['bb_won']}bb ({perf['bb_per_hour']}bb/hr) | "
                    f"VPIP:{perf['vpip']}% PFR:{perf['pfr']}% AGG:{perf['aggression']}% | "
                    f"ROI:{perf['roi']}% | Range:{perf['session_low']}-{perf['session_high']}")
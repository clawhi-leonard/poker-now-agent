"""
Analytics Integration Patch v28.0
Quick integration of advanced analytics into existing multi_bot.py system

This module provides drop-in analytics enhancement without disrupting the proven v27 system.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from advanced_analytics import AdvancedAnalytics, create_session_summary
import json
import time

# Global analytics instances (one per bot)
bot_analytics = {}

def initialize_analytics(bot_profiles):
    """Initialize analytics for all bots at session start"""
    global bot_analytics
    bot_analytics = {}
    
    for profile in bot_profiles:
        bot_name = profile['name']
        bot_style = profile['style']
        bot_analytics[bot_name] = AdvancedAnalytics(bot_name, bot_style)
        print(f"   📊 Analytics initialized for {bot_name} ({bot_style})")

def update_hand_analytics(bot_name, hand_num, position, stack, bb_change, actions):
    """Update analytics after each hand (call from bot_loop)"""
    if bot_name in bot_analytics:
        bot_analytics[bot_name].update_hand_result(
            hand_num, position, stack, bb_change, actions
        )

def update_opponent_analytics(bot_name, opponent, action, equity, position, result):
    """Track opponent behavior for exploitation (call from decision points)"""
    if bot_name in bot_analytics:
        bot_analytics[bot_name].update_opponent_data(
            opponent, action, equity, position, result
        )

def get_enhanced_status_report():
    """Generate enhanced status report with analytics"""
    if not bot_analytics:
        return "📊 Analytics not initialized"
    
    reports = []
    
    for bot_name, analytics in bot_analytics.items():
        stats = analytics.get_realtime_stats()
        
        # Basic performance
        bb_hr = f"{stats['bb_per_hour']:+.1f}bb/hr" if stats['bb_per_hour'] != 0 else "0.0bb/hr"
        trend = stats['recent_trend']
        
        reports.append(f"{bot_name}: {bb_hr} {trend} ({stats['hands_played']}h)")
        
        # Opponent insights (if available)
        exploits = analytics.detect_exploitable_patterns()
        if exploits:
            for opp, patterns in exploits.items():
                reports.append(f"   🎯 {opp}: {', '.join(patterns)}")
    
    return "📊 ENHANCED ANALYTICS | " + " | ".join(reports)

def get_session_recommendations():
    """Get AI-powered strategy recommendations for all bots"""
    recommendations = []
    
    for bot_name, analytics in bot_analytics.items():
        recs = analytics.get_strategy_recommendations()
        if recs:
            recommendations.append(f"\n🤖 {bot_name}:")
            recommendations.extend([f"   {rec}" for rec in recs[:2]])  # Top 2 recommendations
    
    return "\n".join(recommendations) if recommendations else ""

def export_session_analytics(log_dir="logs"):
    """Export comprehensive analytics at session end"""
    if not bot_analytics:
        return []
    
    export_files = []
    
    # Export individual bot analytics
    for bot_name, analytics in bot_analytics.items():
        filename = os.path.join(log_dir, f"analytics_{bot_name}_session.json")
        analytics.export_session_data(filename)
        export_files.append(filename)
    
    # Create session summary
    session_duration = max(
        (time.time() - analytics.session_start) / 3600 
        for analytics in bot_analytics.values()
    ) if bot_analytics else 0
    
    summary = create_session_summary(list(bot_analytics.values()), session_duration)
    summary_file = os.path.join(log_dir, "session_summary_analytics.json")
    
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    export_files.append(summary_file)
    
    return export_files

def get_opponent_profile(bot_name, opponent_name):
    """Get detailed opponent analysis for decision making"""
    if bot_name in bot_analytics:
        return bot_analytics[bot_name].get_opponent_profile(opponent_name)
    return None

def get_position_performance(bot_name):
    """Get position-based performance analysis"""
    if bot_name in bot_analytics:
        return bot_analytics[bot_name].get_position_analysis()
    return {}

# Integration points for multi_bot.py:
# 
# 1. In main() function after BOT_PROFILES definition:
#    from analytics_integration import initialize_analytics
#    initialize_analytics(BOT_PROFILES[:NUM_BOTS])
#
# 2. In status_reporter() function:
#    from analytics_integration import get_enhanced_status_report, get_session_recommendations
#    enhanced_report = get_enhanced_status_report()
#    recommendations = get_session_recommendations()
#
# 3. In bot_loop() after action completion:
#    from analytics_integration import update_hand_analytics, update_opponent_analytics
#    update_hand_analytics(name, hand_num, position, stack, bb_change, actions_this_hand)
#
# 4. At session end in main():
#    from analytics_integration import export_session_analytics
#    analytics_files = export_session_analytics(LOG_DIR)
#    log(f"📊 Analytics exported: {analytics_files}")

if __name__ == "__main__":
    # Test integration
    print("Testing Analytics Integration...")
    
    # Mock bot profiles
    test_profiles = [
        {'name': 'TestBot1', 'style': 'TAG'},
        {'name': 'TestBot2', 'style': 'LAG'}
    ]
    
    initialize_analytics(test_profiles)
    update_hand_analytics('TestBot1', 1, 'BTN', 5050, 0.5, ['call', 'raise'])
    update_hand_analytics('TestBot2', 1, 'UTG', 4950, -0.5, ['fold'])
    
    print("\nEnhanced Status:")
    print(get_enhanced_status_report())
    
    print("\nRecommendations:")
    print(get_session_recommendations())
    
    print("\nExported files:")
    print(export_session_analytics("."))
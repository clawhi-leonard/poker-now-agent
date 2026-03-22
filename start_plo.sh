#!/bin/bash
# PLO Poker Bot Launcher - Permanent Solution
# This script ensures PLO configuration always works

echo "🎯 Starting PLO Poker Bot with proven configuration..."
echo "📅 $(date)"
echo "🔧 Solution: Options → Game Configurations → Select PLO → UPDATE GAME"
echo ""

# Switch to workspace 2
echo "🖥️ Switching to workspace 2..."
aerospace workspace 2

# Clean up any existing processes
echo "🧹 Cleaning up previous sessions..."
pkill -f "multi_bot" 2>/dev/null || true
pkill -f "fresh_plo" 2>/dev/null || true

# Navigate to project directory
cd ~/Projects/poker-now-agent

# Verify PLO files exist
if [ ! -f "multi_bot_plo.py" ]; then
    echo "❌ Error: multi_bot_plo.py not found!"
    exit 1
fi

if [ ! -f "perfect_plo_config.py" ]; then
    echo "❌ Error: perfect_plo_config.py not found!"
    exit 1
fi

echo "✅ PLO configuration files verified"
echo ""

# Start PLO session
echo "🚀 Launching PLO session with working configuration..."
python3 fresh_plo_bot.py

echo ""
echo "🎉 PLO session completed!"
echo "📊 Check game logs for 4-card hand verification"
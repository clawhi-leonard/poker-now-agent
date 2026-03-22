#!/usr/bin/env python3
"""
Fresh PLO Bot - Completely isolated PLO session
No cached state, no old URLs, pure PLO poker
"""

import os
import subprocess
import sys
import time

# Force fresh start
os.environ.pop('game_url_global', None)
os.environ['FORCE_NEW_GAME'] = '1' 
os.environ['POKER_VARIANT'] = 'PLO'

# Switch to workspace 2
try:
    subprocess.run(['aerospace', 'workspace', '2'], check=True)
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Switched to workspace 2")
except:
    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Could not switch workspace")

# Clear all browser state
subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
subprocess.run(['pkill', '-f', 'playwright'], capture_output=True)

print(f"[{time.strftime('%H:%M:%S')}] 🚀 Starting FRESH PLO session...")
print(f"[{time.strftime('%H:%M:%S')}] 🎯 Game type: Pot Limit Omaha Hi")

# Import and run the modified PLO bot
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reset global state
import multi_bot_plo
multi_bot_plo.game_url_global = None

# Execute main
if __name__ == "__main__":
    print(f"[{time.strftime('%H:%M:%S')}] 🃏 Launching PLO Multi-Bot Arena...")
    import asyncio
    asyncio.run(multi_bot_plo.main())
"""
PLO-specific session runner
Extends multi_bot.py with PLO-specific configurations and game creation
"""

import asyncio
import subprocess
import sys
import time

async def run_plo_session():
    """Run a PLO-specific session with proper configuration"""
    print("🃏 Starting PLO (Pot Limit Omaha Hi) Session")
    print("=" * 60)
    
    # For now, let's run the standard multi_bot and manually configure PLO
    # The hand evaluation already supports PLO (4-card detection)
    
    print("🚀 Launching multi_bot.py...")
    print("   NOTE: After game creation, we'll need to:")
    print("   1. Click Options -> Game Configurations")  
    print("   2. Change 'Poker Variant' to 'Pot Limit Omaha Hi'")
    print("   3. Apply settings")
    print()
    
    # Run multi_bot.py normally - it will create a Hold'em game first
    # Then we can modify it to PLO through the interface
    result = subprocess.run([
        sys.executable, "multi_bot.py"
    ], capture_output=False)
    
    return result.returncode

if __name__ == "__main__":
    asyncio.run(run_plo_session())
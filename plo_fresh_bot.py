#!/usr/bin/env python3
"""
PLO Fresh Bot - Creates PLO games from the start
Modifies the game creation process to set PLO variant during initial setup
"""

import os
import subprocess
import sys
import time
import asyncio

print(f"[{time.strftime('%H:%M:%S')}] 🚀 Starting FRESH PLO session...")

# Switch to workspace 2
try:
    subprocess.run(['aerospace', 'workspace', '2'], check=True)
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Switched to workspace 2")
except:
    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Could not switch workspace")

# Clear all browser state
subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
subprocess.run(['pkill', '-f', 'playwright'], capture_output=True)

print(f"[{time.strftime('%H:%M:%S')}] 🃏 Creating PLO-specific game...")

# Import the multi_bot and modify it for PLO
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def create_plo_game():
    """Create a game that's PLO from the start"""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
    
    print(f"[{time.strftime('%H:%M:%S')}] 🌐 Launching browser...")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Apply stealth
        stealth = Stealth()
        await stealth.async_inject(page)
        
        print(f"[{time.strftime('%H:%M:%S')}] 🎰 Creating PLO game...")
        
        # Go to PokerNow
        await page.goto("https://www.pokernow.club", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Click "Start a New Game"
        await page.click('a:has-text("Start a New Game")')
        await asyncio.sleep(3)
        
        # Fill nickname
        await page.fill('input[placeholder="Your Nickname"]', "Clawhi")
        await asyncio.sleep(1)
        
        # Click "Create Game" 
        await page.click('button:has-text("Create Game")')
        
        # Wait for game creation and PLO config
        for i in range(60):
            if "/games/" in page.url:
                print(f"[{time.strftime('%H:%M:%S')}] ✅ Game created: {page.url}")
                break
            await asyncio.sleep(1)
        
        if "/games/" not in page.url:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ Game creation failed")
            return None
            
        # Now configure PLO immediately  
        print(f"[{time.strftime('%H:%M:%S')}] 🔧 Configuring PLO...")
        
        await page.click('button:has-text("Options")')
        await asyncio.sleep(2)
        
        await page.click('button:has-text("Game Configurations")')
        await asyncio.sleep(2)
        
        # Change to PLO
        await page.select_option('select', label="Pot Limit Omaha Hi")
        print(f"[{time.strftime('%H:%M:%S')}] ✅ Set to Pot Limit Omaha Hi")
        
        # Go back
        await page.click('button:has-text("Back")')
        await asyncio.sleep(2)
        
        print(f"[{time.strftime('%H:%M:%S')}] 🎯 PLO game ready!")
        
        # Keep browser open for manual verification
        input("Press Enter to close browser...")
        await browser.close()
        
        return page.url

if __name__ == "__main__":
    asyncio.run(create_plo_game())
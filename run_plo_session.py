"""
PLO Session Runner
Creates a fresh game and converts it to PLO format, then runs the bots
"""

import asyncio
import os
import subprocess
import sys
from playwright.async_api import async_playwright
import time
import random

async def convert_to_plo(page, game_url):
    """Convert an existing PokerNow game to PLO format"""
    print("🔄 Converting game to PLO format...")
    
    try:
        # Go to the game page
        await page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # Click Options button
        print("   Clicking Options...")
        options_clicked = False
        for sel in ['button:has-text("Options")', 'button[class*="options"]', 'button:contains("Options")']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    options_clicked = True
                    print("   ✅ Options clicked")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not options_clicked:
            print("   ❌ Could not find Options button")
            return False
        
        # Click Game Configurations
        print("   Clicking Game Configurations...")
        config_clicked = False
        for sel in ['button:has-text("Game Configurations")', 'button:has-text("Configuration")', 'a:has-text("Configuration")']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    config_clicked = True
                    print("   ✅ Game Configurations clicked")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not config_clicked:
            print("   ❌ Could not find Game Configurations button")
            return False
        
        # Find and change poker variant dropdown
        print("   Looking for Poker Variant dropdown...")
        variant_changed = False
        
        # Try multiple dropdown selectors
        for sel in ['select[name*="variant"]', 'select[id*="variant"]', 'select:has-text("Hold")', 'select']:
            try:
                dropdown = await page.query_selector(sel)
                if dropdown and await dropdown.is_visible():
                    # Get current value
                    current_value = await dropdown.input_value()
                    print(f"   Found dropdown with current value: {current_value}")
                    
                    # Select PLO option
                    await dropdown.select_option(value="PLO")  # or try other PLO values
                    variant_changed = True
                    print("   ✅ Changed to PLO")
                    break
            except Exception as e:
                print(f"   Dropdown {sel} failed: {e}")
                continue
        
        if not variant_changed:
            print("   ⚠️ Could not find/change variant dropdown - trying different approach...")
            # Try clicking on dropdown options directly
            for text in ["Pot Limit Omaha", "Omaha", "PLO"]:
                try:
                    el = await page.query_selector(f'option:has-text("{text}")')
                    if el:
                        await el.click()
                        variant_changed = True
                        print(f"   ✅ Selected {text}")
                        break
                except:
                    continue
        
        # Apply/Save settings
        print("   Applying settings...")
        for sel in ['button:has-text("Apply")', 'button:has-text("Save")', 'button[type="submit"]']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    print("   ✅ Settings applied")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        return variant_changed
        
    except Exception as e:
        print(f"   ❌ PLO conversion failed: {e}")
        return False

async def run_multibot_with_plo():
    """Create a game, convert to PLO, then run multi-bot"""
    
    print("🃏 PLO Bot Session Starting")
    print("=" * 50)
    print("🎯 Mission: Create PLO game and run autonomous bots")
    print()
    
    # Start the multi_bot process but intercept after game creation
    print("🚀 Starting game creation...")
    
    # For now, let's run multi_bot normally and let it create a Hold'em game
    # Then we'll manually note the game URL and convert it
    
    cmd = [sys.executable, "multi_bot.py"]
    
    # Start subprocess and monitor output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    game_url = None
    
    # Monitor output for game creation
    for line in iter(process.stdout.readline, ''):
        print(line.strip())
        
        # Look for game URL
        if "Game created:" in line and "games/" in line:
            # Extract URL
            parts = line.split("Game created:")
            if len(parts) > 1:
                game_url = parts[1].strip()
                print(f"\n🎯 GAME URL DETECTED: {game_url}")
                break
        
        # Also check for "✅ Game created"
        if "✅ Game created:" in line:
            parts = line.split("✅ Game created:")
            if len(parts) > 1:
                game_url = parts[1].strip()
                print(f"\n🎯 GAME URL DETECTED: {game_url}")
                break
    
    if game_url:
        print(f"\n🔄 Now converting {game_url} to PLO...")
        
        # Create a separate browser instance to convert to PLO
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            success = await convert_to_plo(page, game_url)
            
            if success:
                print("✅ PLO conversion successful!")
            else:
                print("❌ PLO conversion failed")
            
            await browser.close()
        
        print("\n🤖 Continuing with bot gameplay...")
    
    # Let the process continue
    process.wait()
    
    return process.returncode

if __name__ == "__main__":
    asyncio.run(run_multibot_with_plo())
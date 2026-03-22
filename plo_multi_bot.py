"""
PLO Multi-Bot - Modified version of multi_bot.py for Pot Limit Omaha
Creates game, converts to PLO format, then runs all bots
"""

import sys
import os
import asyncio
import time
from playwright.async_api import async_playwright
import random

# Import the existing multi_bot functionality
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from multi_bot import create_game, dismiss_cookie_banner, wait_for_recaptcha_clear

LOG_DIR = "logs"

def log(message):
    timestamp = time.strftime("[%H:%M:%S]", time.localtime())
    print(f"{timestamp} {message}")

async def convert_game_to_plo(page, game_url):
    """Convert a freshly created game to PLO format"""
    log("🔄 Converting game to PLO (Pot Limit Omaha Hi)...")
    
    try:
        # Go to the game page
        await page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # Dismiss any overlays/banners
        await dismiss_cookie_banner(page)
        await asyncio.sleep(1)
        
        # Click Options button
        log("   Clicking Options...")
        options_clicked = False
        
        for attempt in range(3):
            try:
                # Look for Options button
                options_btn = await page.query_selector('button:has-text("Options")')
                if options_btn and await options_btn.is_visible():
                    await options_btn.click()
                    options_clicked = True
                    log("   ✅ Options clicked")
                    await asyncio.sleep(2)
                    break
            except Exception as e:
                log(f"   Options attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)
        
        if not options_clicked:
            log("   ❌ Could not find Options button")
            return False
        
        # Click Game Configurations
        log("   Clicking Game Configurations...")
        config_clicked = False
        
        for attempt in range(3):
            try:
                config_btn = await page.query_selector('button:has-text("Game Configurations")')
                if config_btn and await config_btn.is_visible():
                    await config_btn.click()
                    config_clicked = True
                    log("   ✅ Game Configurations clicked")
                    await asyncio.sleep(2)
                    break
            except Exception as e:
                log(f"   Config attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)
        
        if not config_clicked:
            log("   ❌ Could not find Game Configurations button")
            return False
        
        # Find and change poker variant dropdown
        log("   Looking for Poker Variant dropdown...")
        variant_changed = False
        
        for attempt in range(3):
            try:
                # Look for the dropdown
                dropdown = await page.query_selector('select:has-text("Hold"), select[name*="variant"], select[id*="variant"]')
                if dropdown and await dropdown.is_visible():
                    # Check if it's disabled
                    is_disabled = await dropdown.evaluate('el => el.disabled')
                    if is_disabled:
                        log("   ⚠️ Dropdown is disabled - likely because players are seated")
                        return False
                    
                    # Select PLO option
                    await dropdown.select_option(label="Pot Limit Omaha Hi")
                    variant_changed = True
                    log("   ✅ Changed to Pot Limit Omaha Hi")
                    await asyncio.sleep(1)
                    break
                    
            except Exception as e:
                log(f"   Dropdown attempt {attempt + 1} failed: {e}")
                
                # Try alternative approach - click option directly  
                try:
                    plo_option = await page.query_selector('option:has-text("Pot Limit Omaha Hi")')
                    if plo_option:
                        await plo_option.click()
                        variant_changed = True
                        log("   ✅ Selected Pot Limit Omaha Hi (direct click)")
                        break
                except:
                    pass
                
                await asyncio.sleep(1)
        
        if not variant_changed:
            log("   ❌ Could not change poker variant")
            return False
        
        # Apply/Save settings (there might not be an explicit save button)
        log("   Looking for Apply/Save button...")
        try:
            for sel in ['button:has-text("Apply")', 'button:has-text("Save")', 'button:has-text("Update")']:
                save_btn = await page.query_selector(sel)
                if save_btn and await save_btn.is_visible():
                    await save_btn.click()
                    log("   ✅ Settings applied")
                    await asyncio.sleep(2)
                    break
        except Exception as e:
            log(f"   Apply button: {e}")
            # Some variants may auto-save, so continue anyway
        
        # Go back to main game view to verify
        try:
            back_btn = await page.query_selector('button:has-text("Back")')
            if back_btn and await back_btn.is_visible():
                await back_btn.click()
                await asyncio.sleep(2)
        except:
            pass
        
        log("   ✅ PLO conversion completed!")
        return True
        
    except Exception as e:
        log(f"   ❌ PLO conversion failed: {e}")
        return False

async def run_plo_session():
    """Main PLO session runner"""
    
    log("============================================================")
    log("🃏 PLO Poker Now Multi-Bot Arena")
    log("   Variant: Pot Limit Omaha Hi")
    log("   Bots: Clawhi(TAG), AceBot(LAG), NitKing(NIT), CallStn(STATION)")
    log("   Stack: 5000 | BB: 10")
    log("============================================================")
    
    # Create browser and game
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling"
            ]
        )
        
        try:
            # Create a fresh page for game creation
            page = await browser.new_page()
            
            # Set stealth mode properties
            await page.evaluate("""() => {
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            }""")
            
            # Create new game
            log("🎰 Creating new PLO game...")
            game_url = await create_game(page, "Clawhi")
            
            if not game_url:
                log("❌ Failed to create game")
                return
            
            log(f"✅ Game created: {game_url}")
            
            # Convert to PLO BEFORE any bots join
            log("🔧 Converting to PLO format...")
            plo_success = await convert_game_to_plo(page, game_url)
            
            if not plo_success:
                log("❌ Failed to convert to PLO - aborting")
                return
            
            log("✅ PLO conversion successful!")
            
            # Close this browser instance
            await browser.close()
            
            # Now run the standard multi_bot with the PLO game URL
            log("🚀 Launching PLO bots...")
            
            # Import and run multi_bot main function with the game URL
            import subprocess
            cmd = [sys.executable, "multi_bot.py", "--url", game_url]
            
            log(f"🤖 Running: {' '.join(cmd)}")
            result = subprocess.run(cmd)
            
            log(f"🏁 PLO session completed with code: {result.returncode}")
            
        except Exception as e:
            log(f"❌ PLO session error: {e}")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_plo_session())
#!/usr/bin/env python3
"""
Manual PLO Fix - Connect to running Chrome instance and set PLO
"""

import asyncio
import sys
from playwright.async_api import async_playwright

async def set_plo():
    """Connect to existing Chrome and set PLO"""
    async with async_playwright() as p:
        # Connect to existing Chrome instance
        try:
            # Try to connect to existing browser
            browsers = await p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            print("Connected to existing Chrome instance")
            
            contexts = browsers.contexts
            if not contexts:
                print("No contexts found")
                return
                
            pages = await contexts[0].pages()
            print(f"Found {len(pages)} pages")
            
            # Find the poker page
            poker_page = None
            for page in pages:
                url = page.url
                if "pokernow.com/games" in url and "Owner: Clawhi" in await page.content():
                    poker_page = page
                    print(f"Found owner page: {url}")
                    break
            
            if not poker_page:
                print("Could not find owner's poker page")
                return
                
            # Set PLO
            print("Setting PLO...")
            
            # Click Options
            await poker_page.click('button:has-text("Options")')
            await asyncio.sleep(2)
            
            # Click Game Configurations
            await poker_page.click('button:has-text("Game Configurations")')
            await asyncio.sleep(2)
            
            # Change to PLO
            await poker_page.select_option('select', 'Pot Limit Omaha Hi')
            print("✅ Set to Pot Limit Omaha Hi")
            
            # Go back
            await poker_page.click('button:has-text("Back")')
            await asyncio.sleep(1)
            
            print("✅ PLO configuration complete!")
            
        except Exception as e:
            print(f"Error: {e}")
            
            # Fallback: try the browser tool approach with specific targeting
            print("Trying alternative approach...")
            
            # Connect via debugging port scanning
            for port in range(9222, 9232):
                try:
                    browser = await p.chromium.connect_over_cdp(f"ws://127.0.0.1:{port}")
                    print(f"Connected on port {port}")
                    
                    for context in browser.contexts:
                        pages = await context.pages()
                        for page in pages:
                            if "pokernow.com/games" in page.url:
                                # Check if this is the owner page
                                content = await page.content()
                                if "Owner: Clawhi" in content:
                                    print(f"Found owner page: {page.url}")
                                    
                                    # Set PLO from authenticated session
                                    await page.click('button:has-text("Options")')
                                    await asyncio.sleep(2)
                                    await page.click('button:has-text("Game Configurations")')
                                    await asyncio.sleep(2)
                                    await page.select_option('select', 'Pot Limit Omaha Hi')
                                    await page.click('button:has-text("Back")')
                                    
                                    print("✅ PLO set via owner session!")
                                    return
                                    
                except Exception as port_err:
                    continue
            
            print("Could not connect to any Chrome instance")

if __name__ == "__main__":
    asyncio.run(set_plo())
"""
PLO Configuration Module
Configures PokerNow games to use Pot Limit Omaha instead of Hold'em
"""

import asyncio
import time

async def configure_plo(page, host_name):
    """Configure the game to use Pot Limit Omaha Hi instead of No Limit Hold'em"""
    print(f"[{time.strftime('%H:%M:%S')}] 🔧 Configuring game for PLO (Pot Limit Omaha Hi)...")
    
    try:
        # Wait a moment for page to fully load
        await asyncio.sleep(3)
        
        # Use JS to directly change the game variant
        result = await page.evaluate("""() => {
            // Find the poker variant dropdown
            const dropdown = document.querySelector('select, [role="combobox"]');
            if (dropdown && !dropdown.disabled) {
                // Look for PLO option
                const options = dropdown.querySelectorAll('option');
                for (const option of options) {
                    if (option.textContent.includes('Pot Limit Omaha Hi') && !option.textContent.includes('Lo')) {
                        option.selected = true;
                        dropdown.value = option.value;
                        dropdown.dispatchEvent(new Event('change', {bubbles: true}));
                        return 'success';
                    }
                }
                return 'no_plo_option';
            }
            return 'no_dropdown_or_disabled';
        }""")
        
        if result == 'success':
            print(f"[{time.strftime('%H:%M:%S')}]    ✅ Set game type to Pot Limit Omaha Hi via JS")
            await asyncio.sleep(2)
            return True
        else:
            print(f"[{time.strftime('%H:%M:%S')}]    ⚠️ JS config failed: {result}")
            
            # Fallback: Try manual click approach
            await page.click('button:has-text("Options")')
            await asyncio.sleep(2)
            
            await page.click('button:has-text("Game Configurations")')
            await asyncio.sleep(2)
            
            # Try to click the dropdown and select PLO
            dropdown = await page.query_selector('select')
            if dropdown:
                await dropdown.click()
                await asyncio.sleep(1)
                
                # Look for PLO option
                plo_option = await page.query_selector('option:has-text("Pot Limit Omaha Hi")')
                if plo_option:
                    await plo_option.click()
                    print(f"[{time.strftime('%H:%M:%S')}]    ✅ Set game type to Pot Limit Omaha Hi")
                    await asyncio.sleep(1)
                    
                    # Go back to game
                    await page.click('button:has-text("Back")')
                    await asyncio.sleep(2)
                    return True
        
        return False
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}]    ⚠️ PLO config error: {e}")
        # Try to get back to main game view
        try:
            await page.keyboard.press("Escape")
            await page.click('button:has-text("Back")')
        except:
            pass
        return False
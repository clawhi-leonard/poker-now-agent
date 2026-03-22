#!/usr/bin/env python3
"""
PLO Setter - Use JavaScript injection to set PLO in running session
"""

import asyncio
import time

async def configure_plo_smart(page, host_name):
    """Smart PLO configuration using multiple approaches"""
    print(f"[{time.strftime('%H:%M:%S')}] 🔧 SMART PLO Configuration starting...")
    
    try:
        # Wait for page to be fully ready
        await asyncio.sleep(3)
        
        # Approach 1: Direct JS manipulation of dropdown
        result = await page.evaluate("""() => {
            console.log('Starting PLO configuration...');
            
            // Wait for dropdown to be available
            let attempts = 0;
            const maxAttempts = 10;
            
            const trySetPLO = () => {
                attempts++;
                console.log('Attempt', attempts);
                
                // Look for the poker variant dropdown
                const dropdowns = document.querySelectorAll('select, [role="combobox"], combobox');
                console.log('Found dropdowns:', dropdowns.length);
                
                for (const dropdown of dropdowns) {
                    if (dropdown.disabled) {
                        console.log('Dropdown is disabled');
                        continue;
                    }
                    
                    const options = dropdown.querySelectorAll('option');
                    console.log('Options in dropdown:', options.length);
                    
                    for (const option of options) {
                        const text = option.textContent.trim();
                        console.log('Option text:', text);
                        if (text.includes('Pot Limit Omaha Hi') && !text.includes('Lo')) {
                            console.log('Found PLO option, selecting...');
                            option.selected = true;
                            dropdown.value = option.value;
                            
                            // Trigger events
                            dropdown.dispatchEvent(new Event('change', {bubbles: true}));
                            dropdown.dispatchEvent(new Event('input', {bubbles: true}));
                            dropdown.dispatchEvent(new Event('blur', {bubbles: true}));
                            
                            return 'success';
                        }
                    }
                }
                
                if (attempts < maxAttempts) {
                    setTimeout(trySetPLO, 1000);
                    return 'retrying';
                }
                
                return 'failed';
            };
            
            return trySetPLO();
        }""")
        
        if result == 'success':
            print(f"[{time.strftime('%H:%M:%S')}]    ✅ PLO set via JavaScript!")
            return True
        elif result == 'retrying':
            # Wait for retries to complete
            await asyncio.sleep(12)
            return True
        else:
            print(f"[{time.strftime('%H:%M:%S')}]    ⚠️ JS approach failed: {result}")
        
        # Approach 2: UI click sequence
        print(f"[{time.strftime('%H:%M:%S')}]    Trying UI click approach...")
        
        # Click Options (if not already open)
        try:
            options_btn = await page.query_selector('button:has-text("Options")')
            if options_btn and await options_btn.is_visible():
                await options_btn.click()
                await asyncio.sleep(2)
        except:
            pass
        
        # Click Game Configurations
        try:
            config_btn = await page.query_selector('button:has-text("Game Configurations")')
            if config_btn and await config_btn.is_visible():
                await config_btn.click()
                await asyncio.sleep(3)
                
                # Try to select PLO
                select_elem = await page.query_selector('select')
                if select_elem and not await select_elem.is_disabled():
                    await select_elem.select_option(label="Pot Limit Omaha Hi")
                    print(f"[{time.strftime('%H:%M:%S')}]    ✅ PLO set via UI!")
                    
                    # Go back
                    back_btn = await page.query_selector('button:has-text("Back")')
                    if back_btn:
                        await back_btn.click()
                        await asyncio.sleep(1)
                    
                    return True
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}]    ⚠️ UI approach error: {e}")
        
        # Approach 3: Force page reload and retry
        print(f"[{time.strftime('%H:%M:%S')}]    Trying reload approach...")
        await page.reload()
        await asyncio.sleep(3)
        
        # Try once more after reload
        try:
            await page.click('button:has-text("Options")')
            await asyncio.sleep(2)
            await page.click('button:has-text("Game Configurations")')
            await asyncio.sleep(2)
            await page.select_option('select', label="Pot Limit Omaha Hi")
            await page.click('button:has-text("Back")')
            print(f"[{time.strftime('%H:%M:%S')}]    ✅ PLO set after reload!")
            return True
        except:
            pass
        
        print(f"[{time.strftime('%H:%M:%S')}]    ❌ All PLO configuration attempts failed")
        return False
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}]    ❌ PLO configuration error: {e}")
        return False

if __name__ == "__main__":
    print("PLO Setter - Use this function in your bot code")
    print("Call: await configure_plo_smart(host_page, host_name)")
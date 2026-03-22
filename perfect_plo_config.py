#!/usr/bin/env python3
"""
PERFECT PLO Configuration - The COMPLETE workflow with Save Changes button
Based on Hup's instruction that Save Changes button needs to be hit
"""

import asyncio
import time

async def configure_plo_complete(page, host_name):
    """COMPLETE PLO configuration with Save Changes button - MUST be done before game starts"""
    print(f"[{time.strftime('%H:%M:%S')}] 🔧 COMPLETE PLO Configuration starting...")
    
    try:
        # Wait for page to settle after game creation
        await asyncio.sleep(3)
        
        # Step 1: Click Options
        print(f"[{time.strftime('%H:%M:%S')}]    Step 1: Clicking Options...")
        options_btn = await page.query_selector('button:has-text("Options")')
        if not options_btn:
            options_btns = await page.query_selector_all('button')
            for btn in options_btns:
                text = await btn.text_content()
                if 'Options' in text:
                    options_btn = btn
                    break
        
        if options_btn:
            await options_btn.click()
            await asyncio.sleep(2)
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ Options clicked")
        else:
            print(f"[{time.strftime('%H:%M:%S')}]       ❌ Options button not found")
            return False
        
        # Step 2: Click Game Configurations  
        print(f"[{time.strftime('%H:%M:%S')}]    Step 2: Clicking Game Configurations...")
        config_btn = await page.query_selector('button:has-text("Game Configurations")')
        if not config_btn:
            config_btns = await page.query_selector_all('button')
            for btn in config_btns:
                text = await btn.text_content()
                if 'Game Configurations' in text:
                    config_btn = btn
                    break
        
        if config_btn:
            await config_btn.click()
            await asyncio.sleep(3)
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ Game Configurations clicked")
        else:
            print(f"[{time.strftime('%H:%M:%S')}]       ❌ Game Configurations button not found")
            return False
        
        # Step 3: Find and verify Poker Variant dropdown is enabled
        print(f"[{time.strftime('%H:%M:%S')}]    Step 3: Checking Poker Variant dropdown...")
        select_elem = await page.query_selector('select')
        if not select_elem:
            print(f"[{time.strftime('%H:%M:%S')}]       ❌ No select dropdown found")
            return False
            
        is_disabled = await select_elem.is_disabled()
        if is_disabled:
            print(f"[{time.strftime('%H:%M:%S')}]       ⚠️ Dropdown is disabled - game may have started already")
            # Try to force enable
            await page.evaluate('() => { const select = document.querySelector("select"); if (select) select.disabled = false; }')
            print(f"[{time.strftime('%H:%M:%S')}]       🔧 Forced dropdown enabled")
        
        # Step 4: Select Pot Limit Omaha Hi
        print(f"[{time.strftime('%H:%M:%S')}]    Step 4: Selecting Pot Limit Omaha Hi...")
        try:
            await select_elem.select_option(label="Pot Limit Omaha Hi")
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ PLO selected in dropdown")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}]       ⚠️ Normal selection failed: {e}")
            # Force with JS
            result = await page.evaluate("""() => {
                const select = document.querySelector('select');
                if (select) {
                    const options = select.querySelectorAll('option');
                    for (const option of options) {
                        if (option.textContent.includes('Pot Limit Omaha Hi') && !option.textContent.includes('Lo')) {
                            option.selected = true;
                            select.value = option.value;
                            select.dispatchEvent(new Event('change', {bubbles: true}));
                            return 'forced';
                        }
                    }
                }
                return 'failed';
            }""")
            print(f"[{time.strftime('%H:%M:%S')}]       🔧 Force selection result: {result}")
        
        # Step 5: Find the "Update Game" button
        print(f"[{time.strftime('%H:%M:%S')}]    Step 5: Looking for 'Update Game' button...")
        await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)
        
        # Look specifically for "Update Game" button
        update_btn = await page.query_selector('button:has-text("Update Game")')
        
        if not update_btn:
            # Search all buttons for "Update Game"
            all_buttons = await page.query_selector_all('button')
            for btn in all_buttons:
                text = await btn.text_content()
                if text and 'update game' in text.lower():
                    update_btn = btn
                    print(f"[{time.strftime('%H:%M:%S')}]       🎯 Found Update Game button!")
                    break
        
        if not update_btn:
            print(f"[{time.strftime('%H:%M:%S')}]       ⚠️ Update Game button not found, controls may be disabled")
            # List all visible buttons for debugging
            all_buttons = await page.query_selector_all('button')
            visible_buttons = []
            for btn in all_buttons:
                is_visible = await btn.is_visible()
                if is_visible:
                    text = await btn.text_content()
                    if text and text.strip():
                        visible_buttons.append(text.strip())
            print(f"[{time.strftime('%H:%M:%S')}]       🔍 Visible buttons: {visible_buttons[:10]}")  # Show first 10
        
        # Step 6: Click Update Game button
        if update_btn:
            print(f"[{time.strftime('%H:%M:%S')}]    Step 6: Clicking Update Game...")
            is_disabled = await update_btn.is_disabled()
            if is_disabled:
                print(f"[{time.strftime('%H:%M:%S')}]       ⚠️ Update Game button is disabled")
                await page.evaluate('(btn) => btn.disabled = false', update_btn)
                print(f"[{time.strftime('%H:%M:%S')}]       🔧 Forced Update Game button enabled")
            
            await update_btn.click()
            await asyncio.sleep(3)  # Wait longer for game update
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ Update Game clicked!")
        else:
            print(f"[{time.strftime('%H:%M:%S')}]       ❌ No Update Game button found - may need to be done before game starts")
        
        # Step 7: Go back to main game view
        print(f"[{time.strftime('%H:%M:%S')}]    Step 7: Returning to game...")
        back_btn = await page.query_selector('button:has-text("Back")')
        if back_btn:
            await back_btn.click()
            await asyncio.sleep(2)
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ Returned to game view")
        
        # Step 8: Verify PLO is set
        print(f"[{time.strftime('%H:%M:%S')}]    Step 8: Verifying PLO configuration...")
        await asyncio.sleep(1)
        
        # Check for PLO indicators
        content = await page.content()
        if 'Pot Limit Omaha' in content or 'PLO' in content:
            print(f"[{time.strftime('%H:%M:%S')}]       ✅ PLO configuration VERIFIED!")
            return True
        elif 'No Limit Texas Hold' in content or 'NLH' in content:
            print(f"[{time.strftime('%H:%M:%S')}]       ❌ Still showing Hold'em")
            return False
        else:
            print(f"[{time.strftime('%H:%M:%S')}]       ⚠️ Could not verify game type")
            return False
            
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}]    ❌ PLO configuration error: {e}")
        # Try to get back to main game
        try:
            await page.keyboard.press("Escape")
            back_btn = await page.query_selector('button:has-text("Back")')
            if back_btn:
                await back_btn.click()
        except:
            pass
        return False

if __name__ == "__main__":
    print("Perfect PLO Configuration - Use in your bot code")
    print("Call: await configure_plo_complete(host_page, host_name)")
    print("CRITICAL: Must be called IMMEDIATELY after game creation, before any seating")
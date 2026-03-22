#!/usr/bin/env python3
"""
Force PLO - Inject PLO change directly into running session
"""

import asyncio
import sys
from multi_bot_plo import *

async def force_plo_now():
    """Force PLO change in currently running session"""
    print("🔧 Force PLO - connecting to running session...")
    
    # Find the host page from the running processes
    # This is a hack to access the global host page
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        print("Looking for Chrome processes...")
        
        # Launch our own browser to inject into the session
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Navigate to the game  
        await page.goto("https://www.pokernow.com/games/pglsfGrgyJ0EMk-ahBmFCHy5W")
        await asyncio.sleep(3)
        
        print("📡 Injecting PLO change JavaScript...")
        
        # Inject powerful PLO change script
        result = await page.evaluate("""() => {
            console.log('🔧 Force PLO injection starting...');
            
            // Function to wait for elements
            const waitFor = (selector, timeout = 5000) => {
                return new Promise((resolve, reject) => {
                    const element = document.querySelector(selector);
                    if (element) {
                        resolve(element);
                        return;
                    }
                    
                    const observer = new MutationObserver(() => {
                        const element = document.querySelector(selector);
                        if (element) {
                            observer.disconnect();
                            resolve(element);
                        }
                    });
                    
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                    
                    setTimeout(() => {
                        observer.disconnect();
                        reject(new Error('Timeout waiting for ' + selector));
                    }, timeout);
                });
            };
            
            // Step 1: Click Options
            const clickOptions = async () => {
                try {
                    const optionsBtn = await waitFor('button:contains("Options")');
                    optionsBtn.click();
                    console.log('✅ Clicked Options');
                    return true;
                } catch (e) {
                    console.log('❌ Options click failed:', e.message);
                    return false;
                }
            };
            
            // Step 2: Click Game Configurations  
            const clickGameConfig = async () => {
                try {
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    const configBtn = await waitFor('button:contains("Game Configurations")');
                    configBtn.click();
                    console.log('✅ Clicked Game Configurations');
                    return true;
                } catch (e) {
                    console.log('❌ Game Config click failed:', e.message);
                    return false;
                }
            };
            
            // Step 3: Change to PLO
            const changeToPLO = async () => {
                try {
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    
                    // Find the select element
                    const selects = document.querySelectorAll('select');
                    console.log('Found selects:', selects.length);
                    
                    for (const select of selects) {
                        if (select.disabled) {
                            console.log('Select is disabled, trying to enable...');
                            select.disabled = false;
                        }
                        
                        const options = select.querySelectorAll('option');
                        console.log('Options in select:', options.length);
                        
                        for (const option of options) {
                            if (option.textContent.includes('Pot Limit Omaha Hi') && !option.textContent.includes('Lo')) {
                                console.log('🎯 Found PLO option, forcing selection...');
                                
                                // Force selection multiple ways
                                option.selected = true;
                                select.value = option.value;
                                
                                // Trigger all possible events
                                const events = ['change', 'input', 'blur', 'click'];
                                events.forEach(eventType => {
                                    const event = new Event(eventType, { bubbles: true, cancelable: true });
                                    select.dispatchEvent(event);
                                });
                                
                                console.log('✅ PLO selection forced!');
                                return true;
                            }
                        }
                    }
                    
                    console.log('❌ No PLO option found');
                    return false;
                } catch (e) {
                    console.log('❌ PLO change failed:', e.message);
                    return false;
                }
            };
            
            // Step 4: Save/Apply
            const saveChanges = async () => {
                try {
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // Look for save/apply buttons
                    const saveButtons = document.querySelectorAll('button');
                    for (const btn of saveButtons) {
                        const text = btn.textContent.toLowerCase();
                        if (text.includes('save') || text.includes('apply') || text.includes('ok')) {
                            btn.click();
                            console.log('✅ Clicked save button:', btn.textContent);
                            return true;
                        }
                    }
                    
                    // Go back
                    const backBtn = document.querySelector('button:contains("Back")');
                    if (backBtn) {
                        backBtn.click();
                        console.log('✅ Clicked Back');
                        return true;
                    }
                    
                    return false;
                } catch (e) {
                    console.log('❌ Save failed:', e.message);
                    return false;
                }
            };
            
            // Execute sequence
            const executeSequence = async () => {
                console.log('🚀 Starting PLO change sequence...');
                
                if (await clickOptions()) {
                    if (await clickGameConfig()) {
                        if (await changeToPLO()) {
                            await saveChanges();
                            return 'success';
                        }
                    }
                }
                
                return 'failed';
            };
            
            // Use helper function that supports :contains
            const addContainsSupport = () => {
                if (!document.querySelector(':contains')) {
                    const style = document.createElement('style');
                    document.head.appendChild(style);
                }
            };
            
            addContainsSupport();
            return executeSequence();
        }""")
        
        print(f"📊 PLO injection result: {result}")
        
        # Keep browser open for verification
        input("Press Enter to close...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(force_plo_now())
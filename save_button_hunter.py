#!/usr/bin/env python3
"""
Save Button Hunter - Find the exact save mechanism for PokerNow PLO config
"""

import asyncio

async def hunt_save_mechanism(page):
    """Hunt for the exact save mechanism PokerNow uses"""
    print("🔍 HUNTING for save mechanism...")
    
    # Navigate to config page
    await page.click('button:has-text("Options")')
    await asyncio.sleep(2)
    await page.click('button:has-text("Game Configurations")')
    await asyncio.sleep(3)
    
    # Comprehensive save hunting
    result = await page.evaluate("""() => {
        console.log('🕵️ COMPREHENSIVE SAVE HUNTING...');
        
        const findings = {
            forms: [],
            buttons: [],
            inputs: [],
            eventListeners: [],
            apiCalls: [],
            mutations: []
        };
        
        // 1. Find all forms
        const forms = document.querySelectorAll('form');
        forms.forEach((form, i) => {
            findings.forms.push({
                index: i,
                action: form.action,
                method: form.method,
                elements: form.elements.length,
                hasSubmit: !!form.querySelector('[type="submit"]')
            });
        });
        
        // 2. Find all buttons with save-like functionality
        const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
        buttons.forEach((btn, i) => {
            const text = (btn.textContent || btn.value || '').toLowerCase();
            const id = btn.id;
            const classes = btn.className;
            const onclick = btn.onclick ? btn.onclick.toString() : null;
            
            if (text.includes('save') || text.includes('apply') || text.includes('submit') || 
                text.includes('update') || text.includes('confirm') || text.includes('ok') ||
                id.includes('save') || id.includes('submit') || id.includes('apply') ||
                classes.includes('save') || classes.includes('submit') || classes.includes('apply')) {
                findings.buttons.push({
                    index: i,
                    text: btn.textContent || btn.value,
                    id: id,
                    classes: classes,
                    disabled: btn.disabled,
                    visible: btn.offsetParent !== null,
                    onclick: onclick ? onclick.substring(0, 100) : null
                });
            }
        });
        
        // 3. Check for hidden inputs or auto-submit mechanisms
        const hiddenInputs = document.querySelectorAll('input[type="hidden"]');
        hiddenInputs.forEach((input, i) => {
            findings.inputs.push({
                name: input.name,
                value: input.value,
                id: input.id
            });
        });
        
        // 4. Monitor for AJAX/fetch calls when dropdown changes
        const originalFetch = window.fetch;
        const originalXHR = XMLHttpRequest.prototype.send;
        
        let interceptedCalls = [];
        
        // Intercept fetch
        window.fetch = function(...args) {
            interceptedCalls.push({type: 'fetch', url: args[0], options: args[1]});
            return originalFetch.apply(this, args);
        };
        
        // Intercept XMLHttpRequest
        XMLHttpRequest.prototype.send = function(data) {
            interceptedCalls.push({type: 'xhr', url: this._url || 'unknown', data: data});
            return originalXHR.call(this, data);
        };
        
        // 5. Test dropdown change and monitor API calls
        const select = document.querySelector('select');
        if (select) {
            select.disabled = false;
            const ploOption = Array.from(select.querySelectorAll('option')).find(o => 
                o.textContent.includes('Pot Limit Omaha Hi') && !o.textContent.includes('Lo')
            );
            
            if (ploOption) {
                console.log('Setting PLO and monitoring API calls...');
                
                ploOption.selected = true;
                select.value = ploOption.value;
                select.dispatchEvent(new Event('change', {bubbles: true}));
                
                // Wait for any async calls
                await new Promise(resolve => setTimeout(resolve, 2000));
                
                findings.apiCalls = interceptedCalls;
            }
        }
        
        // 6. Look for mutation observers or auto-save indicators
        const scripts = Array.from(document.querySelectorAll('script'));
        scripts.forEach((script, i) => {
            const content = script.textContent;
            if (content && (content.includes('save') || content.includes('submit') || content.includes('onchange'))) {
                findings.mutations.push({
                    index: i,
                    content: content.substring(0, 200)
                });
            }
        });
        
        return findings;
    }""")
    
    print(f"🔍 FINDINGS:")
    print(f"   Forms: {len(result.get('forms', []))}")
    print(f"   Save Buttons: {len(result.get('buttons', []))}")
    print(f"   Hidden Inputs: {len(result.get('inputs', []))}")
    print(f"   API Calls: {len(result.get('apiCalls', []))}")
    print(f"   Scripts: {len(result.get('mutations', []))}")
    
    for button in result.get('buttons', []):
        print(f"   📍 Save Button: '{button['text']}' (visible: {button['visible']}, disabled: {button['disabled']})")
    
    for call in result.get('apiCalls', []):
        print(f"   🌐 API Call: {call['type']} to {call['url']}")
    
    return result

if __name__ == "__main__":
    print("Save Button Hunter - Use this to find PokerNow's save mechanism")
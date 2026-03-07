"""
Execute poker actions on Poker Now.

v5 - Fixed the raise panel opener (2026-03-06):
  ROOT CAUSE: "BET 20" button matched before "BET" button.
    "BET 20" = preset min-bet (acts immediately, no slider)
    "BET" / "RAISE" = opens custom slider panel
  FIX: For raise, prefer buttons with EXACT text "Bet"/"Raise" (no numbers).
       Fallback to keyboard shortcut "r" which always opens the panel.
"""
import asyncio
import os
from typing import Optional
from playwright.async_api import Page

_raise_diag_logged = False


async def click_action_button(page: Page, text: str) -> bool:
    """Click a visible action button containing the given text."""
    buttons = await page.query_selector_all('.game-decisions-ctn button, button.action-button')
    for btn in buttons:
        try:
            if not await btn.is_visible():
                continue
            content = (await btn.text_content() or '').strip()
            if text.lower() in content.lower():
                await btn.click()
                return True
        except:
            continue
    buttons = await page.query_selector_all('button')
    for btn in buttons:
        try:
            if not await btn.is_visible():
                continue
            content = (await btn.text_content() or '').strip()
            if content.lower() == text.lower():
                await btn.click()
                return True
        except:
            continue
    return False


async def _click_raise_opener(page: Page) -> bool:
    """
    Click the button that OPENS the raise/bet slider panel.
    Must NOT click "BET 20" / "RAISE TO 40" (those are preset actions).
    Must click the bare "BET" or "RAISE" button.
    """
    buttons = await page.query_selector_all('.game-decisions-ctn button, button.action-button, button')
    
    # Pass 1: Look for buttons with EXACT text "Bet" or "Raise" (no numbers)
    for btn in buttons:
        try:
            if not await btn.is_visible():
                continue
            raw = (await btn.text_content() or '').strip()
            # Strip keyboard shortcut letters (single char at start/end)
            text = raw.strip()
            # The button might contain a hotkey like "R" prefix — clean it
            # pokernow buttons: "Bet", "Raise", "BET", "RAISE"
            # NOT: "Bet 20", "Raise to 40", "BET 20"
            text_lower = text.lower()
            if text_lower in ('bet', 'raise', 'r bet', 'r raise'):
                await btn.click()
                return True
            # Check if text is just "Bet" or "Raise" possibly with whitespace
            import re
            if re.match(r'^(bet|raise)$', text_lower.strip()):
                await btn.click()
                return True
        except:
            continue
    
    # Pass 2: Look for "Raise" or "Bet" that don't have a number after them
    for btn in buttons:
        try:
            if not await btn.is_visible():
                continue
            raw = (await btn.text_content() or '').strip()
            text_lower = raw.lower().strip()
            import re
            # Match "raise" or "bet" NOT followed by a number
            if re.match(r'^(raise|bet)\s*$', text_lower):
                await btn.click()
                return True
        except:
            continue
    
    return False


async def _wait_for_raise_panel(page: Page, timeout_ms=2500) -> bool:
    """Wait for the raise/bet input panel (slider or number input) to appear."""
    interval = 100
    elapsed = 0
    while elapsed < timeout_ms:
        found = await page.evaluate("""() => {
            // Check for slider
            const slider = document.querySelector('input[type="range"]');
            if (slider) {
                const rect = slider.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
            // Check for number/text input in decision area
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                if (inp.type === 'range' || inp.type === 'checkbox' || inp.type === 'radio' ||
                    inp.type === 'hidden' || inp.type === 'submit') continue;
                const rect = inp.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    const cl = (inp.className || '').toLowerCase();
                    const ph = (inp.placeholder || '').toLowerCase();
                    if (cl.includes('chat') || ph.includes('name') || ph.includes('nick') ||
                        ph.includes('message') || ph.includes('search')) continue;
                    // Likely a bet input
                    return true;
                }
            }
            return false;
        }""")
        if found:
            return True
        await asyncio.sleep(interval / 1000)
        elapsed += interval
    return False


async def _find_bet_input(page: Page):
    """Find the bet amount input element with comprehensive fallback."""
    return await page.evaluate("""() => {
        const result = { found: false, min: 2, max: 100, current: 0, selector: null, debug: '' };
        
        // Try specific selectors first, then broad
        const selectors = [
            '.game-decisions-ctn input[type="number"]',
            '.game-decisions-ctn input.value-input',
            '.game-decisions-ctn input.value',
            '.bet-input-handler input',
            '.raise-controller input',
            'input.value',
            'input.value-input',
            'input[type="number"]',
        ];
        
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    result.found = true;
                    result.current = parseInt(el.value) || 0;
                    result.selector = sel;
                    break;
                }
            }
        }
        
        // Broadest fallback
        if (!result.found) {
            const allInputs = document.querySelectorAll('input');
            for (const inp of allInputs) {
                if (inp.type === 'range' || inp.type === 'checkbox' || inp.type === 'radio' ||
                    inp.type === 'hidden' || inp.type === 'submit') continue;
                const rect = inp.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) continue;
                const ph = (inp.placeholder || '').toLowerCase();
                const cl = (inp.className || '').toLowerCase();
                if (ph.includes('chat') || ph.includes('name') || ph.includes('nick') ||
                    ph.includes('search') || ph.includes('message') ||
                    cl.includes('chat') || cl.includes('search')) continue;
                const val = parseInt(inp.value);
                if (val > 0 || inp.type === 'number') {
                    result.found = true;
                    result.current = val || 0;
                    if (inp.className) {
                        result.selector = 'input.' + inp.className.split(' ')[0];
                    } else {
                        result.selector = 'input[type="' + (inp.type || 'text') + '"]';
                    }
                    break;
                }
            }
        }
        
        // Get slider range
        const slider = document.querySelector('input[type="range"]');
        if (slider) {
            const rect = slider.getBoundingClientRect();
            if (rect.width > 0) {
                result.min = parseInt(slider.min) || 0;
                result.max = parseInt(slider.max) || 100;
                if (result.min === 0 && result.current > 0) {
                    result.min = result.current;
                }
            }
        }
        
        // Scan for range text if slider not found or range is small
        if (result.max <= 100) {
            const els = document.querySelectorAll('span, div, p, label');
            for (const el of els) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0) continue;
                const t = el.textContent.trim();
                const m = t.match(/(\\d+)\\s*[-–]\\s*(\\d+)/);
                if (m && parseInt(m[2]) > 100) {
                    result.min = Math.max(result.min, parseInt(m[1]));
                    result.max = parseInt(m[2]);
                    break;
                }
            }
        }
        
        // Debug dump if not found
        if (!result.found) {
            const dbg = [];
            document.querySelectorAll('input').forEach(inp => {
                const rect = inp.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    dbg.push('type=' + inp.type + ' class=' + inp.className +
                             ' val=' + inp.value + ' ph=' + inp.placeholder +
                             ' parent=' + (inp.parentElement?.className || ''));
                }
            });
            result.debug = dbg.join(' | ');
        }
        
        return result;
    }""")


async def _set_bet_amount(page: Page, amount: int, input_selector: str) -> str:
    """Set the bet amount using React-compatible JS setter."""
    actual = await page.evaluate("""(args) => {
        const [amount, selector] = args;
        const nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        
        const textInput = document.querySelector(selector);
        if (textInput) {
            nativeSetter.call(textInput, String(amount));
            textInput.dispatchEvent(new Event('input', { bubbles: true }));
            textInput.dispatchEvent(new Event('change', { bubbles: true }));
            // Try React event handler
            for (const key of Object.keys(textInput)) {
                if (key.startsWith('__reactEventHandlers$') || key.startsWith('__reactProps$')) {
                    const props = textInput[key];
                    if (props && props.onChange) {
                        props.onChange({ target: textInput });
                        break;
                    }
                }
            }
        }
        
        const slider = document.querySelector('input[type="range"]');
        if (slider) {
            nativeSetter.call(slider, String(amount));
            slider.dispatchEvent(new Event('input', { bubbles: true }));
            slider.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        if (textInput) return textInput.value;
        if (slider) return slider.value;
        return '?';
    }""", [amount, input_selector])
    return str(actual)


async def execute_action(page: Page, action: str, amount: Optional[int] = None) -> str:
    global _raise_diag_logged
    action = action.lower().strip()

    if action == "check":
        if not await click_action_button(page, "Check"):
            await page.keyboard.press("k")
        return "Checked"

    elif action == "fold":
        if not await click_action_button(page, "Fold"):
            await page.keyboard.press("f")
        return "Folded"

    elif action == "call":
        if not await click_action_button(page, "Call"):
            await page.keyboard.press("c")
        return "Called"

    elif action in ("bet", "raise"):
        # CRITICAL: Open the raise SLIDER panel, not the preset bet button
        panel_opened = await _click_raise_opener(page)
        
        if not panel_opened:
            # Keyboard shortcut "r" ALWAYS opens the raise panel in pokernow
            await page.keyboard.press("r")
        
        # Wait for the slider panel to render
        panel_ready = await _wait_for_raise_panel(page, timeout_ms=2500)
        if not panel_ready:
            # The keyboard shortcut might not have worked. Try clicking more aggressively
            await page.keyboard.press("r")
            await asyncio.sleep(1.0)
            panel_ready = await _wait_for_raise_panel(page, timeout_ms=1500)

        # Find the bet input
        bet_info = await _find_bet_input(page)
        
        if not bet_info.get("found"):
            await asyncio.sleep(0.5)
            bet_info = await _find_bet_input(page)
        
        # Diagnostic on failure
        if not bet_info.get("found") and not _raise_diag_logged:
            _raise_diag_logged = True
            diag = bet_info.get("debug", "")
            try:
                log_path = os.path.expanduser("~/Projects/poker-now-agent/logs/raise_diag.txt")
                with open(log_path, "w") as f:
                    f.write(f"Raise panel not found!\nDebug: {diag}\n")
                await page.screenshot(path=os.path.expanduser(
                    "~/Projects/poker-now-agent/logs/raise_diag.png"))
            except:
                pass
        
        min_raise = bet_info.get("min", 2)
        max_raise = bet_info.get("max", 100)
        input_selector = bet_info.get("selector") or "input.value"
        
        final_amount = amount if amount else min_raise
        final_amount = max(final_amount, min_raise)
        final_amount = min(final_amount, max_raise)

        # Try setting the value up to 3 times
        actual = "?"
        for attempt in range(3):
            if bet_info.get("found"):
                actual = await _set_bet_amount(page, int(final_amount), input_selector)
            
            try:
                actual_int = int(actual)
                if abs(actual_int - final_amount) <= 1:
                    break
            except (ValueError, TypeError):
                pass
            
            if attempt < 2:
                await asyncio.sleep(0.3)
                try:
                    for sel in [input_selector, 'input.value', 'input[type="number"]',
                                'input.value-input', 'input[type="range"]']:
                        inp = await page.query_selector(sel)
                        if inp and await inp.is_visible():
                            await inp.click(click_count=3)
                            await asyncio.sleep(0.1)
                            await page.keyboard.press("Meta+a")
                            await page.keyboard.type(str(int(final_amount)))
                            await asyncio.sleep(0.2)
                            actual = await page.evaluate("""(sel) => {
                                const inp = document.querySelector(sel);
                                return inp ? inp.value : '?';
                            }""", sel)
                            try:
                                if abs(int(actual) - final_amount) <= 1:
                                    break
                            except:
                                pass
                except Exception:
                    pass

        # Submit the raise
        submitted = False
        for sel in ['input[type="submit"]', '.game-decisions-ctn input[type="submit"]',
                    '.game-decisions-ctn button.green', 'button.green']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    submitted = True
                    break
            except:
                continue
        
        if not submitted:
            # Try buttons with raise/bet/confirm text
            buttons = await page.query_selector_all('button')
            for btn in buttons:
                try:
                    if not await btn.is_visible():
                        continue
                    text = (await btn.text_content() or '').strip().lower()
                    if any(x in text for x in ['fold', 'check', 'call', 'extra',
                                                'got it', 'options', 'leave', 'away']):
                        continue
                    if any(x in text for x in ['raise', 'bet', 'confirm', 'submit']):
                        await btn.click()
                        submitted = True
                        break
                except:
                    continue

        if not submitted:
            await page.keyboard.press("Enter")

        return f"Raised to {actual} (range {min_raise}-{max_raise})"

    else:
        return f"Unknown action: {action}"


async def send_chat(page: Page, message: str) -> str:
    await page.keyboard.press("m")
    await asyncio.sleep(0.2)
    chat_input = await page.query_selector('.chat-input input, .chat-input textarea, input.chat-text-input')
    if chat_input:
        await chat_input.fill(message)
        await page.keyboard.press("Enter")
        return f"Sent: {message}"
    return "Chat input not found"

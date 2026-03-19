"""
Execute poker actions on Poker Now.

v14 - Fix submit button detachment (2026-03-19):
  ROOT CAUSE: React SPA re-renders the submit button during game state changes,
    causing Playwright's cached element handle to become stale ("Element is not attached to the DOM").
  FIX: Use page.keyboard.press("Enter") as primary submit method.
    Enter key submits the form via the browser's native form handling, bypassing the need
    for a stable element reference. Re-query fallback only if Enter fails.
  RESULT: Eliminates ~10 "Element detached" errors per session.

v13 - Complete slider rewrite (2026-03-18):
  ROOT CAUSE: React SPA ignores nativeSetter value changes on the range slider.
    The displayed bet amount stays at slider max regardless of JS manipulation.
  
  NEW APPROACH (3-tier):
    1. Mouse drag: Get slider bounding box, calculate pixel position for target value,
       drag from current thumb position to target position.
    2. Arrow key: Focus slider, press Left arrow to decrement from max to target.
    3. fill() on text input: Triple-click + type the amount directly into the text field.
    4. VALIDATION: After each attempt, read back the displayed value. If wrong, try next tier.
    5. CALL FALLBACK: If all tiers fail and actual > 2x target, downgrade to call.
  
  Also: improved panel detection, better submit button finding.

v5 - Fixed the raise panel opener:
  ROOT CAUSE: "BET 20" button matched before "BET" button.
    "BET 20" = preset min-bet (acts immediately, no slider)
    "BET" / "RAISE" = opens custom slider panel
"""
import asyncio
import os
import re
from typing import Optional, Tuple
from playwright.async_api import Page

_raise_diag_logged = False
_slider_stats = {"attempts": 0, "successes": 0, "tier1_ok": 0, "tier2_ok": 0, "tier3_ok": 0, "fallback_calls": 0}


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
            text_lower = raw.lower().strip()
            if text_lower in ('bet', 'raise', 'r bet', 'r raise'):
                await btn.click()
                return True
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
            const slider = document.querySelector('input[type="range"]');
            if (slider) {
                const rect = slider.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
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


async def _get_slider_info(page: Page) -> dict:
    """Get comprehensive slider and bet input state from the DOM."""
    return await page.evaluate("""() => {
        const result = {
            slider_found: false,
            text_input_found: false,
            slider_min: 0,
            slider_max: 100,
            slider_value: 0,
            text_value: 0,
            slider_selector: null,
            text_selector: null,
            slider_rect: null,
            displayed_amount: 0,
            debug: ''
        };
        
        // Find the range slider
        const slider = document.querySelector('input[type="range"]');
        if (slider) {
            const rect = slider.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                result.slider_found = true;
                result.slider_min = parseInt(slider.min) || 0;
                result.slider_max = parseInt(slider.max) || 100;
                result.slider_value = parseInt(slider.value) || 0;
                result.slider_rect = {
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                };
            }
        }
        
        // Find the text input for bet amount
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
            if (el && el.type !== 'range') {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    result.text_input_found = true;
                    result.text_value = parseInt(el.value) || 0;
                    result.text_selector = sel;
                    break;
                }
            }
        }
        
        // Broadest text input fallback
        if (!result.text_input_found) {
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
                    result.text_input_found = true;
                    result.text_value = val || 0;
                    if (inp.className) {
                        result.text_selector = 'input.' + inp.className.split(' ')[0];
                    } else {
                        result.text_selector = 'input[type="' + (inp.type || 'text') + '"]';
                    }
                    break;
                }
            }
        }
        
        // Get the displayed bet amount (what the UI actually shows, not input.value)
        // Look for span/div near the slider that shows the current amount
        const candidates = document.querySelectorAll('.game-decisions-ctn span, .game-decisions-ctn div, .raise-controller span');
        for (const el of candidates) {
            const text = (el.textContent || '').trim();
            const m = text.match(/^\\$?([\\d,]+)$/);
            if (m) {
                const val = parseInt(m[1].replace(/,/g, ''));
                if (val >= (result.slider_min || 1) && val <= (result.slider_max || 999999)) {
                    result.displayed_amount = val;
                    break;
                }
            }
        }
        
        // If no displayed amount found, use text input value
        if (!result.displayed_amount && result.text_input_found) {
            result.displayed_amount = result.text_value;
        }
        
        return result;
    }""")


async def _read_current_bet_value(page: Page) -> int:
    """Read the current bet amount that would actually be submitted."""
    info = await _get_slider_info(page)
    # Priority: displayed amount > text input > slider value
    if info.get("displayed_amount", 0) > 0:
        return info["displayed_amount"]
    if info.get("text_value", 0) > 0:
        return info["text_value"]
    return info.get("slider_value", 0)


async def _tier1_mouse_drag(page: Page, target: int, info: dict) -> bool:
    """Tier 1: Mouse drag on the slider track to set exact value."""
    if not info.get("slider_found") or not info.get("slider_rect"):
        return False
    
    rect = info["slider_rect"]
    smin = info["slider_min"]
    smax = info["slider_max"]
    
    if smax <= smin:
        return False
    
    # Calculate target pixel X position on the slider track
    ratio = (target - smin) / (smax - smin)
    ratio = max(0.0, min(1.0, ratio))
    
    # Slider track: left edge = min, right edge = max
    # Add small padding (slider thumb might be inset)
    padding = 8  # pixels of padding on each side of slider track
    track_width = rect["width"] - (padding * 2)
    target_x = rect["x"] + padding + (track_width * ratio)
    target_y = rect["y"] + rect["height"] / 2
    
    # Current thumb position (based on current slider value)
    current_ratio = (info["slider_value"] - smin) / (smax - smin) if smax > smin else 1.0
    current_x = rect["x"] + padding + (track_width * current_ratio)
    current_y = target_y
    
    try:
        # Click directly at the target position on the slider track
        await page.mouse.click(target_x, target_y)
        await asyncio.sleep(0.3)
        
        # Verify
        actual = await _read_current_bet_value(page)
        if actual > 0 and abs(actual - target) <= max(target * 0.1, 5):
            return True
        
        # If click didn't work, try drag from current to target
        await page.mouse.move(current_x, current_y)
        await page.mouse.down()
        await asyncio.sleep(0.05)
        # Drag in small steps for smoother tracking
        steps = max(5, int(abs(target_x - current_x) / 5))
        for i in range(1, steps + 1):
            interp_x = current_x + (target_x - current_x) * (i / steps)
            await page.mouse.move(interp_x, target_y)
            await asyncio.sleep(0.01)
        await page.mouse.up()
        await asyncio.sleep(0.3)
        
        actual = await _read_current_bet_value(page)
        if actual > 0 and abs(actual - target) <= max(target * 0.15, 10):
            return True
    except Exception:
        pass
    
    return False


async def _tier2_arrow_keys(page: Page, target: int, info: dict) -> bool:
    """Tier 2: Focus slider and use arrow keys to adjust from current value to target."""
    if not info.get("slider_found"):
        return False
    
    try:
        slider = await page.query_selector('input[type="range"]')
        if not slider:
            return False
        
        await slider.focus()
        await asyncio.sleep(0.1)
        
        current = info.get("slider_value", info.get("slider_max", 0))
        smin = info.get("slider_min", 0)
        smax = info.get("slider_max", 0)
        
        # Determine step size. Default is 1, but pokernow might use bigger steps.
        # We'll try to detect it from the DOM
        step = await page.evaluate("""() => {
            const s = document.querySelector('input[type="range"]');
            return s ? (parseInt(s.step) || 1) : 1;
        }""")
        
        diff = current - target
        if diff <= 0:
            # Need to go UP (unlikely since we usually want less than max)
            presses = min(abs(diff) // step, 500)  # Cap to avoid infinite loop
            for _ in range(presses):
                await page.keyboard.press("ArrowRight")
                await asyncio.sleep(0.01)
        else:
            # Need to go DOWN from current to target
            presses = min(diff // step, 500)
            for _ in range(presses):
                await page.keyboard.press("ArrowLeft")
                await asyncio.sleep(0.01)
        
        await asyncio.sleep(0.3)
        
        actual = await _read_current_bet_value(page)
        if actual > 0 and abs(actual - target) <= max(target * 0.15, 10):
            return True
        
        # If we overshot, try Home key (min) + ArrowRight to build up
        if abs(actual - target) > target * 0.3 and target <= smin + (smax - smin) * 0.3:
            await page.keyboard.press("Home")  # Go to min
            await asyncio.sleep(0.1)
            up_presses = min((target - smin) // step, 500)
            for _ in range(up_presses):
                await page.keyboard.press("ArrowRight")
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.2)
            actual = await _read_current_bet_value(page)
            if actual > 0 and abs(actual - target) <= max(target * 0.15, 10):
                return True
    except Exception:
        pass
    
    return False


async def _tier3_text_input(page: Page, target: int, info: dict) -> bool:
    """Tier 3: Directly type into the text input field."""
    selectors_to_try = []
    if info.get("text_selector"):
        selectors_to_try.append(info["text_selector"])
    selectors_to_try.extend([
        '.game-decisions-ctn input[type="number"]',
        '.game-decisions-ctn input.value-input',
        '.game-decisions-ctn input.value',
        'input.value',
        'input.value-input',
        'input[type="number"]',
    ])
    
    for sel in selectors_to_try:
        try:
            inp = await page.query_selector(sel)
            if not inp or not await inp.is_visible():
                continue
            inp_type = await inp.get_attribute("type")
            if inp_type == "range":
                continue
            
            # Method A: Triple-click to select all, then type
            await inp.click(click_count=3)
            await asyncio.sleep(0.1)
            await page.keyboard.press("Meta+a")
            await asyncio.sleep(0.05)
            await page.keyboard.type(str(int(target)), delay=30)
            await asyncio.sleep(0.3)
            
            actual = await _read_current_bet_value(page)
            if actual > 0 and abs(actual - target) <= max(target * 0.1, 5):
                return True
            
            # Method B: Clear via JS then type
            await page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (!el) return;
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, '');
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                // Try React onChange
                for (const key of Object.keys(el)) {
                    if (key.startsWith('__reactEventHandlers$') || key.startsWith('__reactProps$')) {
                        const props = el[key];
                        if (props && props.onChange) {
                            props.onChange({ target: { value: '' } });
                            break;
                        }
                    }
                }
            }""", sel)
            await asyncio.sleep(0.1)
            await inp.type(str(int(target)), delay=30)
            await asyncio.sleep(0.3)
            
            # Also set via React nativeSetter as backup
            await page.evaluate("""(args) => {
                const [sel, val] = args;
                const el = document.querySelector(sel);
                if (!el) return;
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, String(val));
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                for (const key of Object.keys(el)) {
                    if (key.startsWith('__reactEventHandlers$') || key.startsWith('__reactProps$')) {
                        const props = el[key];
                        if (props && props.onChange) {
                            props.onChange({ target: { value: String(val) } });
                            break;
                        }
                    }
                }
                // Also set the slider if it exists
                const slider = document.querySelector('input[type="range"]');
                if (slider) {
                    nativeSetter.call(slider, String(val));
                    slider.dispatchEvent(new Event('input', { bubbles: true }));
                    slider.dispatchEvent(new Event('change', { bubbles: true }));
                    for (const key of Object.keys(slider)) {
                        if (key.startsWith('__reactEventHandlers$') || key.startsWith('__reactProps$')) {
                            const props = slider[key];
                            if (props && props.onChange) {
                                props.onChange({ target: { value: String(val) } });
                                break;
                            }
                        }
                    }
                }
            }""", [sel, target])
            await asyncio.sleep(0.3)
            
            actual = await _read_current_bet_value(page)
            if actual > 0 and abs(actual - target) <= max(target * 0.1, 5):
                return True
        except Exception:
            continue
    
    return False


async def _set_bet_amount_v13(page: Page, target: int) -> Tuple[int, str]:
    """
    v13: Set bet amount using 3-tier approach with validation.
    Returns (actual_amount, tier_used).
    """
    _slider_stats["attempts"] += 1
    
    info = await _get_slider_info(page)
    smin = info.get("slider_min", 0)
    smax = info.get("slider_max", 0)
    
    # Clamp target to valid range
    target = max(target, smin)
    target = min(target, smax)
    
    # If target == min, just click the min preset button if available
    if target <= smin:
        # Try clicking a preset button like "BET 20" that matches min
        try:
            buttons = await page.query_selector_all('.game-decisions-ctn button')
            for btn in buttons:
                text = (await btn.text_content() or '').strip().lower()
                m = re.search(r'(\d+)', text)
                if m and int(m.group(1)) == smin and ('bet' in text or 'raise' in text):
                    await btn.click()
                    return (smin, "preset_min")
        except:
            pass
    
    # If target == max (all-in), just leave the slider at max
    if target >= smax:
        return (smax, "max")
    
    # Tier 1: Mouse drag/click on slider
    ok = await _tier1_mouse_drag(page, target, info)
    if ok:
        actual = await _read_current_bet_value(page)
        _slider_stats["tier1_ok"] += 1
        _slider_stats["successes"] += 1
        return (actual, "tier1_mouse")
    
    # Refresh info after tier 1 attempt
    info = await _get_slider_info(page)
    
    # Tier 2: Arrow keys
    ok = await _tier2_arrow_keys(page, target, info)
    if ok:
        actual = await _read_current_bet_value(page)
        _slider_stats["tier2_ok"] += 1
        _slider_stats["successes"] += 1
        return (actual, "tier2_arrows")
    
    # Refresh info
    info = await _get_slider_info(page)
    
    # Tier 3: Text input direct type
    ok = await _tier3_text_input(page, target, info)
    if ok:
        actual = await _read_current_bet_value(page)
        _slider_stats["tier3_ok"] += 1
        _slider_stats["successes"] += 1
        return (actual, "tier3_text")
    
    # All tiers failed — read what we've got
    actual = await _read_current_bet_value(page)
    return (actual, "FAILED")


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
            await page.keyboard.press("r")
            await asyncio.sleep(1.0)
            panel_ready = await _wait_for_raise_panel(page, timeout_ms=1500)

        if not panel_ready:
            # Absolute last resort: just call instead of raising
            if await click_action_button(page, "Call"):
                return "Called (panel failed)"
            await page.keyboard.press("c")
            return "Called (panel failed, key)"

        # Get slider info for range
        info = await _get_slider_info(page)
        min_raise = info.get("slider_min", 2)
        max_raise = info.get("slider_max", 100)

        final_amount = amount if amount else min_raise
        final_amount = max(final_amount, min_raise)
        final_amount = min(final_amount, max_raise)

        # v13: Use the 3-tier slider approach
        actual, tier = await _set_bet_amount_v13(page, int(final_amount))
        
        # v13 CRITICAL: If slider failed and actual is way too high, CANCEL and CALL instead
        # This prevents accidental all-ins from slider going to max
        if tier == "FAILED" and actual > 0:
            # If actual is more than 2x our target (or more than 50% of max), cancel the raise
            if actual > final_amount * 2 and actual > max_raise * 0.7:
                # Close the raise panel by pressing Escape, then call
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                _slider_stats["fallback_calls"] += 1
                if await click_action_button(page, "Call"):
                    return f"Called (slider failed: wanted {final_amount}, got {actual}, tier={tier})"
                elif await click_action_button(page, "Check"):
                    return f"Checked (slider failed: wanted {final_amount}, got {actual}, tier={tier})"
                await page.keyboard.press("c")
                return f"Called/key (slider failed: wanted {final_amount}, got {actual}, tier={tier})"

        # Submit the raise — v14: Use Enter key as PRIMARY method to avoid
        # "Element is not attached to the DOM" errors from React SPA re-renders.
        # The submit button gets recreated by React on game state changes, making
        # Playwright's element handle stale. Enter key bypasses this entirely.
        submitted = False
        try:
            await page.keyboard.press("Enter")
            submitted = True
        except:
            pass
        
        if not submitted:
            # Fallback: re-query and click submit button (fresh handle)
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

        return f"Raised to {actual} (target {final_amount}, range {min_raise}-{max_raise}, {tier})"

    else:
        return f"Unknown action: {action}"


def get_slider_stats() -> dict:
    """Return slider accuracy stats for logging."""
    return dict(_slider_stats)


async def send_chat(page: Page, message: str) -> str:
    await page.keyboard.press("m")
    await asyncio.sleep(0.2)
    chat_input = await page.query_selector('.chat-input input, .chat-input textarea, input.chat-text-input')
    if chat_input:
        await chat_input.fill(message)
        await page.keyboard.press("Enter")
        return f"Sent: {message}"
    return "Chat input not found"

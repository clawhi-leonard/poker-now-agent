"""
Execute poker actions on Poker Now.
Primary: click buttons. Raise: use slider input for min/max, set value via JS.
"""
import asyncio
from typing import Optional
from playwright.async_api import Page


async def click_action_button(page: Page, text: str) -> bool:
    """Click a visible action button containing the given text."""
    buttons = await page.query_selector_all('button.action-button')
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
    # Fallback: any visible button
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


async def execute_action(page: Page, action: str, amount: Optional[int] = None) -> str:
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
        # Open raise panel
        if not await click_action_button(page, "Raise"):
            if not await click_action_button(page, "Bet"):
                await page.keyboard.press("r")
        await asyncio.sleep(0.5)

        # Read min/max from the slider (most reliable source)
        raise_info = await page.evaluate("""() => {
            const slider = document.querySelector('input[type="range"]');
            const textInput = document.querySelector('input.value, input[type="text"]');
            const result = { min: 2, max: 100, prefilled: 2 };
            
            if (slider) {
                result.min = parseInt(slider.min) || 0;
                result.max = parseInt(slider.max) || 100;
                // Slider min=0 means the actual min raise is the prefilled text value
            }
            if (textInput) {
                const val = parseInt(textInput.value);
                if (val > 0) result.prefilled = val;
            }
            // Real min raise = prefilled value (what Poker Now sets as default)
            if (result.prefilled > result.min) result.min = result.prefilled;
            return result;
        }""")

        min_raise = raise_info.get("min", 2)
        max_raise = raise_info.get("max", 100)
        
        # If slider min is 0, real min is the prefilled value
        if min_raise == 0:
            min_raise = raise_info.get("prefilled", 2)

        # Determine final amount
        final_amount = amount if amount else min_raise
        final_amount = max(final_amount, min_raise)
        final_amount = min(final_amount, max_raise)

        # Set the value via JS (bypasses React input issues)
        await page.evaluate("""(val) => {
            const textInput = document.querySelector('input.value, input[type="text"]');
            if (textInput) {
                // React-compatible: set via native setter + dispatch events
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(textInput, String(val));
                textInput.dispatchEvent(new Event('input', { bubbles: true }));
                textInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
            // Also set the slider
            const slider = document.querySelector('input[type="range"]');
            if (slider) {
                const sliderSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                sliderSetter.call(slider, String(val));
                slider.dispatchEvent(new Event('input', { bubbles: true }));
                slider.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""", int(final_amount))
        
        await asyncio.sleep(0.2)

        # Read back actual value
        actual = await page.evaluate("""() => {
            const inp = document.querySelector('input.value, input[type="text"]');
            return inp ? inp.value : '?';
        }""")

        # Click the Bet/submit button
        submitted = False
        # Try input[type=submit] first (Poker Now uses this)
        submit_btn = await page.query_selector('input[type="submit"]')
        if submit_btn and await submit_btn.is_visible():
            await submit_btn.click()
            submitted = True
        
        if not submitted:
            submitted = await click_action_button(page, "Bet") or await click_action_button(page, "Confirm")
        
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

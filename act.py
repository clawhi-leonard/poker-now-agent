"""
Execute poker actions on Poker Now via keyboard shortcuts.
Keyboard is faster than clicking buttons.

Shortcuts (from Poker Now):
  k = Check
  f = Fold
  c = Call / Bet min
  r = Raise (opens input)
"""
import asyncio
import time
from playwright.async_api import Page


async def execute_action(page: Page, action: str, amount: int | None = None) -> str:
    """
    Execute a poker action. Returns description of what was done.
    
    Actions: check, fold, call, bet, raise
    For bet/raise with custom amount: provide amount param.
    """
    action = action.lower().strip()

    if action == "check":
        await page.keyboard.press("k")
        return "Checked"

    elif action == "fold":
        await page.keyboard.press("f")
        return "Folded"

    elif action == "call":
        await page.keyboard.press("c")
        return "Called"

    elif action in ("bet", "raise"):
        if amount is None:
            # Min bet/raise
            await page.keyboard.press("c")
            return f"Bet/raised minimum"

        # Custom amount: click raise button, clear input, type amount, confirm
        await page.keyboard.press("r")
        await asyncio.sleep(0.15)  # wait for slider/input to appear

        # Find and fill the raise input
        input_el = await page.query_selector('.raise-input input, .bet-input-wrapper input, input[type="number"]')
        if input_el:
            await input_el.click(click_count=3)  # select all
            await input_el.fill(str(amount))
            await asyncio.sleep(0.05)

            # Click confirm/submit
            confirm = await page.query_selector('.raise-confirm button, .bet-confirm button, button.confirm-raise')
            if confirm:
                await confirm.click()
            else:
                await page.keyboard.press("Enter")
            return f"Raised to {amount}"
        else:
            # Fallback: just press c for min
            await page.keyboard.press("c")
            return f"Bet minimum (couldn't find raise input)"

    elif action == "check_fold":
        # Pre-action: check/fold
        btn = await page.query_selector('button:has-text("Check or Fold")')
        if btn:
            await btn.click()
            return "Set check/fold"
        return "Check/fold button not found"

    else:
        return f"Unknown action: {action}"


async def send_chat(page: Page, message: str) -> str:
    """Send a chat message."""
    # Click new message button
    btn = await page.query_selector('button:has-text("New Message")')
    if btn:
        await btn.click()
        await asyncio.sleep(0.1)

    # Find chat input
    chat_input = await page.query_selector('.chat-input input, .chat-input textarea, input.chat-text-input')
    if chat_input:
        await chat_input.fill(message)
        await page.keyboard.press("Enter")
        return f"Sent: {message}"
    return "Chat input not found"

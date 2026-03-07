"""
Multi-Bot Test Harness for Poker Now

Launches multiple browser instances, creates a game, joins bots, and lets them play.
Runs autonomously — auto-starts, auto-rebuys, handles all popups.
"""
import asyncio
import sys
import os
import time
import signal
import traceback
import re
import random
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(__file__))

from hand_eval import get_equity, detect_draws

NUM_BOTS = 3
BOT_NAMES = ["Clawhi", "AceBot", "SharkAI"]
GAME_TYPE = "NLH"
STARTING_STACK = 1000
HEADLESS = True
POLL_MS = 300


async def dismiss_alerts(page):
    """Dismiss any alerts/modals on the page."""
    for sel in [
        '.alert-1-container button:has-text("Confirm")',
        '.alert-1-container button:has-text("Ok")',
        '.alert-1-container button:has-text("OK")',
        '.alert-1-container button:has-text("Yes")',
        'button:has-text("Close")',
        '.modal button:has-text("OK")',
    ]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                try:
                    cb = await page.query_selector('.alert-1-container input[type="checkbox"]')
                    if cb: await cb.click()
                except: pass
                await el.click()
                await asyncio.sleep(0.3)
        except: continue


async def create_game(page, game_type="NLH"):
    """Create a new poker game. Returns game URL."""
    print("🎰 Creating new game...")
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Click Create
    for sel in ['text="Create game"', 'text="Create Game"', 'a:has-text("Create")', 'button:has-text("Create")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(2)
                break
        except: continue

    await asyncio.sleep(2)

    # Name input
    for sel in ['input[placeholder*="name"]', 'input[placeholder*="Name"]', 'input[type="text"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(BOT_NAMES[0])
                await asyncio.sleep(0.3)
                break
        except: continue

    # Submit
    for sel in ['button:has-text("Create")', 'button:has-text("Start")', 'button:has-text("Join")', 'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(3)
                break
        except: continue

    for _ in range(20):
        if "pokernow.club/games/" in page.url:
            break
        await asyncio.sleep(1)

    print(f"   ✅ Game: {page.url}")
    return page.url


async def join_game(page, game_url, player_name):
    """Join an existing game."""
    print(f"   🤖 {player_name} joining...")
    await page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    for sel in ['input[placeholder*="name"]', 'input[placeholder*="Name"]', 'input[type="text"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(player_name)
                await asyncio.sleep(0.3)
                break
        except: continue

    for sel in ['button:has-text("Join")', 'button:has-text("Enter")', 'button:has-text("Play")', 'input[type="submit"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(2)
                break
        except: continue

    await asyncio.sleep(2)
    for sel in ['.table-player-empty', 'button:has-text("Sit")', '.empty-seat']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(1)
                break
        except: continue

    for sel in ['button:has-text("Confirm")', 'button:has-text("OK")', 'button:has-text("Sit Down")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(1)
                break
        except: continue

    print(f"   ✅ {player_name} joined!")


async def start_game(page):
    """Try to start the game."""
    for sel in ['button:has-text("Start")', 'button:has-text("Start Game")', '.start-game-btn']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(1)
                print("   ▶️  Game started!")
                return True
        except: continue
    return False


async def auto_rebuy(page, player_name, amount=1000):
    """Auto-rebuy when busted."""
    for sel in ['button:has-text("Re-buy")', 'button:has-text("Rebuy")', 'button:has-text("Add chips")', 'button:has-text("Buy In")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(1)
                inp = await page.query_selector('input[type="number"], input[type="text"]')
                if inp and await inp.is_visible():
                    await inp.fill(str(amount))
                    await asyncio.sleep(0.3)
                for csel in ['button:has-text("Confirm")', 'button:has-text("OK")', 'button:has-text("Buy")', 'input[type="submit"]']:
                    btn = await page.query_selector(csel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        print(f"   💰 {player_name} rebought {amount}")
                        await asyncio.sleep(1)
                        return True
        except: pass
    return False


async def scrape_state_safe(page):
    """Scrape with timeout."""
    try:
        from scrape import scrape_state
        return await asyncio.wait_for(scrape_state(page), timeout=5.0)
    except:
        return {"is_my_turn": False}


async def execute_action_safe(page, action, amount=None):
    """Execute action with timeout."""
    try:
        from act import execute_action
        return await asyncio.wait_for(execute_action(page, action, amount), timeout=10.0)
    except Exception as e:
        return f"Error: {str(e)[:50]}"


async def bot_decide(state):
    """Local-only decision engine for testing."""
    actions_str = " ".join(state.get("actions", []))
    can_check = "Check" in actions_str
    can_raise = "Raise" in actions_str or "Bet" in actions_str
    can_call = "Call" in actions_str

    my_cards = state.get("my_cards", [])
    board = state.get("board", [])
    num_opps = max(1, sum(1 for p in state.get("players", [])
                          if not p.get("is_me") and p.get("status", "active") == "active"))

    if not my_cards:
        return ("check" if can_check else "fold", None)

    equity = get_equity(my_cards, board if board else None, num_opps)
    pot = int(state.get("pot_total") or state.get("pot") or 0)
    my_stack = 1000
    for p in state.get("players", []):
        if p.get("is_me"):
            try: my_stack = int(p["stack"])
            except: pass

    if can_check and not can_call:
        if equity > 60 and can_raise:
            return ("raise", min(max(4, int(pot * random.uniform(0.5, 0.8))), my_stack))
        return ("check", None)

    if equity >= 65:
        if can_raise:
            return ("raise", min(max(4, int(pot * random.uniform(0.6, 1.0))), my_stack))
        return ("call", None)
    elif equity >= 45:
        if can_raise and random.random() < 0.4:
            return ("raise", min(max(4, int(pot * random.uniform(0.5, 0.7))), my_stack))
        return ("call", None) if can_call else ("check", None)
    elif equity >= 30:
        return ("call", None) if can_call else ("check", None) if can_check else ("fold", None)
    else:
        return ("check", None) if can_check else ("fold", None)


async def bot_loop(page, player_name, is_host, stop_event):
    """Main loop for one bot."""
    print(f"🤖 {player_name} loop starting...")
    last_state_key = None
    last_act_time = 0
    errors = 0
    hands = 0
    last_cards = None

    while not stop_event.is_set():
        try:
            await dismiss_alerts(page)
            if is_host:
                await start_game(page)

            state = await scrape_state_safe(page)

            cards = tuple(state.get("my_cards", []))
            if cards and cards != last_cards and last_cards:
                hands += 1
                if hands % 10 == 0:
                    print(f"   📊 {player_name}: {hands} hands")
            last_cards = cards

            if state.get("is_my_turn"):
                now = time.time()
                if state.get("im_all_in"):
                    await asyncio.sleep(2)
                    continue

                actions_text = " ".join(state.get("actions", []))
                if not any(k in actions_text for k in ["Check", "Call", "Fold", "Raise", "Bet"]):
                    await asyncio.sleep(1)
                    continue

                has_call = any("Call" in a for a in state.get("actions", []))
                pot_val = int(state.get("pot_total") or state.get("pot") or 0)
                state_key = (cards, tuple(state.get("board", [])), has_call, pot_val)

                if state_key == last_state_key and now - last_act_time < 3.0:
                    await asyncio.sleep(0.2)
                    continue

                action, amount = await bot_decide(state)
                if action == "fold" and "Check" in actions_text:
                    action = "check"

                result = await execute_action_safe(page, action, amount)
                street = state.get("street", "?")
                cards_str = " ".join(state.get("my_cards", ["?"]))
                print(f"   {player_name} | {street} | {cards_str} → {action} {amount or ''} | {result}")

                last_act_time = time.time()
                last_state_key = state_key
                errors = 0
                await asyncio.sleep(0.5)
            else:
                # Check rebuy
                my_stack = 0
                for p in state.get("players", []):
                    if p.get("is_me"):
                        try: my_stack = int(p["stack"])
                        except: pass
                if my_stack == 0:
                    await auto_rebuy(page, player_name, STARTING_STACK)

                await asyncio.sleep(POLL_MS / 1000)

        except Exception as e:
            errors += 1
            if errors % 5 == 1:
                print(f"   ⚠️ {player_name} error ({errors}): {str(e)[:80]}")
            if errors > 20:
                await asyncio.sleep(30)
                errors = 0
            else:
                await asyncio.sleep(min(2 ** min(errors, 5), 30))

    print(f"   🛑 {player_name} done. {hands} hands played.")


async def main():
    print("=" * 60)
    print("🃏 Poker Now Multi-Bot Test Harness")
    print(f"   Bots: {', '.join(BOT_NAMES[:NUM_BOTS])}")
    print(f"   Game: {GAME_TYPE} | Stack: {STARTING_STACK}")
    print(f"   Headless: {HEADLESS}")
    print("=" * 60)

    stop_event = asyncio.Event()

    def signal_handler():
        print("\n🛑 Shutting down...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, signal_handler)
        except: pass

    pw = await async_playwright().start()
    browsers = []
    pages = []

    try:
        for i in range(NUM_BOTS):
            print(f"\n🌐 Browser {i+1}/{NUM_BOTS} for {BOT_NAMES[i]}...")
            browser = await pw.chromium.launch(headless=HEADLESS)
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await ctx.new_page()
            browsers.append(browser)
            pages.append(page)

        game_url = await create_game(pages[0], GAME_TYPE)

        if "pokernow.club/games/" not in game_url:
            print("❌ Failed to create game.")
            return

        for i in range(1, NUM_BOTS):
            await join_game(pages[i], game_url, BOT_NAMES[i])
            await asyncio.sleep(2)

        await asyncio.sleep(3)
        await start_game(pages[0])

        print(f"\n{'=' * 60}")
        print("🎮 All bots seated. Running...")
        print(f"{'=' * 60}\n")

        tasks = [asyncio.create_task(bot_loop(pages[i], BOT_NAMES[i], i == 0, stop_event)) for i in range(NUM_BOTS)]
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        print(f"\n❌ Fatal: {e}")
        traceback.print_exc()
    finally:
        print("\n🧹 Cleaning up...")
        for b in browsers:
            try: await b.close()
            except: pass
        await pw.stop()
        print("👋 Done.")


if __name__ == "__main__":
    asyncio.run(main())

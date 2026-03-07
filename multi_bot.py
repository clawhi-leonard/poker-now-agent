"""
Multi-Bot Poker Arena — pokernow.club
Each bot has a distinct play style. Runs autonomously.

v2 - Fixed seating flow based on DOM diagnostic (2026-03-06):
  - Host: Click Sit → fill Your Name + Your Stack → "Take the Seat"
  - Bots: Click Sit → fill Your Name + Intended Stack → "Request the Seat"
  - Host approves bot seat requests
  - Proper game start after all seated
"""
import asyncio
import sys
import os
import time
import signal
import traceback
import re
import random
import json
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file so config.py imports work (needed by scrape.py)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from hand_eval import get_equity, detect_draws

NUM_BOTS = 4
STARTING_STACK = 1000
HEADLESS = False
POLL_MS = 400
LOG_DIR = os.path.expanduser("~/Projects/poker-now-agent/logs")
LOG_FILE = os.path.join(LOG_DIR, f"session_{time.strftime('%Y-%m-%d_%H')}.log")

BOT_PROFILES = [
    {"name": "Clawhi",   "style": "TAG",     "aggression": 0.55, "tightness": 45, "bluff_freq": 0.12, "position_aware": 1.0},
    {"name": "AceBot",   "style": "LAG",     "aggression": 0.70, "tightness": 30, "bluff_freq": 0.25, "position_aware": 0.7},
    {"name": "NitKing",  "style": "NIT",     "aggression": 0.30, "tightness": 60, "bluff_freq": 0.03, "position_aware": 0.5},
    {"name": "CallStn",  "style": "STATION", "aggression": 0.15, "tightness": 25, "bluff_freq": 0.02, "position_aware": 0.3},
]

game_url_global = None
hands_played = {p["name"]: 0 for p in BOT_PROFILES}


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


async def dismiss_cookie_banner(page):
    """Remove the cookie/terms banner that blocks everything."""
    # Method 1: Remove the overlay from DOM directly
    await page.evaluate("""() => {
        const alert = document.querySelector('.alert-1-container');
        if (alert) alert.remove();
    }""")
    await asyncio.sleep(0.3)
    # Method 2: Click "Got it!" if still visible
    try:
        btn = await page.query_selector('button:has-text("Got it")')
        if btn and await btn.is_visible():
            # Also check the "don't show again" checkbox
            try:
                cb = await page.query_selector('.alert-1-container input[type="checkbox"]')
                if cb:
                    await cb.click()
            except:
                pass
            await btn.click()
            await asyncio.sleep(0.5)
    except:
        pass


async def dismiss_alerts(page):
    """Dismiss any popup/modal/alert that appears during gameplay."""
    for sel in ['button:has-text("OK")', 'button:has-text("Confirm")',
                'button:has-text("Close")', 'button:has-text("Dismiss")',
                'button:has-text("Continue")', 'button:has-text("Yes")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.3)
        except:
            continue


async def create_game(page, host_name):
    """Create a new game on pokernow.club. Returns the game URL."""
    log("🎰 Creating new game on pokernow.club...")
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # Dismiss cookie banner
    await dismiss_cookie_banner(page)
    await asyncio.sleep(1)

    # Click "Start a New Game"
    create_clicked = False
    for sel in ['a:has-text("Start a New Game")', 'a.main-ctn-game-button',
                'a:has-text("START A NEW GAME")', 'a:has-text("New Quick Game")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                create_clicked = True
                log(f"   Clicked: {sel}")
                await asyncio.sleep(3)
                break
        except:
            continue

    if not create_clicked:
        log("   ❌ Could not find create game button")
        await page.screenshot(path="/tmp/poker_create_fail.png")
        return None

    # Fill nickname on /start-game page
    name_input = await page.query_selector('input[placeholder="Your Nickname"]')
    if not name_input:
        name_input = await page.query_selector('input[placeholder*="ick"]')
    if not name_input:
        name_input = await page.query_selector('input[type="text"]')

    if name_input and await name_input.is_visible():
        await name_input.fill(host_name)
        log(f"   Filled host name: {host_name}")
    else:
        log("   ⚠️ No name input found on create page")

    await asyncio.sleep(0.5)

    # Click "Create Game"
    for sel in ['button:has-text("Create Game")', 'button.button-1.green',
                'button:has-text("Create")', 'input[type="submit"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log(f"   Submitted game creation")
                break
        except:
            continue

    # Wait for redirect to /games/...
    for i in range(30):
        if "/games/" in page.url:
            log(f"   ✅ Game created: {page.url}")
            return page.url
        await asyncio.sleep(1)

    log(f"   ❌ Timed out waiting for game. URL: {page.url}")
    await page.screenshot(path="/tmp/poker_create_timeout.png")
    return None


async def seat_at_table(page, player_name, stack, seat_number, is_host=False):
    """
    Sit a player at a specific seat.
    Host uses "Take the Seat", bots use "Request the Seat".
    """
    label = "HOST" if is_host else player_name
    log(f"   🪑 {label}: Sitting at seat {seat_number}...")

    # Click the specific seat's Sit button
    seat_sel = f'.table-player-{seat_number} .table-player-seat-button'
    try:
        seat_btn = await page.query_selector(seat_sel)
        if not seat_btn or not await seat_btn.is_visible():
            # Fallback: click nth seat button
            btns = await page.query_selector_all('.table-player-seat-button')
            visible_btns = []
            for b in btns:
                if await b.is_visible():
                    visible_btns.append(b)
            if seat_number - 1 < len(visible_btns):
                seat_btn = visible_btns[seat_number - 1]
            elif visible_btns:
                seat_btn = visible_btns[0]
            else:
                log(f"   ❌ {label}: No visible seat buttons")
                return False

        await seat_btn.click()
        log(f"   {label}: Clicked seat {seat_number}")
        await asyncio.sleep(1.5)
    except Exception as e:
        log(f"   ❌ {label}: Failed to click seat: {e}")
        return False

    # The seat form should now be visible inside the selected seat
    # It has: "Your Name" input, "Your Stack"/"Intended Stack" input, and a submit button

    # Fill the name input (placeholder: "Your Name")
    name_filled = False
    for sel in ['input[placeholder="Your Name"]', 'input[placeholder*="Name"]',
                'input[placeholder="Your Nickname"]']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.triple_click()  # Select all existing text
                    await el.fill(player_name)
                    name_filled = True
                    log(f"   {label}: Filled name: {player_name}")
                    break
            if name_filled:
                break
        except:
            continue

    if not name_filled:
        # Fallback: find text inputs within the selected seat
        try:
            selected = await page.query_selector('.table-player-seat.selected')
            if selected:
                inputs = await selected.query_selector_all('input[type="text"]')
                if inputs and await inputs[0].is_visible():
                    await inputs[0].fill(player_name)
                    name_filled = True
                    log(f"   {label}: Filled name (fallback)")
        except:
            pass

    if not name_filled:
        log(f"   ❌ {label}: Could not fill name input")
        await page.screenshot(path=f"/tmp/poker_seat_fail_{player_name}.png")
        return False

    await asyncio.sleep(0.3)

    # Fill the stack input (placeholder: "Your Stack" for host, "Intended Stack" for bots)
    stack_filled = False
    for sel in ['input[placeholder="Your Stack"]', 'input[placeholder="Intended Stack"]',
                'input[placeholder*="Stack"]', 'input[placeholder*="stack"]']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.triple_click()
                    await el.fill(str(stack))
                    stack_filled = True
                    log(f"   {label}: Filled stack: {stack}")
                    break
            if stack_filled:
                break
        except:
            continue

    if not stack_filled:
        # Fallback: second text input in selected seat
        try:
            selected = await page.query_selector('.table-player-seat.selected')
            if selected:
                inputs = await selected.query_selector_all('input[type="text"]')
                if len(inputs) >= 2 and await inputs[1].is_visible():
                    await inputs[1].fill(str(stack))
                    stack_filled = True
                    log(f"   {label}: Filled stack (fallback)")
        except:
            pass

    await asyncio.sleep(0.3)

    # Click the submit button
    if is_host:
        submit_sel = 'button:has-text("Take the Seat")'
    else:
        submit_sel = 'button:has-text("Request the Seat")'

    submitted = False
    try:
        btn = await page.query_selector(submit_sel)
        if btn and await btn.is_visible():
            await btn.click()
            submitted = True
            log(f"   {label}: Clicked '{submit_sel}'")
    except:
        pass

    if not submitted:
        # Fallback: any green highlighted button in the selected area
        for sel in ['button.button-1.highlighted.green', 'button.med-button',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    submitted = True
                    log(f"   {label}: Submitted via fallback: {sel}")
                    break
            except:
                continue

    await asyncio.sleep(2)

    # Check for validation errors
    error_text = await page.evaluate("""() => {
        const selected = document.querySelector('.table-player-seat.selected');
        if (selected) {
            const text = selected.textContent || '';
            if (text.includes('must be unique')) return 'name_not_unique';
            if (text.includes('error') || text.includes('Error')) return 'error';
        }
        return null;
    }""")

    if error_text:
        log(f"   ⚠️ {label}: Validation error: {error_text}")
        return False

    # Verify seating succeeded (check for "Leave Seat" or "Waiting" status)
    await asyncio.sleep(1)
    if is_host:
        is_seated = await page.evaluate("""() => {
            // Check for Leave Seat button (text match, not :has-text pseudo)
            let hasLeave = false;
            document.querySelectorAll('button').forEach(b => {
                if (b.textContent.trim().includes('Leave Seat')) hasLeave = true;
            });
            const waiting = document.querySelector('.table-player-status-icon.waiting');
            return !!(hasLeave || waiting);
        }""")
    else:
        # Bot: check if the form is gone and player appears
        is_seated = await page.evaluate("""() => {
            const selected = document.querySelector('.table-player-seat.selected');
            return !selected;  // Form should be gone if seating succeeded
        }""")

    if is_seated:
        log(f"   ✅ {label}: Seated successfully!")
    else:
        log(f"   ⚠️ {label}: Seating may have failed (checking again...)")
        await page.screenshot(path=f"/tmp/poker_seat_check_{player_name}.png")

    return True


async def approve_seat_requests(host_page, expected_names, timeout=15):
    """Host approves any pending seat requests from bots."""
    log("   🔍 Host checking for seat requests to approve...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        # Look for approval buttons/notifications
        approved = False
        for sel in ['button:has-text("Approve")', 'button:has-text("Accept")',
                    'button:has-text("Allow")', 'button:has-text("Yes")',
                    'button:has-text("Confirm")']:
            try:
                els = await host_page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        await el.click()
                        approved = True
                        log(f"   ✅ Host approved a seat request")
                        await asyncio.sleep(1)
            except:
                continue

        # Also check for alert-style approval
        await dismiss_alerts(host_page)

        # Check if all expected players are now seated
        seated_count = await host_page.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('.table-player').forEach(p => {
                // Seated players have a name link and stack, and are NOT just seat buttons
                const nameEl = p.querySelector('a');
                const stack = p.querySelector('.table-player-stack');
                if (nameEl && stack) count++;
            });
            return count;
        }""")

        if seated_count >= len(expected_names):
            log(f"   ✅ All {seated_count} players seated!")
            return True

        await asyncio.sleep(1)

    log(f"   ⚠️ Timeout waiting for all players to be seated")
    return False


async def start_game(page):
    """Host starts the game. Returns True if started."""
    for sel in ['button:has-text("Start")', 'button:has-text("Start Game")',
                'button:has-text("Deal")', 'button:has-text("Begin")',
                '.start-game']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log("   ▶️ Game started!")
                await asyncio.sleep(2)
                return True
        except:
            continue
    return False


async def auto_rebuy(page, player_name, amount=1000):
    """Auto-rebuy when a player busts. Handles multiple UI states."""
    # Check if there's a rebuy/add-chips UI visible
    rebuy_clicked = False
    
    # Method 1: Look for rebuy button by text content (can't use :has-text in evaluate)
    try:
        found = await page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, a');
            for (const btn of buttons) {
                const text = (btn.textContent || '').trim().toLowerCase();
                if ((text.includes('re-buy') || text.includes('rebuy') || 
                     text.includes('add chips') || text.includes('buy in') ||
                     text.includes('buy back')) && btn.offsetParent !== null) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        if found:
            rebuy_clicked = True
            await asyncio.sleep(1.5)
    except:
        pass
    
    # Method 2: Try Playwright selectors
    if not rebuy_clicked:
        for sel in ['button:has-text("Re-buy")', 'button:has-text("Rebuy")',
                    'button:has-text("Add chips")', 'button:has-text("Buy In")',
                    'button:has-text("Buy back")', 'a:has-text("Re-buy")']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    rebuy_clicked = True
                    await asyncio.sleep(1.5)
                    break
            except:
                continue
    
    if not rebuy_clicked:
        return False
    
    # Fill the rebuy amount
    amount_filled = False
    for sel in ['input[type="number"]', 'input[type="text"]', 'input[placeholder*="Stack"]',
                'input[placeholder*="stack"]', 'input[placeholder*="amount"]']:
        try:
            inp = await page.query_selector(sel)
            if inp and await inp.is_visible():
                await inp.click(click_count=3)
                await inp.fill(str(amount))
                amount_filled = True
                break
        except:
            continue
    
    if not amount_filled:
        # Try all visible number/text inputs
        try:
            inputs = await page.query_selector_all('input')
            for inp in inputs:
                if await inp.is_visible():
                    inp_type = await inp.get_attribute('type') or ''
                    if inp_type in ('number', 'text', ''):
                        await inp.click(click_count=3)
                        await inp.fill(str(amount))
                        amount_filled = True
                        break
        except:
            pass
    
    await asyncio.sleep(0.5)
    
    # Confirm
    for csel in ['button:has-text("Confirm")', 'button:has-text("OK")',
                  'button:has-text("Buy")', 'button:has-text("Submit")',
                  'input[type="submit"]', 'button.green']:
        try:
            btn = await page.query_selector(csel)
            if btn and await btn.is_visible():
                await btn.click()
                log(f"   💰 {player_name} rebought {amount}")
                await asyncio.sleep(2)
                return True
        except:
            continue
    
    return False


async def scrape_state_safe(page):
    try:
        from scrape import scrape_state
        return await asyncio.wait_for(scrape_state(page), timeout=5.0)
    except Exception as e:
        log(f"   ⚠️ Scrape error: {type(e).__name__}: {str(e)[:80]}")
        return {"is_my_turn": False}


async def execute_action_safe(page, action, amount=None):
    try:
        from act import execute_action
        return await asyncio.wait_for(execute_action(page, action, amount), timeout=10.0)
    except Exception as e:
        return f"Error: {str(e)[:50]}"


def bot_decide(state, profile):
    actions_str = " ".join(state.get("actions", []))
    can_check = "Check" in actions_str
    can_raise = "Raise" in actions_str or "Bet" in actions_str
    can_call = "Call" in actions_str
    street = state.get("street", "preflop")
    pot = int(state.get("pot_total") or state.get("pot") or 0)

    my_cards = state.get("my_cards", [])
    board = state.get("board", [])
    if not my_cards:
        return ("check" if can_check else "fold", None)

    num_opps = max(1, sum(1 for p in state.get("players", [])
                          if not p.get("is_me") and p.get("status", "active") == "active"))
    equity = get_equity(my_cards, board if board else None, num_opps)
    draws = detect_draws(my_cards, board) if board else []
    has_draw = len(draws) > 0

    my_stack = 1000
    for p in state.get("players", []):
        if p.get("is_me"):
            try:
                my_stack = int(p["stack"])
            except:
                pass

    agg = profile["aggression"]
    tight = profile["tightness"]
    bluff = profile["bluff_freq"]
    pos_mult = profile["position_aware"]
    in_pos = state.get("in_position", False)
    pos_adj = 8 * pos_mult if in_pos else 0
    effective_tight = tight - pos_adj

    call_amount = 0
    for a in state.get("actions", []):
        m = re.search(r"Call\s+(\d+)", a)
        if m:
            call_amount = int(m.group(1))

    spr = my_stack / max(pot, 1)

    # Free check
    if can_check and not can_call:
        if equity > 60 and can_raise:
            amt = min(max(4, int(pot * random.uniform(0.4 * agg, 0.9 * agg + 0.3))), my_stack)
            return ("raise", amt)
        if equity > 40 and can_raise and random.random() < agg * 0.5:
            amt = min(max(4, int(pot * random.uniform(0.3, 0.6))), my_stack)
            return ("raise", amt)
        if can_raise and random.random() < bluff * 0.7:
            amt = min(max(4, int(pot * random.uniform(0.4, 0.7))), my_stack)
            return ("raise", amt)
        return ("check", None)

    # Short stack
    if spr < 4:
        if equity >= effective_tight:
            return ("raise", my_stack) if can_raise else ("call", None)
        if equity >= effective_tight - 15 and can_call and call_amount < my_stack * 0.3:
            return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    # PREFLOP
    if street == "preflop":
        raise_thresh = effective_tight + 15
        call_thresh = effective_tight - 5
        if equity >= raise_thresh:
            if can_raise and random.random() < agg + 0.3:
                # Scale raise size with equity — bigger raises for premium hands
                eq_factor = min(1.0, (equity - raise_thresh) / 20 + 0.5)
                amt = min(max(4, int(pot * random.uniform(0.5, 0.8) * eq_factor + pot * 0.2)), my_stack)
                # Cap re-raises: if facing a big bet, need strong equity to continue
                if call_amount > pot * 0.5 and equity < 65:
                    return ("call", None)
                return ("raise", amt)
            return ("call", None) if can_call else ("check", None)
        elif equity >= call_thresh:
            if can_raise and random.random() < agg * 0.3:
                # Only small raises with medium hands
                amt = min(max(4, int(pot * random.uniform(0.4, 0.6))), my_stack)
                # Don't re-raise with medium hands
                if call_amount > 0:
                    return ("call", None)
                return ("raise", amt)
            return ("call", None) if can_call else ("check", None)
        elif equity >= call_thresh - 8:
            # Marginal hands: only limp for very cheap, no raising
            if can_call and call_amount <= max(2, my_stack * 0.02):
                return ("call", None)
            return ("check", None) if can_check else ("fold", None)
        else:
            return ("check", None) if can_check else ("fold", None)

    # POSTFLOP
    value_thresh = 55 - (agg * 10) + pos_adj  # Less aggressive threshold adjustment
    if equity >= value_thresh:
        if can_raise and random.random() < agg + 0.2:
            size_mult = random.uniform(0.4 + agg * 0.2, 0.7 + agg * 0.3)
            amt = min(max(4, int(pot * size_mult)), my_stack)
            return ("raise", amt)
        return ("call", None) if can_call else ("check", None)

    if has_draw and equity >= 25:
        if can_raise and random.random() < agg * 0.6:
            amt = min(max(4, int(pot * random.uniform(0.4, 0.7))), my_stack)
            return ("raise", amt)
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            if pot_odds < equity + 10:
                return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    if equity >= 30:
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            if pot_odds < equity:
                return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    if can_raise and street not in ("river", "turn") and random.random() < bluff:
        # Only bluff on flop, and less frequently
        amt = min(max(4, int(pot * random.uniform(0.4, 0.65))), my_stack)
        return ("raise", amt)

    return ("check", None) if can_check else ("fold", None)


async def bot_loop(page, profile, is_host, stop_event):
    name = profile["name"]
    style = profile["style"]
    log(f"🤖 {name} ({style}) loop starting...")
    last_state_key = None
    last_act_time = 0
    errors = 0
    last_cards = None

    while not stop_event.is_set():
        try:
            # Dismiss any popups
            await dismiss_alerts(page)

            # Host periodically tries to start/deal and approve rebuys
            if is_host:
                await start_game(page)
                # Approve any pending rebuy/seat requests
                for asel in ['button:has-text("Approve")', 'button:has-text("Accept")',
                             'button:has-text("Allow")', 'button:has-text("Yes")']:
                    try:
                        el = await page.query_selector(asel)
                        if el and await el.is_visible():
                            await el.click()
                            log(f"   ✅ {name} approved a request")
                            await asyncio.sleep(0.5)
                    except:
                        pass

            state = await scrape_state_safe(page)
            cards = tuple(state.get("my_cards", []))
            if cards and cards != last_cards and last_cards:
                hands_played[name] = hands_played.get(name, 0) + 1
                h = hands_played[name]
                if h % 25 == 0:
                    log(f"   📊 {name} ({style}): {h} hands played")
            last_cards = cards

            if state.get("is_my_turn"):
                if state.get("im_all_in"):
                    await asyncio.sleep(2)
                    continue
                actions_text = " ".join(state.get("actions", []))
                if not any(k in actions_text for k in ["Check", "Call", "Fold", "Raise", "Bet"]):
                    await asyncio.sleep(1)
                    continue

                has_call = any("Call" in a for a in state.get("actions", []))
                pot_val = int(state.get("pot_total") or state.get("pot") or 0)
                street = state.get("street", "?")
                state_key = (cards, tuple(state.get("board", [])), has_call, pot_val, street)
                # Prevent double-acting: wait at least 2s between actions
                if time.time() - last_act_time < 2.0:
                    await asyncio.sleep(0.5)
                    continue
                if state_key == last_state_key and time.time() - last_act_time < 5.0:
                    await asyncio.sleep(0.3)
                    continue

                action, amount = bot_decide(state, profile)
                if action == "fold" and "Check" in actions_text:
                    action = "check"

                result = await execute_action_safe(page, action, amount)
                street = state.get("street", "?")
                cards_str = " ".join(state.get("my_cards", ["?"]))
                eq = get_equity(state.get("my_cards", []),
                               state.get("board", []) if state.get("board") else None, 1)
                log(f"   {name}({style}) | {street} | {cards_str} | eq={eq:.0f}% → {action} {amount or ''} | {result}")

                last_act_time = time.time()
                last_state_key = state_key
                errors = 0
                # Wait for UI to update after our action
                await asyncio.sleep(random.uniform(1.0, 2.0))
            else:
                my_stack = 0
                for p in state.get("players", []):
                    if p.get("is_me"):
                        try:
                            my_stack = int(p["stack"])
                        except:
                            pass
                # Check for bust/elimination and auto-rebuy
                if my_stack == 0:
                    rebuy_ok = await auto_rebuy(page, name, STARTING_STACK)
                    if rebuy_ok:
                        log(f"   🔄 {name} rebuying after bust")
                    else:
                        # Check if we're eliminated from the table entirely
                        is_eliminated = await page.evaluate("""() => {
                            const body = document.body.textContent.toLowerCase();
                            return body.includes('eliminated') || body.includes('busted') ||
                                   body.includes('you have been removed');
                        }""")
                        if is_eliminated:
                            log(f"   ☠️ {name} eliminated — attempting rejoin")
                            # Try clicking any "rejoin" or "sit" button
                            for rsv in ['button:has-text("Sit")', '.table-player-seat-button',
                                       'button:has-text("Re-join")', 'button:has-text("Rejoin")']:
                                try:
                                    el = await page.query_selector(rsv)
                                    if el and await el.is_visible():
                                        await el.click()
                                        await asyncio.sleep(2)
                                        break
                                except:
                                    continue
                await asyncio.sleep(POLL_MS / 1000)

        except Exception as e:
            errors += 1
            if errors % 5 == 1:
                log(f"   ⚠️ {name} error ({errors}): {str(e)[:80]}")
            if errors > 20:
                await asyncio.sleep(30)
                errors = 0
            else:
                await asyncio.sleep(min(2 ** min(errors, 5), 30))

    log(f"   🛑 {name} done. {hands_played.get(name, 0)} hands.")


async def status_reporter(stop_event):
    while not stop_event.is_set():
        await asyncio.sleep(300)
        total = sum(hands_played.values())
        parts = [f"{n}: {h}h" for n, h in hands_played.items() if h > 0]
        log(f"📊 STATUS | Total: {total} hands | {' | '.join(parts)}")


async def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    log("=" * 60)
    log("🃏 Poker Now Multi-Bot Arena v2")
    log(f"   Bots: {', '.join(p['name'] + '(' + p['style'] + ')' for p in BOT_PROFILES[:NUM_BOTS])}")
    log(f"   Stack: {STARTING_STACK} | Headless: {HEADLESS}")
    log("=" * 60)

    stop_event = asyncio.Event()

    def signal_handler():
        log("🛑 Shutting down...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except:
            pass

    pw = await async_playwright().start()
    browsers = []
    pages = []

    try:
        # Launch all browsers
        for i in range(NUM_BOTS):
            log(f"🌐 Launching browser {i + 1}/{NUM_BOTS} for {BOT_PROFILES[i]['name']}...")
            browser = await pw.chromium.launch(headless=HEADLESS)
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await ctx.new_page()
            page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            browsers.append(browser)
            pages.append(page)

        host_name = BOT_PROFILES[0]["name"]
        host_page = pages[0]

        # ───── STEP 1: Create the game ─────
        global game_url_global
        game_url_global = await create_game(host_page, host_name)

        if not game_url_global or "/games/" not in game_url_global:
            log("❌ Failed to create game.")
            return

        # ───── STEP 2: Dismiss alerts on game page ─────
        await asyncio.sleep(2)
        await dismiss_cookie_banner(host_page)
        await dismiss_alerts(host_page)
        await asyncio.sleep(1)

        # ───── STEP 3: Host sits at seat 1 ─────
        host_seated = await seat_at_table(host_page, host_name, STARTING_STACK, seat_number=1, is_host=True)
        if not host_seated:
            log("❌ Host failed to sit. Check screenshots.")
            await host_page.screenshot(path="/tmp/poker_host_seat_fail.png")
            return

        await asyncio.sleep(2)

        # ───── STEP 4: Bots join and sit ─────
        for i in range(1, NUM_BOTS):
            bot_page = pages[i]
            bot_name = BOT_PROFILES[i]["name"]
            seat_num = i + 1  # Seats 2, 3, 4...

            log(f"🤖 {bot_name} joining game...")
            await bot_page.goto(game_url_global, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Dismiss cookie/alert banners
            await dismiss_cookie_banner(bot_page)
            await dismiss_alerts(bot_page)
            await asyncio.sleep(1)

            # Sit at a specific seat
            seated = await seat_at_table(bot_page, bot_name, STARTING_STACK, seat_number=seat_num, is_host=False)

            if not seated:
                log(f"   ⚠️ {bot_name} may not have seated properly")
                await bot_page.screenshot(path=f"/tmp/poker_bot_seat_fail_{bot_name}.png")

            await asyncio.sleep(2)

            # Host approves seat requests if needed
            await approve_seat_requests(host_page, [p["name"] for p in BOT_PROFILES[:i + 1]], timeout=10)
            await asyncio.sleep(1)

        # ───── STEP 5: Verify all seated ─────
        await asyncio.sleep(3)
        seated_count = await host_page.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('.table-player').forEach(p => {
                const nameEl = p.querySelector('.table-player-name');
                const stack = p.querySelector('.table-player-stack');
                if (nameEl && stack && stack.textContent.trim()) count++;
            });
            return count;
        }""")
        log(f"   📊 Seated players: {seated_count}/{NUM_BOTS}")

        if seated_count < 2:
            log("❌ Not enough players seated. Need at least 2.")
            await host_page.screenshot(path="/tmp/poker_not_enough_seated.png")
            return

        # ───── STEP 6: Start the game ─────
        log("\n🎮 Starting game...")
        game_started = False
        for attempt in range(10):
            if await start_game(host_page):
                game_started = True
                break
            await asyncio.sleep(2)

        if not game_started:
            log("⚠️ Could not find Start button (game may auto-start)")
            await host_page.screenshot(path="/tmp/poker_no_start_btn.png")

        with open("/tmp/poker_game_url.txt", "w") as f:
            f.write(game_url_global)

        log(f"\n{'=' * 60}")
        log(f"🎮 GAME LIVE: {game_url_global}")
        log(f"{'=' * 60}\n")

        # ───── STEP 7: Run bot loops ─────
        tasks = [asyncio.create_task(bot_loop(pages[i], BOT_PROFILES[i], i == 0, stop_event))
                 for i in range(NUM_BOTS)]
        tasks.append(asyncio.create_task(status_reporter(stop_event)))
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        log(f"❌ Fatal: {e}")
        traceback.print_exc()
    finally:
        log("🧹 Cleaning up...")
        for b in browsers:
            try:
                await b.close()
            except:
                pass
        await pw.stop()
        log("👋 Done.")


if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("")
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n⚠️ Top-level crash: {e}")
            traceback.print_exc()
            print("   Restarting in 10s...")
            time.sleep(10)

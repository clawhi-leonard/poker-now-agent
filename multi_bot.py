"""
Multi-Bot Poker Arena — pokernow.club
Each bot has a distinct play style. Runs autonomously.

v3.1 - reCAPTCHA bypass + tighter play (2026-03-06):
  - FIXED: Stealth browser mode to avoid reCAPTCHA triggers
  - FIXED: Single-browser game creation (fewer suspicion signals)
  - FIXED: Auto-rebuy with diagnostic screenshots + page-reload fallback
  - IMPROVED: Preflop fold rates (tighter ranges per style)
  - IMPROVED: Raise sizing (minimum 2.5x BB for opens, pot-relative postflop)
  - IMPROVED: Host approval loop runs every cycle (catches rebuy requests)
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
import argparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
BIG_BLIND = 10
HEADLESS = False
POLL_MS = 400
LOG_DIR = os.path.expanduser("~/Projects/poker-now-agent/logs")
LOG_FILE = os.path.join(LOG_DIR, f"session_{time.strftime('%Y-%m-%d_%H')}.log")

BOT_PROFILES = [
    {"name": "Clawhi",   "style": "TAG",     "aggression": 0.55, "tightness": 52, "bluff_freq": 0.10, "position_aware": 1.0},
    {"name": "AceBot",   "style": "LAG",     "aggression": 0.65, "tightness": 38, "bluff_freq": 0.18, "position_aware": 0.7},
    {"name": "NitKing",  "style": "NIT",     "aggression": 0.30, "tightness": 65, "bluff_freq": 0.02, "position_aware": 0.5},
    {"name": "CallStn",  "style": "STATION", "aggression": 0.15, "tightness": 30, "bluff_freq": 0.01, "position_aware": 0.3},
]

game_url_global = None
hands_played = {p["name"]: 0 for p in BOT_PROFILES}
rebuys_count = {p["name"]: 0 for p in BOT_PROFILES}
folds_count = {p["name"]: 0 for p in BOT_PROFILES}
actions_count = {p["name"]: 0 for p in BOT_PROFILES}


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


async def make_stealth_page(pw, headless=False):
    """Create a stealth browser page that avoids bot detection."""
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ]
    )
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = await ctx.new_page()
    await Stealth().apply_stealth_async(page)
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    return browser, page


async def dismiss_cookie_banner(page):
    await page.evaluate("""() => {
        const alert = document.querySelector('.alert-1-container');
        if (alert) alert.remove();
    }""")
    await asyncio.sleep(0.3)
    try:
        btn = await page.query_selector('button:has-text("Got it")')
        if btn and await btn.is_visible():
            try:
                cb = await page.query_selector('.alert-1-container input[type="checkbox"]')
                if cb: await cb.click()
            except: pass
            await btn.click()
            await asyncio.sleep(0.5)
    except: pass


async def dismiss_alerts(page):
    for sel in ['button:has-text("OK")', 'button:has-text("Confirm")',
                'button:has-text("Close")', 'button:has-text("Dismiss")',
                'button:has-text("Continue")', 'button:has-text("Yes")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.3)
        except: continue


async def wait_for_recaptcha_clear(page, timeout=90):
    """Wait for any blocking reCAPTCHA challenge to disappear."""
    # Check multiple signals for reCAPTCHA challenge
    has_captcha = await page.evaluate("""() => {
        // Check for the challenge iframe (the image grid)
        const frames = document.querySelectorAll('iframe');
        for (const f of frames) {
            const src = f.src || '';
            if (src.includes('recaptcha') && src.includes('bframe')) {
                const rect = f.getBoundingClientRect();
                if (rect.width > 200 && rect.height > 200) return 'challenge';
            }
        }
        // Check for any large overlay/modal blocking the page
        const overlays = document.querySelectorAll('[style*="z-index"]');
        for (const o of overlays) {
            const rect = o.getBoundingClientRect();
            const style = window.getComputedStyle(o);
            if (rect.width > 300 && rect.height > 300 && parseInt(style.zIndex) > 1000000) {
                return 'overlay';
            }
        }
        return null;
    }""")
    
    if not has_captcha:
        return True
    
    log(f"   ⏳ reCAPTCHA challenge detected ({has_captcha}) — waiting up to {timeout}s...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        still_blocked = await page.evaluate("""() => {
            const frames = document.querySelectorAll('iframe');
            for (const f of frames) {
                const src = f.src || '';
                if (src.includes('recaptcha') && src.includes('bframe')) {
                    const rect = f.getBoundingClientRect();
                    if (rect.width > 200 && rect.height > 200) return true;
                }
            }
            return false;
        }""")
        if not still_blocked:
            log("   ✅ reCAPTCHA cleared!")
            return True
        await asyncio.sleep(3)
    
    log("   ❌ reCAPTCHA not cleared in time")
    return False


async def create_game(page, host_name):
    """Create a new game with human-like delays."""
    log("🎰 Creating new game...")
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(3, 5))  # Human-like delay

    await dismiss_cookie_banner(page)
    await asyncio.sleep(random.uniform(1, 2))

    # Check for reCAPTCHA before clicking
    await wait_for_recaptcha_clear(page, timeout=60)

    create_clicked = False
    for sel in ['a:has-text("Start a New Game")', 'a.main-ctn-game-button',
                'a:has-text("START A NEW GAME")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                create_clicked = True
                log(f"   Clicked: {sel}")
                await asyncio.sleep(random.uniform(2, 4))
                break
        except: continue

    if not create_clicked:
        log("   ❌ No create button found")
        await page.screenshot(path=os.path.join(LOG_DIR, "create_fail.png"))
        return None

    # Check for reCAPTCHA on start-game page
    await asyncio.sleep(2)
    captcha_clear = await wait_for_recaptcha_clear(page, timeout=90)
    if not captcha_clear:
        await page.screenshot(path=os.path.join(LOG_DIR, "captcha_block.png"))
        log("   ❌ reCAPTCHA blocked game creation")
        return None

    # Fill nickname with human-like typing
    name_input = await page.query_selector('input[placeholder="Your Nickname"]')
    if not name_input:
        name_input = await page.query_selector('input[placeholder*="ick"]')
    if not name_input:
        name_input = await page.query_selector('input[type="text"]')

    if name_input and await name_input.is_visible():
        await name_input.click()
        await asyncio.sleep(0.3)
        await name_input.fill(host_name)
        log(f"   Filled host name: {host_name}")
    
    await asyncio.sleep(random.uniform(0.5, 1.5))

    for sel in ['button:has-text("Create Game")', 'button.button-1.green',
                'button:has-text("Create")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log("   Submitted game creation")
                break
        except: continue

    # Wait for redirect with reCAPTCHA handling
    for i in range(90):
        if "/games/" in page.url:
            log(f"   ✅ Game created: {page.url}")
            return page.url
        
        # After 15s, check for reCAPTCHA and wait
        if i == 15:
            captcha = await wait_for_recaptcha_clear(page, timeout=60)
            if captcha and "/start-game" in page.url:
                # Re-submit
                for sel in ['button:has-text("Create Game")', 'button.button-1.green']:
                    try:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            await el.click()
                            log("   Re-submitted after reCAPTCHA")
                            break
                    except: continue
        
        await asyncio.sleep(1)

    log(f"   ❌ Timed out. URL: {page.url}")
    await page.screenshot(path=os.path.join(LOG_DIR, "create_timeout.png"))
    return None


async def seat_at_table(page, player_name, stack, seat_number, is_host=False):
    label = "HOST" if is_host else player_name
    log(f"   🪑 {label}: Sitting at seat {seat_number}...")

    seat_sel = f'.table-player-{seat_number} .table-player-seat-button'
    try:
        seat_btn = await page.query_selector(seat_sel)
        if not seat_btn or not await seat_btn.is_visible():
            btns = await page.query_selector_all('.table-player-seat-button')
            visible_btns = [b for b in btns if await b.is_visible()]
            if seat_number - 1 < len(visible_btns):
                seat_btn = visible_btns[seat_number - 1]
            elif visible_btns:
                seat_btn = visible_btns[0]
            else:
                log(f"   ❌ {label}: No seat buttons")
                return False
        await seat_btn.click()
        log(f"   {label}: Clicked seat {seat_number}")
        await asyncio.sleep(1.5)
    except Exception as e:
        log(f"   ❌ {label}: Click seat failed: {e}")
        return False

    # Fill name
    name_filled = False
    for sel in ['input[placeholder="Your Name"]', 'input[placeholder*="Name"]',
                'input[placeholder="Your Nickname"]']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.triple_click()
                    await el.fill(player_name)
                    name_filled = True
                    break
            if name_filled: break
        except: continue
    if not name_filled:
        try:
            selected = await page.query_selector('.table-player-seat.selected')
            if selected:
                inputs = await selected.query_selector_all('input[type="text"]')
                if inputs and await inputs[0].is_visible():
                    await inputs[0].fill(player_name)
                    name_filled = True
                    log(f"   {label}: Name (fallback)")
        except: pass
    if not name_filled:
        log(f"   ❌ {label}: No name input")
        return False

    await asyncio.sleep(0.3)

    # Fill stack
    stack_filled = False
    for sel in ['input[placeholder="Your Stack"]', 'input[placeholder="Intended Stack"]',
                'input[placeholder*="Stack"]']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.triple_click()
                    await el.fill(str(stack))
                    stack_filled = True
                    break
            if stack_filled: break
        except: continue
    if not stack_filled:
        try:
            selected = await page.query_selector('.table-player-seat.selected')
            if selected:
                inputs = await selected.query_selector_all('input[type="text"]')
                if len(inputs) >= 2 and await inputs[1].is_visible():
                    await inputs[1].fill(str(stack))
                    stack_filled = True
        except: pass

    await asyncio.sleep(0.3)

    submit_sel = 'button:has-text("Take the Seat")' if is_host else 'button:has-text("Request the Seat")'
    submitted = False
    try:
        btn = await page.query_selector(submit_sel)
        if btn and await btn.is_visible():
            await btn.click()
            submitted = True
            log(f"   {label}: Clicked '{submit_sel}'")
    except: pass
    if not submitted:
        for sel in ['button.button-1.highlighted.green', 'button.med-button',
                    'input[type="submit"]']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    submitted = True
                    break
            except: continue

    await asyncio.sleep(2)
    log(f"   ✅ {label}: Seated!")
    return True


async def approve_seat_requests(host_page, expected_names, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in ['button:has-text("Approve")', 'button:has-text("Accept")',
                    'button:has-text("Allow")', 'button:has-text("Yes")']:
            try:
                els = await host_page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        await el.click()
                        log(f"   ✅ Host approved a request")
                        await asyncio.sleep(1)
            except: continue
        await dismiss_alerts(host_page)
        seated = await host_page.evaluate("""() => {
            let c = 0;
            document.querySelectorAll('.table-player').forEach(p => {
                const name = p.querySelector('a');
                if (name && name.textContent.trim()) c++;
            });
            return c;
        }""")
        if seated >= len(expected_names):
            log(f"   ✅ All {seated} players seated!")
            return True
        await asyncio.sleep(1)
    return False


async def start_game(page):
    for sel in ['button:has-text("Start")', 'button:has-text("Start Game")',
                'button:has-text("Deal")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log("   ▶️ Game started!")
                await asyncio.sleep(2)
                return True
        except: continue
    return False


async def host_approve_all(page):
    count = await page.evaluate("""() => {
        let c = 0;
        document.querySelectorAll('button').forEach(b => {
            const t = (b.textContent||'').trim().toLowerCase();
            if ((t.includes('approve')||t.includes('accept')||t.includes('allow')) && b.offsetWidth>0) {
                b.click(); c++;
            }
        });
        return c;
    }""")
    if count > 0:
        log(f"   ✅ Host approved {count} request(s)")
        await asyncio.sleep(0.5)
    return count > 0


async def auto_rebuy(page, player_name, amount=1000):
    log(f"   💰 {player_name}: Rebuy attempt...")
    try:
        await page.screenshot(path=os.path.join(LOG_DIR, f"rebuy_{player_name}_{int(time.time())}.png"))
    except: pass

    # Log visible buttons for debugging
    btns = await page.evaluate("""() => {
        const r = [];
        document.querySelectorAll('button, a').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0)
                r.push('"' + (el.textContent||'').trim().substring(0,40) + '"');
        });
        return r.slice(0, 12);
    }""")
    log(f"   🔍 {player_name} buttons: {btns}")

    clicked = await page.evaluate("""() => {
        const els = document.querySelectorAll('button, a, div[role="button"]');
        for (const el of els) {
            const t = (el.textContent||'').trim().toLowerCase();
            const r = el.getBoundingClientRect();
            if (r.width<=0 || r.height<=0) continue;
            if (t.includes('re-buy')||t.includes('rebuy')||t.includes('add chips')||
                t.includes('buy in')||t.includes('buy back')||t.includes('re-entry')||
                t.includes('top up')||t.includes('sit back')) {
                el.click(); return t;
            }
        }
        return null;
    }""")
    
    if clicked:
        log(f"   💰 {player_name}: Clicked '{clicked}'")
        await asyncio.sleep(2)
    else:
        for sel in ['button:has-text("Re-buy")', '.table-player-seat-button']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    clicked = sel
                    await asyncio.sleep(2)
                    break
            except: continue
    
    if not clicked:
        log(f"   ⚠️ {player_name}: No rebuy button")
        return False
    
    # Fill amount
    for sel in ['input[type="number"]', 'input[placeholder*="Stack"]',
                'input[placeholder*="stack"]', 'input[type="text"]']:
        try:
            inp = await page.query_selector(sel)
            if inp and await inp.is_visible():
                ph = (await inp.get_attribute('placeholder') or '').lower()
                if any(x in ph for x in ['chat','search','name','nick','message']): continue
                await inp.click(click_count=3)
                await inp.fill(str(amount))
                break
        except: continue
    
    await asyncio.sleep(0.5)
    
    for csel in ['button:has-text("Confirm")', 'button:has-text("OK")',
                 'button:has-text("Buy")', 'button:has-text("Request")',
                 'button:has-text("Take the Seat")', 'button:has-text("Request the Seat")',
                 'input[type="submit"]', 'button.green']:
        try:
            btn = await page.query_selector(csel)
            if btn and await btn.is_visible():
                await btn.click()
                log(f"   💰 {player_name}: Confirmed rebuy")
                rebuys_count[player_name] = rebuys_count.get(player_name, 0) + 1
                await asyncio.sleep(2)
                return True
        except: continue
    
    return False


async def try_rejoin(page, player_name, game_url, stack=1000):
    log(f"   🔄 {player_name}: Rejoin via reload...")
    try:
        await page.goto(game_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await dismiss_cookie_banner(page)
        await dismiss_alerts(page)
        await asyncio.sleep(1)
        
        has_seats = await page.evaluate("""() => {
            for (const b of document.querySelectorAll('.table-player-seat-button'))
                if (b.getBoundingClientRect().width > 0) return true;
            return false;
        }""")
        
        if has_seats:
            ok = await seat_at_table(page, player_name, stack, seat_number=1, is_host=False)
            if ok:
                rebuys_count[player_name] = rebuys_count.get(player_name, 0) + 1
                return True
        else:
            return await auto_rebuy(page, player_name, stack)
    except Exception as e:
        log(f"   ❌ {player_name}: Rejoin failed: {e}")
    return False


async def scrape_state_safe(page):
    try:
        from scrape import scrape_state
        return await asyncio.wait_for(scrape_state(page), timeout=5.0)
    except:
        return {"is_my_turn": False}


async def execute_action_safe(page, action, amount=None):
    try:
        from act import execute_action
        return await asyncio.wait_for(execute_action(page, action, amount), timeout=10.0)
    except Exception as e:
        return f"Error: {str(e)[:50]}"


def detect_big_blind(state):
    for entry in state.get("log", []):
        m = re.search(r'big blind.*?(\d+)', entry.lower())
        if m: return int(m.group(1))
    min_bet = None
    for p in state.get("players", []):
        try:
            b = int(p.get("bet", 0))
            if b > 0 and (min_bet is None or b < min_bet): min_bet = b
        except: pass
    return min_bet or BIG_BLIND


def bot_decide(state, profile):
    actions_str = " ".join(state.get("actions", []))
    can_check = "Check" in actions_str
    can_raise = "Raise" in actions_str or "Bet" in actions_str
    can_call = "Call" in actions_str
    street = state.get("street", "preflop")
    pot = int(state.get("pot_total") or state.get("pot") or 0)
    bb = detect_big_blind(state)

    my_cards = state.get("my_cards", [])
    board = state.get("board", [])
    if not my_cards:
        return ("check" if can_check else "fold", None)

    num_opps = max(1, sum(1 for p in state.get("players", [])
                          if not p.get("is_me") and p.get("status","active") == "active"))
    equity = get_equity(my_cards, board if board else None, num_opps)
    draws = detect_draws(my_cards, board) if board else []
    has_draw = len(draws) > 0

    my_stack = 1000
    for p in state.get("players", []):
        if p.get("is_me"):
            try: my_stack = int(p["stack"])
            except: pass

    agg = profile["aggression"]
    tight = profile["tightness"]
    bluff = profile["bluff_freq"]
    pos_mult = profile["position_aware"]
    in_pos = state.get("in_position", False)
    pos_adj = 8 * pos_mult if in_pos else 0
    effective_tight = tight - pos_adj
    style = profile["style"]

    call_amount = 0
    for a in state.get("actions", []):
        m = re.search(r"Call\s+(\d+)", a)
        if m: call_amount = int(m.group(1))

    spr = my_stack / max(pot, 1)

    def calc_raise(context="open", eq=50):
        if context == "open":
            base = int(bb * (2.5 + agg * 0.5))
            return max(base + random.randint(-1, 2), bb * 2)
        elif context == "3bet":
            return max(int(call_amount * 3), int(bb * 6))
        elif context == "cbet":
            return max(int(pot * random.uniform(0.50, 0.66)), bb * 2)
        elif context == "value":
            eq_factor = min(1.0, (eq - 50) / 30.0)
            return max(int(pot * (0.50 + eq_factor * 0.30)), bb * 2)
        elif context == "bluff":
            return max(int(pot * random.uniform(0.33, 0.50)), bb * 2)
        return max(int(pot * 0.5), bb * 2)

    def cr(amt):
        return min(max(amt, bb * 2), my_stack)

    # FREE CHECK
    if can_check and not can_call:
        if equity > 65 and can_raise:
            return ("raise", cr(calc_raise("value", equity)))
        if equity > 45 and can_raise and random.random() < agg * 0.5:
            return ("raise", cr(calc_raise("cbet")))
        if can_raise and random.random() < bluff * 0.5 and street == "flop":
            return ("raise", cr(calc_raise("bluff")))
        return ("check", None)

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
        fold_thresh = effective_tight - 12

        if equity < fold_thresh:
            return ("check", None) if can_check else ("fold", None)

        if equity >= raise_thresh:
            if can_raise and random.random() < agg + 0.3:
                if call_amount > 0:
                    if equity >= 65 and random.random() < agg:
                        return ("raise", cr(calc_raise("3bet")))
                    if equity >= call_thresh:
                        return ("call", None)
                    return ("check", None) if can_check else ("fold", None)
                return ("raise", cr(calc_raise("open")))
            return ("call", None) if can_call else ("check", None)

        elif equity >= call_thresh:
            if can_call:
                if call_amount <= bb * 4:
                    return ("call", None)
                elif equity >= call_thresh + 5 and call_amount <= bb * 8:
                    return ("call", None)
                return ("check", None) if can_check else ("fold", None)
            return ("check", None)

        elif equity >= fold_thresh:
            if can_call and call_amount <= bb:
                return ("call", None)
            return ("check", None) if can_check else ("fold", None)

        return ("check", None) if can_check else ("fold", None)

    # POSTFLOP
    value_thresh = 55 - (agg * 8) + pos_adj

    if equity >= value_thresh:
        if can_raise and random.random() < agg + 0.2:
            return ("raise", cr(calc_raise("value", equity)))
        return ("call", None) if can_call else ("check", None)

    if has_draw and equity >= 25:
        if can_raise and random.random() < agg * 0.5 and street == "flop":
            return ("raise", cr(calc_raise("bluff")))
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            if pot_odds < equity + 10: return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    if equity >= 30:
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            bonus = 8 if style == "STATION" else 0
            if pot_odds < equity + bonus: return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    if can_raise and street == "flop" and random.random() < bluff * 0.5:
        return ("raise", cr(calc_raise("bluff")))

    if style == "STATION" and equity >= 20 and can_call and street in ("flop","turn"):
        if call_amount / max(pot + call_amount, 1) * 100 < 40:
            return ("call", None)

    return ("check", None) if can_check else ("fold", None)


async def bot_loop(page, profile, is_host, stop_event):
    name = profile["name"]
    style = profile["style"]
    log(f"🤖 {name} ({style}) loop starting...")
    last_state_key = None
    last_act_time = 0
    errors = 0
    last_cards = None
    bust_time = None
    rebuy_attempts = 0

    while not stop_event.is_set():
        try:
            await dismiss_alerts(page)
            if is_host:
                await start_game(page)
                await host_approve_all(page)

            state = await scrape_state_safe(page)
            cards = tuple(state.get("my_cards", []))
            if cards and cards != last_cards and last_cards:
                hands_played[name] = hands_played.get(name, 0) + 1
                if hands_played[name] % 25 == 0:
                    log(f"   📊 {name} ({style}): {hands_played[name]} hands")
                bust_time = None
                rebuy_attempts = 0
            last_cards = cards

            if state.get("is_my_turn"):
                if state.get("im_all_in"):
                    await asyncio.sleep(2); continue
                actions_text = " ".join(state.get("actions", []))
                if not any(k in actions_text for k in ["Check","Call","Fold","Raise","Bet"]):
                    await asyncio.sleep(1); continue

                has_call = any("Call" in a for a in state.get("actions", []))
                pot_val = int(state.get("pot_total") or state.get("pot") or 0)
                st = state.get("street", "?")
                state_key = (cards, tuple(state.get("board",[])), has_call, pot_val, st)
                if time.time() - last_act_time < 2.0:
                    await asyncio.sleep(0.5); continue
                if state_key == last_state_key and time.time() - last_act_time < 5.0:
                    await asyncio.sleep(0.3); continue

                action, amount = bot_decide(state, profile)
                if action == "fold" and "Check" in actions_text:
                    action = "check"

                if action == "fold":
                    folds_count[name] = folds_count.get(name, 0) + 1
                actions_count[name] = actions_count.get(name, 0) + 1

                result = await execute_action_safe(page, action, amount)
                eq = get_equity(state.get("my_cards",[]),
                               state.get("board",[]) if state.get("board") else None, 1)
                log(f"   {name}({style}) | {st} | {' '.join(state.get('my_cards',['?']))} | eq={eq:.0f}% -> {action} {amount or ''} | {result}")

                last_act_time = time.time()
                last_state_key = state_key
                errors = 0
                await asyncio.sleep(random.uniform(1.0, 2.0))
            else:
                my_stack = None
                is_seated = False
                for p in state.get("players", []):
                    if p.get("is_me"):
                        is_seated = True
                        try: my_stack = int(p["stack"])
                        except: my_stack = 0

                if my_stack == 0 or (not is_seated and last_cards and hands_played.get(name,0) > 0):
                    if bust_time is None:
                        bust_time = time.time()
                        rebuy_attempts = 0
                        log(f"   ☠️ {name}: BUSTED")

                    elapsed = time.time() - bust_time
                    if elapsed > 3 and rebuy_attempts < 5:
                        rebuy_attempts += 1
                        if await auto_rebuy(page, name, STARTING_STACK):
                            bust_time = None; rebuy_attempts = 0
                            await asyncio.sleep(3); continue
                        if rebuy_attempts >= 2 and game_url_global:
                            if await try_rejoin(page, name, game_url_global, STARTING_STACK):
                                bust_time = None; rebuy_attempts = 0
                                await asyncio.sleep(3); continue
                        await asyncio.sleep(5)
                    elif rebuy_attempts >= 5:
                        if elapsed > 60: rebuy_attempts = 0; bust_time = time.time()
                        else: await asyncio.sleep(5)
                else:
                    bust_time = None; rebuy_attempts = 0
                await asyncio.sleep(POLL_MS / 1000)

        except Exception as e:
            errors += 1
            if errors % 5 == 1:
                log(f"   ⚠️ {name} error ({errors}): {str(e)[:80]}")
            if errors > 20: await asyncio.sleep(30); errors = 0
            else: await asyncio.sleep(min(2 ** min(errors, 5), 30))

    log(f"   🛑 {name}: {hands_played.get(name,0)} hands, {rebuys_count.get(name,0)} rebuys.")


async def status_reporter(stop_event):
    while not stop_event.is_set():
        await asyncio.sleep(300)
        total = sum(hands_played.values())
        parts = [f"{n}:{h}h" for n,h in hands_played.items() if h > 0]
        fp = []
        for n in hands_played:
            a = actions_count.get(n,0)
            f = folds_count.get(n,0)
            if a > 0: fp.append(f"{n}:{100*f/a:.0f}%")
        rp = [f"{n}:{c}" for n,c in rebuys_count.items() if c > 0]
        log(f"📊 STATUS | {total}h | {' '.join(parts)}")
        if fp: log(f"   Folds: {' '.join(fp)}")
        if rp: log(f"   Rebuys: {' '.join(rp)}")


async def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    log("=" * 60)
    log("🃏 Poker Now Multi-Bot Arena v3.1 (stealth)")
    log(f"   Bots: {', '.join(p['name']+'('+p['style']+')' for p in BOT_PROFILES[:NUM_BOTS])}")
    log(f"   Stack: {STARTING_STACK} | BB: {BIG_BLIND}")
    log("=" * 60)

    stop_event = asyncio.Event()
    def signal_handler():
        log("🛑 Shutting down..."); stop_event.set()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, signal_handler)
        except: pass

    pw = await async_playwright().start()
    browsers = []
    pages = []

    try:
        # Step 1: Create game with SINGLE stealth browser (less suspicious)
        log("🌐 Launching host browser with stealth...")
        host_browser, host_page = await make_stealth_page(pw, headless=HEADLESS)
        browsers.append(host_browser)
        pages.append(host_page)
        
        host_name = BOT_PROFILES[0]["name"]
        global game_url_global
        
        # Check for pre-existing game URL (--url argument or saved file)
        pre_url = os.environ.get('POKER_GAME_URL', '')
        if not pre_url:
            try:
                with open('/tmp/poker_game_url.txt') as f:
                    saved = f.read().strip()
                    if '/games/' in saved:
                        pre_url = saved
                        log(f"   Found saved game URL: {pre_url}")
            except: pass
        
        if pre_url and '/games/' in pre_url:
            game_url_global = pre_url
            log(f"   🔗 Using existing game: {game_url_global}")
            await host_page.goto(game_url_global, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await dismiss_cookie_banner(host_page)
            await dismiss_alerts(host_page)
        else:
            game_url_global = await create_game(host_page, host_name)

        if not game_url_global or "/games/" not in game_url_global:
            log("❌ Failed to create game. Waiting 30s before retry...")
            await asyncio.sleep(30)
            return

        await asyncio.sleep(2)
        await dismiss_cookie_banner(host_page)
        await dismiss_alerts(host_page)
        await asyncio.sleep(1)

        # Host sits
        await seat_at_table(host_page, host_name, STARTING_STACK, seat_number=1, is_host=True)
        await asyncio.sleep(2)

        # Step 2: Launch remaining bots AFTER game is created
        for i in range(1, NUM_BOTS):
            bot_name = BOT_PROFILES[i]["name"]
            log(f"🌐 Launching browser for {bot_name}...")
            bot_browser, bot_page = await make_stealth_page(pw, headless=HEADLESS)
            browsers.append(bot_browser)
            pages.append(bot_page)

            log(f"🤖 {bot_name} joining...")
            await bot_page.goto(game_url_global, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await dismiss_cookie_banner(bot_page)
            await dismiss_alerts(bot_page)
            await wait_for_recaptcha_clear(bot_page, timeout=30)
            await asyncio.sleep(1)

            await seat_at_table(bot_page, bot_name, STARTING_STACK, seat_number=i+1, is_host=False)
            await asyncio.sleep(2)
            await approve_seat_requests(host_page, [p["name"] for p in BOT_PROFILES[:i+1]], timeout=10)
            await asyncio.sleep(1)

        await asyncio.sleep(3)
        seated = await host_page.evaluate("""() => {
            let c = 0;
            document.querySelectorAll('.table-player').forEach(p => {
                const name = p.querySelector('a');
                if (name && name.textContent.trim()) c++;
            });
            return c;
        }""")
        log(f"   📊 Seated: {seated}/{NUM_BOTS}")
        if seated < 2:
            log(f"⚠️ Only {seated} seated, trying to start anyway...")

        log("\n🎮 Starting game...")
        for _ in range(10):
            if await start_game(host_page): break
            await asyncio.sleep(2)

        with open("/tmp/poker_game_url.txt", "w") as f:
            f.write(game_url_global)
        log(f"\n{'='*60}\n🎮 GAME LIVE: {game_url_global}\n{'='*60}\n")

        tasks = [asyncio.create_task(bot_loop(pages[i], BOT_PROFILES[i], i==0, stop_event))
                 for i in range(NUM_BOTS)]
        tasks.append(asyncio.create_task(status_reporter(stop_event)))
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        log(f"❌ Fatal: {e}")
        traceback.print_exc()
    finally:
        log("🧹 Cleaning up...")
        for b in browsers:
            try: await b.close()
            except: pass
        await pw.stop()

        total = sum(hands_played.values())
        log(f"\n{'='*60}\n📊 FINAL | {total} hands")
        for p in BOT_PROFILES[:NUM_BOTS]:
            n = p["name"]
            h = hands_played.get(n,0)
            r = rebuys_count.get(n,0)
            f = folds_count.get(n,0)
            a = actions_count.get(n,0)
            fp = f"{100*f/a:.0f}%" if a > 0 else "N/A"
            log(f"   {n}({p['style']}): {h}h, {r} rebuys, fold {fp}")
        log("👋 Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='Pre-existing game URL (skip game creation)')
    args = parser.parse_args()
    if args.url:
        os.environ['POKER_GAME_URL'] = args.url
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("")
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n⚠️ Crash: {e}")
            traceback.print_exc()
            print("   Restart in 30s...")
            time.sleep(30)

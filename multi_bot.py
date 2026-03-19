"""
Multi-Bot Poker Arena — pokernow.club
Each bot has a distinct play style. Runs autonomously.

v13.0 - Slider rewrite + deeper stacks (2026-03-18):
  - REWRITE: act.py slider uses 3-tier approach (mouse drag → arrow keys → text input)
  - FIXED: Slider going to max (70% failure rate) → call fallback when all tiers fail
  - CHANGED: STARTING_STACK 1000 → 5000 (500BB) — reduces bust-out frequency 5x
  - ADDED: Slider accuracy stats logged at session end (tier1/tier2/tier3/fallback counts)
  - ADDED: Escape+Call fallback when slider lands at >2x target amount
v12.0 - Bet capping, NIT fix, STATION fix, chip tracking (2026-03-18):
  - FIXED: Flop escalation — max single bet = 2x pot (unless all-in with <25% stack)
  - FIXED: NIT postflop over-aggression — max raise = pot unless equity > 80%
  - FIXED: STATION fold threshold raised 28 → 32 (was calling 4c3h preflop)
  - ADDED: Position + stack logging in action output
  - ADDED: Chip tracking per bot — reports net chip won/lost at session end
  - ADDED: Stack history tracking (stack_history dict, logged every 50 hands)
v11.0 - Re-raise cap, position-based ranges, recalibrated fold rates (2026-03-18):
  - FIXED: Re-raise escalation — max 3 raises/street total, 2 per player → then call/fold
  - FIXED: Preflop fold rates too high — multiway discount 0.85→0.92, thresholds lowered
  - FIXED: Cookie banner more aggressive removal (before every action, kills overlays)
  - IMPROVED: Position-based preflop ranges (BTN opens wider, UTG tighter)
  - IMPROVED: NIT target 45% fold (was 64%), TAG target 35% fold (was 51%)
  - IMPROVED: Per-position equity adjustments: BTN -7, CO -5, UTG +3, SB +3
v10.0 - Fix game stalls, improve postflop play, robust rebuys (2026-03-18):
  - FIXED: Game stalls after all-in — host now clicks Start/Deal every loop
  - FIXED: Host proactively checks for rebuy approvals every 30s (not just on signal)
  - FIXED: Equity uses actual opponent count (was always 1 postflop — wrong!)
  - FIXED: Postflop too passive — increased c-bet frequency, added donk-bet logic
  - FIXED: Value betting too weak — strong hands now bet 60-80% pot consistently  
  - IMPROVED: Monte Carlo sims 300→500 for better equity accuracy
  - IMPROVED: Host bot re-clicks "Start Game" periodically (deals next hand after bust)
  - IMPROVED: Rebuy detection window expanded, host reloads every 30s to catch requests
  - IMPROVED: Better all-in handling — skip action scraping when all-in
v9.0 - Robust rebuy system + decision engine fixes (2026-03-17):
  - FIXED: Rebuy now uses page-reload approach (SPA doesn't re-render seat buttons in-page)
  - FIXED: Bust detection persistence — is_busted flag survives seat transitions
    (Root cause: after Leave Seat, last_cards=() was falsy, resetting bust_time)
  - FIXED: Host rebuy approval coordination via rebuy_pending event
    (Host reloads page when bot signals a seat request, then approves)
  - FIXED: NIT no longer raises river with <70% equity (was raising 838 chips at 48%)
  - FIXED: STATION never 3-bets preflop (calling station behavior)
  - FIXED: STATION prefers calling over raising postflop (only raises 75%+ equity)
  - FIXED: River calling requires better pot odds (equity - 5 vs equity + bonus)
  - IMPROVED: Rebuy retry with 3x seat button search after reload
  - IMPROVED: Increased rebuy attempts from 8 to 10, reset timeout from 90s to 120s
v7.0 - Fix Options menu approval flow (2026-03-15):
  - FIXED: Seat request approvals hidden behind Options menu (hamburger icon w/ red badge)
  - After first inline Accept button, subsequent requests queue in Options panel
  - host_approve_all now: checks inline buttons -> opens Options menu if badge -> checks panel
  - approve_bot timeout increased to 25s (Options menu needs extra time)
  - approve_seat_requests now delegates to host_approve_all (single source of truth)
  - Added Phase 2 (Options menu badge detection) and Phase 3 (notification area) to approval
v4.0 - Robust seating + rebuy + tighter play (2026-03-07):
  - FIXED: Always create fresh games (no stale URL reuse without validation)
  - FIXED: Seat count detection (comprehensive DOM query)
  - FIXED: Host approval with expanded selectors + longer timeouts
  - FIXED: Auto-rebuy with pokernow-specific selectors + page reload fallback
  - FIXED: Preflop ranges tightened (NIT 50%+ fold, STATION 15%+ fold)
  - IMPROVED: Game start detection + retry logic
  - IMPROVED: Comprehensive DOM diagnostics on failures
v5.0 - Better rebuy, tighter ranges, proper sizing (2026-03-10):
  - FIXED: Auto-rebuy via leave-seat-then-re-sit flow (3 approaches)
  - FIXED: Separated _fill_rebuy_form() for clean form handling
  - FIXED: Preflop ranges per style (NIT 50%+, TAG 35%+, LAG 20%+, STATION 10%+ fold)
  - FIXED: Raise sizing BB-based (min 2.5xBB opens, 3x 3-bets, 50-66% pot cbets)
  - FIXED: NIT never bluffs, STATION capped on river calls
  - IMPROVED: Position-adjusted thresholds, SPR-based push/fold
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

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

import tempfile
import urllib.request

NUM_BOTS = 4
STARTING_STACK = 5000  # v13: 500BB — deeper stacks reduce bust-out frequency
BIG_BLIND = 10
HEADLESS = False
POLL_MS = 400
LOG_DIR = os.path.expanduser("~/Projects/poker-now-agent/logs")
LOG_FILE = os.path.join(LOG_DIR, f"session_{time.strftime('%Y-%m-%d_%H')}.log")

BOT_PROFILES = [
    {"name": "Clawhi",   "style": "TAG",     "aggression": 0.55, "tightness": 58, "bluff_freq": 0.08, "position_aware": 1.0},
    {"name": "AceBot",   "style": "LAG",     "aggression": 0.65, "tightness": 42, "bluff_freq": 0.15, "position_aware": 0.7},
    {"name": "NitKing",  "style": "NIT",     "aggression": 0.30, "tightness": 70, "bluff_freq": 0.01, "position_aware": 0.5},
    {"name": "CallStn",  "style": "STATION", "aggression": 0.15, "tightness": 38, "bluff_freq": 0.01, "position_aware": 0.3},
]

game_url_global = None
hands_played = {p["name"]: 0 for p in BOT_PROFILES}
rebuys_count = {p["name"]: 0 for p in BOT_PROFILES}
folds_count = {p["name"]: 0 for p in BOT_PROFILES}
actions_count = {p["name"]: 0 for p in BOT_PROFILES}
stack_history = {p["name"]: [] for p in BOT_PROFILES}  # v12: [(hand_num, stack_value)]
starting_stacks = {}  # v12: track initial stack after first sit-down
rebuy_lock = None  # Initialized in main() as asyncio.Lock()
rebuy_pending = None  # Initialized in main() as asyncio.Event() — signals host to approve rebuy requests
cdp_semaphore = None  # Initialized in main() - limits concurrent CDP calls to prevent Errno 35


async def cdp_safe(page, js_code, arg=None, retries=3, delay=1.5):
    """Execute page.evaluate() with semaphore + Errno 35 retry.
    Prevents macOS socket buffer overflow from concurrent Playwright calls."""
    for attempt in range(retries):
        try:
            async with cdp_semaphore:
                if arg is not None:
                    return await page.evaluate(js_code, arg)
                else:
                    return await page.evaluate(js_code)
        except Exception as e:
            err_str = str(e)
            if "Errno 35" in err_str or "write could not complete" in err_str:
                if attempt < retries - 1:
                    wait = delay * (attempt + 1) + random.uniform(0.5, 2.0)
                    log(f"   ⏳ Errno 35 - backing off {wait:.1f}s (attempt {attempt+1}/{retries})")
                    await asyncio.sleep(wait)
                    continue
            raise
    return None


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


PROFILE_DIR = os.path.expanduser("~/Projects/poker-now-agent/.browser_profiles")


async def make_stealth_page(pw, headless=False, profile_id=0):
    """Create a stealth browser page with persistent profile (reCAPTCHA cookies persist).
    Host (profile_id=0) uses System Chrome for better reCAPTCHA bypass.
    Bot browsers use Playwright Chromium to avoid single-instance conflicts."""
    user_data_dir = os.path.join(PROFILE_DIR, f"bot_{profile_id}")
    os.makedirs(user_data_dir, exist_ok=True)

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # Use Playwright Chromium for all bots. System Chrome conflicts with OpenClaw
    # browser (same executable, macOS single-instance issues). 
    # reCAPTCHA audio solver handles challenges when they appear.
    use_chrome = False
    # Randomize viewport slightly per bot to avoid fingerprint correlation
    vw = 1280 + random.randint(-20, 20) * profile_id
    vh = 800 + random.randint(-10, 10) * profile_id
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir,
        headless=headless,
        executable_path=chrome_path if use_chrome else None,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-infobars',
            '--disable-dev-shm-usage',
            '--disable-extensions',
            f'--window-size={vw},{vh}',
            f'--window-position={100 + profile_id * 50},{100 + profile_id * 50}',
        ],
        viewport={"width": vw, "height": vh},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ignore_default_args=['--enable-automation'],
    )
    if use_chrome:
        log(f"   🌐 Using system Chrome (better reCAPTCHA scores)")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await Stealth().apply_stealth_async(page)
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    # For persistent context, browser=context (context IS the browser)
    return ctx, page


async def dismiss_cookie_banner(page):
    """v11: More aggressive cookie banner removal — kills all overlay elements."""
    await page.evaluate("""() => {
        // Remove cookie banner and any overlay elements that intercept clicks
        document.querySelectorAll('.alert-1-container, .cookie-consent, [class*="cookie"], [class*="consent-banner"]').forEach(el => el.remove());
        // Also remove any fixed/absolute overlays that might block clicks
        document.querySelectorAll('div').forEach(d => {
            const s = getComputedStyle(d);
            const t = (d.textContent || '').toLowerCase();
            if ((s.position === 'fixed' || s.position === 'absolute') && 
                s.zIndex > 999 && (t.includes('cookie') || t.includes('consent') || t.includes('got it'))) {
                d.remove();
            }
        });
    }""")
    await asyncio.sleep(0.2)
    try:
        btn = await page.query_selector('button:has-text("Got it")')
        if btn and await btn.is_visible():
            try:
                cb = await page.query_selector('.alert-1-container input[type="checkbox"]')
                if cb: await cb.click()
            except: pass
            await btn.click()
            await asyncio.sleep(0.3)
    except: pass


async def dismiss_waiting_overlay(page):
    """Dismiss the 'Waiting for others' overlay that blocks seat buttons on pokernow."""
    removed = await page.evaluate("""() => {
        let removed = 0;
        // Remove by class patterns
        document.querySelectorAll('[class*="waiting-for-others"], [class*="share-game"]').forEach(e => {
            e.remove(); removed++;
        });
        // Remove by text content (the overlay with "Waiting for others" / "COPY LINK")
        document.querySelectorAll('div').forEach(d => {
            const t = (d.textContent || '');
            const r = d.getBoundingClientRect();
            // Target the specific centered overlay (not the whole page)
            if (r.width > 200 && r.width < 800 && r.height > 100 && r.height < 400 &&
                (t.includes('Waiting for others') || t.includes('COPY LINK') || t.includes('Share this link'))) {
                // Only remove if it looks like an overlay (positioned in center-ish)
                const cx = r.left + r.width/2;
                const cy = r.top + r.height/2;
                if (cx > 200 && cx < window.innerWidth - 200 && cy > 100 && cy < window.innerHeight - 100) {
                    d.remove(); removed++;
                }
            }
        });
        return removed;
    }""")
    if removed:
        log(f"   🧹 Dismissed waiting overlay ({removed} elements)")
    await asyncio.sleep(0.3)


async def dismiss_alerts(page):
    """Dismiss modals and alerts. Uses Playwright native click for React compatibility."""
    for sel in ['button:has-text("OK")', 'button:has-text("Confirm")',
                'button:has-text("Close")', 'button:has-text("Dismiss")',
                'button:has-text("Continue")', 'button:has-text("Yes")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.3)
        except: continue


async def solve_recaptcha_audio(page, max_attempts=3):
    """Try to solve reCAPTCHA v2 via audio challenge using Google Speech Recognition."""
    if not HAS_SR:
        log("   ⚠️ SpeechRecognition not installed, can't solve audio challenges")
        return False

    for attempt in range(max_attempts):
        log(f"   🔊 Audio solve attempt {attempt+1}/{max_attempts}")

        # Find the bframe (challenge frame)
        bframe = None
        for frame in page.frames:
            furl = frame.url or ''
            if 'recaptcha' in furl and 'bframe' in furl:
                bframe = frame
                break

        if not bframe:
            log("   No reCAPTCHA bframe found")
            return False

        # Click audio button
        try:
            audio_btn = await bframe.query_selector('#recaptcha-audio-button')
            if audio_btn and await audio_btn.is_visible():
                await audio_btn.click()
                log("   Clicked audio button")
                await asyncio.sleep(3)
        except Exception as e:
            log(f"   Audio button click error: {e}")

        await asyncio.sleep(2)

        # Get audio URL
        audio_url = None
        try:
            audio_url = await bframe.evaluate("""() => {
                const audio = document.querySelector('#audio-source');
                return audio ? audio.src : null;
            }""")
        except Exception as e:
            log(f"   Get audio URL error: {e}")

        if not audio_url:
            log("   No audio URL found - may be blocked or wrong mode")
            # Check if we got "automated queries" error
            try:
                error_text = await bframe.evaluate("""() => {
                    const err = document.querySelector('.rc-audiochallenge-error-message');
                    return err ? err.textContent : null;
                }""")
                if error_text:
                    log(f"   reCAPTCHA error: {error_text}")
                    if 'automated' in (error_text or '').lower():
                        log("   ❌ Detected as automated - audio approach blocked")
                        return False
            except: pass
            await asyncio.sleep(2)
            continue

        log(f"   Audio URL: {audio_url[:80]}...")

        # Download audio (async with timeout to prevent event loop blocking)
        try:
            audio_path = os.path.join(tempfile.gettempdir(), f"captcha_audio_{int(time.time())}.mp3")
            def _download():
                urllib.request.urlretrieve(audio_url, audio_path)
                return os.path.getsize(audio_path)
            size = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _download),
                timeout=15.0
            )
            log(f"   Downloaded audio ({size} bytes)")
        except asyncio.TimeoutError:
            log(f"   ⚠️ Audio download timed out (15s) — skipping")
            continue
        except Exception as e:
            log(f"   Download error: {e}")
            continue

        # Transcribe
        try:
            recognizer = sr.Recognizer()
            # pydub converts mp3 -> wav for speech_recognition
            from pydub import AudioSegment
            wav_path = audio_path.replace('.mp3', '.wav')
            AudioSegment.from_mp3(audio_path).export(wav_path, format="wav")
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            log(f"   Transcribed: '{text}'")
        except sr.UnknownValueError:
            log("   Could not understand audio")
            try:
                reload_btn = await bframe.query_selector('#recaptcha-reload-button')
                if reload_btn:
                    await reload_btn.click()
                    await asyncio.sleep(3)
            except: pass
            continue
        except Exception as e:
            log(f"   Transcription error: {e}")
            continue

        # Type the answer
        try:
            response_input = await bframe.query_selector('#audio-response')
            if response_input:
                await response_input.click()
                await asyncio.sleep(0.3)
                # Type character by character with human-like delays
                for ch in text:
                    await response_input.type(ch, delay=random.randint(50, 120))
                log(f"   Typed answer: {text}")
            else:
                log("   No response input found")
                continue
        except Exception as e:
            log(f"   Type error: {e}")
            continue

        # Click verify
        await asyncio.sleep(0.5)
        try:
            verify_btn = await bframe.query_selector('#recaptcha-verify-button')
            if verify_btn:
                await verify_btn.click()
                log("   Clicked Verify")
                await asyncio.sleep(5)
        except Exception as e:
            log(f"   Verify error: {e}")
            continue

        # Check if solved
        still_blocked = await page.evaluate("""() => {
            const frames = document.querySelectorAll('iframe');
            for (const f of frames) {
                if ((f.src||'').includes('recaptcha') && (f.src||'').includes('bframe')) {
                    const r = f.getBoundingClientRect();
                    if (r.width > 200 && r.height > 200) return true;
                }
            }
            return false;
        }""")

        if not still_blocked:
            log("   ✅ reCAPTCHA solved via audio!")
            return True
        else:
            log("   ⚠️ Still blocked after verify - retrying...")
            await asyncio.sleep(2)

    return False


async def wait_for_recaptcha_clear(page, timeout=90):
    """Wait for any blocking reCAPTCHA challenge to disappear.
    With persistent profiles, reCAPTCHA v3 scores improve over time and
    challenges may not appear at all after initial solves."""
    # First, try clicking the reCAPTCHA checkbox (v2) if visible
    try:
        for frame in page.frames:
            if 'recaptcha' in (frame.url or ''):
                checkbox = await frame.query_selector('.recaptcha-checkbox-border')
                if checkbox:
                    await checkbox.click()
                    log("   🔲 Clicked reCAPTCHA checkbox")
                    await asyncio.sleep(3)
    except: pass

    has_captcha = await page.evaluate("""() => {
        const frames = document.querySelectorAll('iframe');
        for (const f of frames) {
            const src = f.src || '';
            if (src.includes('recaptcha') && src.includes('bframe')) {
                const rect = f.getBoundingClientRect();
                if (rect.width > 200 && rect.height > 200) return 'challenge';
            }
        }
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
    
    log(f"   ⏳ reCAPTCHA challenge detected ({has_captcha}) — attempting solve...")

    # If it's a full challenge (not just overlay), try audio solver (with timeout)
    if has_captcha == 'challenge':
        log("   🔊 Attempting audio captcha solve...")
        try:
            solved = await asyncio.wait_for(
                solve_recaptcha_audio(page, max_attempts=3),
                timeout=60.0  # Hard cap: 60s for all audio solve attempts
            )
            if solved:
                return True
        except asyncio.TimeoutError:
            log("   ⚠️ Audio solve hard-timeout (60s)")
        log("   ⚠️ Audio solve failed, waiting passively...")

    # Passive wait as fallback (overlay type or post-solve)
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


async def _human_mouse(page):
    """Simulate human mouse movements to improve reCAPTCHA score."""
    import random
    for _ in range(random.randint(3, 6)):
        x = random.randint(100, 1100)
        y = random.randint(100, 600)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await asyncio.sleep(random.uniform(0.1, 0.5))


async def _human_type(page, selector, text):
    """Type text with human-like delays."""
    el = await page.query_selector(selector)
    if not el:
        return False
    if not await el.is_visible():
        return False
    await el.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(50, 150))
        await asyncio.sleep(random.uniform(0.02, 0.08))
    return True


async def create_game(page, host_name):
    """Create a new game with extensive human-like behavior for reCAPTCHA bypass."""
    log("🎰 Creating new game...")

    # Pre-warm with Google first (builds reCAPTCHA trust score)
    try:
        log("   🌐 Pre-warming with Google...")
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(random.uniform(2, 4))
        await page.mouse.move(400, 300, steps=10)
        await asyncio.sleep(random.uniform(1, 2))
        # Quick search to establish browsing pattern
        search_box = await page.query_selector('textarea[name="q"], input[name="q"]')
        if search_box:
            await search_box.click()
            await asyncio.sleep(0.5)
            for ch in "poker with friends online":
                await page.keyboard.type(ch, delay=random.randint(30, 100))
            await asyncio.sleep(1)
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(2, 4))
            await page.mouse.wheel(0, random.randint(100, 300))
            await asyncio.sleep(random.uniform(1, 2))
    except Exception as e:
        log(f"   Google pre-warm: {e}")

    # Visit pokernow
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(4, 7))

    await dismiss_cookie_banner(page)
    await asyncio.sleep(random.uniform(1, 2))

    # Human-like: move mouse around, scroll
    await _human_mouse(page)
    await page.mouse.wheel(0, random.randint(100, 300))
    await asyncio.sleep(random.uniform(1, 3))
    await page.mouse.wheel(0, random.randint(-300, -100))
    await asyncio.sleep(random.uniform(1, 2))

    # Check for reCAPTCHA before clicking
    await wait_for_recaptcha_clear(page, timeout=30)

    # Click "Start a New Game" with mouse movement first
    create_clicked = False
    for sel in ['a:has-text("Start a New Game")', 'a.main-ctn-game-button',
                'a:has-text("START A NEW GAME")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                box = await el.bounding_box()
                if box:
                    # Move to button naturally
                    await page.mouse.move(
                        box['x'] + box['width'] / 2 + random.randint(-5, 5),
                        box['y'] + box['height'] / 2 + random.randint(-3, 3),
                        steps=random.randint(8, 20))
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                await el.click()
                create_clicked = True
                log(f"   Clicked: {sel}")
                await asyncio.sleep(random.uniform(3, 5))
                break
        except: continue

    if not create_clicked:
        log("   ❌ No create button found")
        await page.screenshot(path=os.path.join(LOG_DIR, "create_fail.png"))
        return None

    # On start-game page — move mouse, then fill form
    await _human_mouse(page)
    await asyncio.sleep(random.uniform(1, 2))

    # Check for reCAPTCHA (v3 scoring happens here)
    captcha_clear = await wait_for_recaptcha_clear(page, timeout=30)
    if not captcha_clear:
        log("   ⚠️ reCAPTCHA challenge present — attempting to proceed anyway...")
        await page.screenshot(path=os.path.join(LOG_DIR, "captcha_block.png"))
        # Don't return None — try to fill form and submit; reCAPTCHA v3 may still pass

    # Fill nickname with character-by-character typing
    typed = False
    for sel in ['input[placeholder="Your Nickname"]', 'input[placeholder*="ick"]', 'input[type="text"]']:
        try:
            typed = await _human_type(page, sel, host_name)
            if typed:
                log(f"   Filled host name: {host_name}")
                break
        except: continue

    await asyncio.sleep(random.uniform(0.5, 1.5))
    await _human_mouse(page)

    # Click Create Game
    for sel in ['button:has-text("Create Game")', 'button.button-1.green',
                'button:has-text("Create")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                box = await el.bounding_box()
                if box:
                    await page.mouse.move(
                        box['x'] + box['width'] / 2 + random.randint(-3, 3),
                        box['y'] + box['height'] / 2 + random.randint(-2, 2),
                        steps=random.randint(5, 12))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                await el.click()
                log("   Submitted game creation")
                break
        except: continue

    # Wait for redirect — actively solve reCAPTCHA if it appears
    captcha_solved_once = False
    for i in range(180):
        if "/games/" in page.url:
            log(f"   ✅ Game created: {page.url}")
            return page.url

        # Check for reCAPTCHA challenge at key intervals
        if i in (5, 15, 30, 60, 90, 120):
            has_challenge = await page.evaluate("""() => {
                const frames = document.querySelectorAll('iframe');
                for (const f of frames) {
                    if ((f.src||'').includes('recaptcha') && (f.src||'').includes('bframe')) {
                        const r = f.getBoundingClientRect();
                        if (r.width > 200 && r.height > 200) return true;
                    }
                }
                return false;
            }""")
            if has_challenge:
                log(f"   🔒 reCAPTCHA challenge at {i}s — trying audio solve...")
                solved = await solve_recaptcha_audio(page, max_attempts=2)
                if solved:
                    captcha_solved_once = True
                    log("   ✅ Captcha solved! Checking for redirect or re-submitting...")
                    await asyncio.sleep(3)
                    if "/games/" in page.url:
                        log(f"   ✅ Game created: {page.url}")
                        return page.url
                    # Re-submit if still on start-game page
                    if "/start-game" in page.url:
                        for sel in ['button:has-text("Create Game")', 'button.button-1.green']:
                            try:
                                el = await page.query_selector(sel)
                                if el and await el.is_visible():
                                    await el.click()
                                    log("   Re-submitted after captcha solve")
                                    break
                            except: continue
                else:
                    log(f"   ⚠️ Audio solve failed at {i}s")
                    await page.screenshot(path=os.path.join(LOG_DIR, f"captcha_fail_{int(time.time())}.png"))

        await asyncio.sleep(1)

    log(f"   ❌ Timed out after 180s. URL: {page.url}")
    await page.screenshot(path=os.path.join(LOG_DIR, "create_timeout.png"))
    return None


async def seat_at_table(page, player_name, stack, seat_number, is_host=False):
    """Seat a player at the table with verification. Uses single evaluate() calls
    to minimize CDP wire messages (prevents Errno 35 on macOS)."""
    label = "HOST" if is_host else player_name
    log(f"   🪑 {label}: Sitting at seat {seat_number}...")

    for attempt in range(3):
        if attempt > 0:
            log(f"   🔄 {label}: Seat attempt {attempt + 1}/3...")
            await asyncio.sleep(2)

        # Dismiss overlays that block seat buttons
        await dismiss_waiting_overlay(page)
        await dismiss_alerts(page)
        await page.evaluate("""() => {
            // Close any overlay modals
            const modals = document.querySelectorAll('.modal, .overlay, [class*="waiting"], [class*="share"]');
            modals.forEach(m => {
                const close = m.querySelector('button[class*="close"], .close, [aria-label="Close"]');
                if (close) close.click();
            });
            const backdrop = document.querySelector('.modal-backdrop, .overlay-backdrop');
            if (backdrop) backdrop.click();
        }""")
        await asyncio.sleep(0.5)

        # Step 1: Click a visible seat button (single CDP call)
        clicked_seat = await page.evaluate("""(seatNum) => {
            // Try specific seat first
            let btn = document.querySelector('.table-player-' + seatNum + ' .table-player-seat-button');
            if (btn && btn.getBoundingClientRect().width > 0) {
                btn.click();
                return 'seat-' + seatNum;
            }
            // Fallback: any visible seat button
            const btns = document.querySelectorAll('.table-player-seat-button');
            for (let i = 0; i < btns.length; i++) {
                if (btns[i].getBoundingClientRect().width > 0) {
                    btns[i].click();
                    return 'seat-fallback-' + i;
                }
            }
            return null;
        }""", seat_number)

        if not clicked_seat:
            # Maybe already seated from a previous attempt
            already = await page.evaluate("""(name) => {
                const youPlayer = document.querySelector('.table-player.you-player');
                if (youPlayer) return 'you-player';
                const players = document.querySelectorAll('.table-player a');
                for (const p of players) {
                    if (p.textContent.trim() === name) return 'found-by-name';
                }
                return null;
            }""", player_name)
            if already:
                log(f"   ✅ {label}: Already seated ({already})")
                return True
            log(f"   ❌ {label}: No seat buttons visible (attempt {attempt+1})")
            continue

        log(f"   {label}: Clicked {clicked_seat}")
        await asyncio.sleep(3)  # Give React time to render seat form

        # Step 2: Fill form (name + stack) and submit — all in one evaluate()
        # ONE CDP call instead of 10+ separate query_selector/fill/click calls
        submit_text = "take the seat" if is_host else "request the seat"
        form_result = await page.evaluate("""(params) => {
            const playerName = params.name;
            const stackAmt = params.stack;
            const submitText = params.submit;
            const result = {name: false, stack: false, submitted: false, diag: []};

            // Set React-compatible input value
            function setInput(input, value) {
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(input, value);
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
            }

            // Find all visible inputs
            const inputs = document.querySelectorAll(
                'input[type="text"], input[type="number"], input:not([type])');
            const visibleInputs = [];
            inputs.forEach(inp => {
                const r = inp.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const ph = (inp.placeholder || '').toLowerCase();
                    visibleInputs.push({el: inp, ph: ph});
                    result.diag.push('input:' + ph);
                }
            });

            // Fill name
            for (const vi of visibleInputs) {
                if (vi.ph.includes('name') || vi.ph.includes('nick')) {
                    setInput(vi.el, playerName);
                    result.name = true;
                    break;
                }
            }

            // Fill stack
            for (const vi of visibleInputs) {
                if (vi.ph.includes('stack') || vi.ph.includes('amount') || vi.ph.includes('buy')) {
                    setInput(vi.el, String(stackAmt));
                    result.stack = true;
                    break;
                }
            }

            // Fallback: positional (first=name, second=stack)
            if (!result.name && visibleInputs.length >= 2) {
                setInput(visibleInputs[0].el, playerName);
                result.name = true;
            }
            if (!result.stack && visibleInputs.length >= 2) {
                setInput(visibleInputs[1].el, String(stackAmt));
                result.stack = true;
            }
            // Single input = probably stack (host has name pre-filled)
            if (!result.stack && visibleInputs.length === 1) {
                setInput(visibleInputs[0].el, String(stackAmt));
                result.stack = true;
                result.diag.push('single-input-as-stack');
            }

            // Click submit button
            const buttons = document.querySelectorAll('button, input[type="submit"]');
            for (const btn of buttons) {
                const t = (btn.textContent || btn.value || '').trim();
                const r = btn.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                const tl = t.toLowerCase();
                // Skip non-seat buttons explicitly
                if (tl.includes('copy') || tl.includes('share') || tl.includes('invite') ||
                    tl.includes('link') || tl.includes('start') || tl.includes('deal') ||
                    tl.includes('sign') || tl.includes('login') || tl.includes('option') ||
                    tl.includes('leave') || tl.includes('away') || tl.includes('chat') ||
                    tl.includes('emoji') || tl.includes('log') || tl.includes('ledger')) continue;
                // Prefer exact seat-submit text
                if (tl.includes(submitText) || tl.includes('take the seat') ||
                    tl.includes('request the seat') || tl === 'confirm' || tl === 'ok') {
                    btn.click();
                    result.submitted = true;
                    result.submitBtn = t;
                    break;
                }
            }

            return result;
        }""", {"name": player_name, "stack": stack, "submit": submit_text})

        log(f"   {label}: Form: name={form_result.get('name')}, stack={form_result.get('stack')}, submitted={form_result.get('submitted')}, btn={form_result.get('submitBtn','?')}, inputs={form_result.get('diag',[])}")

        # Fallback: if form fill failed, try Playwright native fill
        if not form_result.get('name') or not form_result.get('stack'):
            log(f"   {label}: JS form fill incomplete — trying Playwright native fill...")
            for sel in ['input[placeholder*="ick"]', 'input[placeholder*="Name"]', 'input[placeholder*="name"]']:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.click(click_count=3)
                        await el.type(player_name, delay=50)
                        form_result['name'] = True
                        log(f"   {label}: Playwright filled name via {sel}")
                        break
                except: continue
            for sel in ['input[placeholder*="Stack"]', 'input[placeholder*="stack"]',
                        'input[placeholder*="Buy"]', 'input[placeholder*="mount"]']:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.click(click_count=3)
                        await el.type(str(stack), delay=30)
                        form_result['stack'] = True
                        log(f"   {label}: Playwright filled stack via {sel}")
                        break
                except: continue
            await asyncio.sleep(0.5)

        # For non-host bots: if JS submitted the form, return immediately.
        # Don't attempt Playwright native click — it hangs when form is already closing.
        if not is_host and form_result.get('submitted'):
            await asyncio.sleep(1)
            await dismiss_alerts(page)
            log(f"   ✅ {label}: Seat requested via JS (pending host approval)")
            return True

        # Try Playwright native click for the submit button (React needs proper events)
        # Only needed if JS submit failed, or for host (needs DOM verification)
        pw_submitted = False
        pw_submit = 'button:has-text("Take the Seat")' if is_host else 'button:has-text("Request the Seat")'
        for sel in [pw_submit, 'button.button-1.highlighted.green', 'button.med-button']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    # Use timeout to prevent hanging (was hanging 16+ minutes)
                    await asyncio.wait_for(el.click(), timeout=5.0)
                    pw_submitted = True
                    log(f"   {label}: Submit clicked via Playwright: {sel}")
                    break
            except asyncio.TimeoutError:
                log(f"   {label}: ⚠️ Playwright click timed out for {sel}")
                continue
            except: continue
        
        if not pw_submitted and not form_result.get('submitted'):
            log(f"   {label}: ⚠️ Could not submit seat form!")
            # Last resort: try clicking any green/highlighted button
            for sel in ['button.button-1.highlighted', 'button.green', 'button.med-button.green']:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await asyncio.wait_for(el.click(), timeout=5.0)
                        pw_submitted = True
                        log(f"   {label}: Submit via last-resort selector: {sel}")
                        break
                except: continue

        await asyncio.sleep(3)

        # For non-host bots: seat request needs host approval before DOM shows them.
        if not is_host and pw_submitted:
            await asyncio.sleep(1)
            await dismiss_alerts(page)
            log(f"   ✅ {label}: Seat requested via PW (pending host approval)")
            return True

        # Step 3: VERIFY seating (with timeout to avoid hangs)
        is_verified = None
        try:
            is_verified = await asyncio.wait_for(
                page.evaluate("""(name) => {
                    const youPlayer = document.querySelector('.table-player.you-player');
                    if (youPlayer) return 'you-player';
                    const players = document.querySelectorAll('.table-player a');
                    for (const p of players) {
                        if (p.textContent.trim() === name) return 'found-by-name';
                    }
                    return null;
                }""", player_name),
                timeout=8.0
            )
        except asyncio.TimeoutError:
            log(f"   ⚠️ {label}: Verification timed out (page may be loading)")

        if is_verified:
            log(f"   ✅ {label}: Seated and verified ({is_verified})!")
            return True

        log(f"   ⚠️ {label}: Not verified in DOM after submit (attempt {attempt+1})")
        try:
            await page.screenshot(path=os.path.join(LOG_DIR, f"seat_fail_{player_name}_{int(time.time())}.png"))
        except: pass

    log(f"   ❌ {label}: Failed to seat after 3 attempts")
    return False

async def approve_seat_requests(host_page, expected_names, timeout=30):
    """Approve seat requests from bots. Delegates to host_approve_all which handles
    both inline buttons and the Options menu notification badge pattern.
    Polls until all expected players are seated or timeout."""
    deadline = time.time() + timeout
    approved_count = 0
    last_log_time = 0
    diag_taken = False
    
    while time.time() < deadline:
        await dismiss_alerts(host_page)
        
        # DIAGNOSTIC: On first iteration, log ALL visible buttons
        if not diag_taken:
            diag_taken = True
            all_btns = await host_page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('button, a[role="button"], div[role="button"]').forEach(b => {
                    const t = (b.textContent || '').trim();
                    const r = b.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && t.length > 0 && t.length < 100) {
                        results.push(t.substring(0, 50) + ' @(' + Math.round(r.x) + ',' + Math.round(r.y) + ')');
                    }
                });
                return results;
            }""")
            if all_btns:
                log(f"   \U0001f50d DIAG: Host page buttons: {all_btns}")
            
            player_diag = await host_page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('.table-player').forEach(p => {
                    const cls = Array.from(p.classList).join(' ');
                    const a = p.querySelector('a');
                    const name = a ? a.textContent.trim() : '(no-link)';
                    results.push(cls + ' -> ' + name);
                });
                return results;
            }""")
            log(f"   \U0001f50d DIAG: Table players: {player_diag}")
            
            try:
                await host_page.screenshot(path=os.path.join(LOG_DIR, f"approve_diag_{int(time.time())}.png"))
                log(f"   \U0001f4f8 Diagnostic screenshot saved")
            except: pass
        
        # Use host_approve_all (handles inline buttons + Options menu + notifications)
        try:
            result = await asyncio.wait_for(host_approve_all(host_page), timeout=12.0)
            if result:
                approved_count += 1
                log(f"   \u2705 Approval #{approved_count} completed")
                await asyncio.sleep(1.5)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log(f"   \u26a0\ufe0f Approval error: {str(e)[:60]}")

        # Count seated players
        seat_result = await host_page.evaluate("""() => {
            let c = 0;
            const names = [];
            document.querySelectorAll('.table-player').forEach(p => {
                if (p.classList.contains('you-player')) {
                    c++;
                    const nm = p.querySelector('a');
                    names.push('YOU:' + (nm ? nm.textContent.trim() : '(host)'));
                    return;
                }
                const name = p.querySelector('a');
                if (name && name.textContent.trim()) {
                    c++;
                    names.push(name.textContent.trim());
                }
            });
            return {count: c, names: names};
        }""")

        seated = seat_result.get('count', 0) if isinstance(seat_result, dict) else 0
        seat_names = seat_result.get('names', []) if isinstance(seat_result, dict) else []

        if seated >= len(expected_names):
            log(f"   \u2705 All {seated} players seated! ({', '.join(seat_names)})")
            return True

        now = time.time()
        if now - last_log_time >= 5:
            log(f"   \u23f3 Seated: {seated}/{len(expected_names)} ({', '.join(seat_names)}), approved: {approved_count}")
            last_log_time = now

        await asyncio.sleep(1.5)

    # Final count
    seat_result = await host_page.evaluate("""() => {
        let c = 0;
        const names = [];
        document.querySelectorAll('.table-player').forEach(p => {
            if (p.classList.contains('you-player')) { c++; names.push('HOST'); return; }
            const name = p.querySelector('a');
            if (name && name.textContent.trim()) { c++; names.push(name.textContent.trim()); }
        });
        return {count: c, names: names};
    }""")
    seated = seat_result.get('count', 0) if isinstance(seat_result, dict) else 0
    seat_names = seat_result.get('names', []) if isinstance(seat_result, dict) else []
    log(f"   \u26a0\ufe0f Approval timeout. Seated: {seated}/{len(expected_names)} ({', '.join(seat_names)})")
    
    try:
        await host_page.screenshot(path=os.path.join(LOG_DIR, f"approve_fail_{int(time.time())}.png"))
    except: pass
    
    return seated >= 2


async def start_game(page):
    """Click Start/Deal button. Uses cdp_safe for resilience."""
    started = await cdp_safe(page, """() => {
        const targets = ['start', 'start game', 'deal'];
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            const t = (btn.textContent||'').trim().toLowerCase();
            const r = btn.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            for (const target of targets) {
                if (t.includes(target)) { btn.click(); return t; }
            }
        }
        return null;
    }""")
    if started:
        log(f"   ▶️ Game started! (clicked '{started}')")
        await asyncio.sleep(2)
        return True
    return False


async def host_approve_all(page):
    """Approve any pending seat requests using Playwright native clicks.
    
    Pokernow shows seat requests in two ways:
    1. First request: inline notification with Accept button on the main page
    2. Subsequent requests: queued behind the OPTIONS menu (hamburger icon with red badge)
    
    This function handles BOTH patterns.
    """
    approved_any = False
    
    # Phase 1: Check for visible Accept/Approve buttons on the main page
    buttons = await cdp_safe(page, """() => {
        const results = [];
        document.querySelectorAll('button, a, div[role="button"], span[role="button"]').forEach(b => {
            const t = (b.textContent||'').trim();
            const tl = t.toLowerCase();
            const r = b.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return;
            if ((tl.includes('approve') || tl.includes('accept') || tl === 'yes' ||
                 tl === 'allow' || tl === 'ok' || tl === 'confirm') &&
                !tl.includes('cancel') && !tl.includes('deny') && !tl.includes('reject') &&
                !tl.includes('cookie') && !tl.includes('privacy') && !tl.includes('feedback') &&
                !tl.includes('leave') && !tl.includes('options') && t.length < 50) {
                results.push({x: r.x + r.width/2, y: r.y + r.height/2, text: t});
            }
        });
        return results;
    }""")
    
    if buttons and len(buttons) > 0:
        for btn in buttons:
            try:
                await page.mouse.click(btn['x'], btn['y'])
                log(f"   \u2705 Host approved: '{btn['text']}'")
                approved_any = True
                await asyncio.sleep(1)
            except: pass
        return True
    
    # Phase 1b: Playwright selector fallback on main page
    for sel in ['button:has-text("Approve")', 'button:has-text("Accept")',
                'button:has-text("Yes")', 'button.green:has-text("OK")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log(f"   \u2705 Host approved via selector: {sel}")
                await asyncio.sleep(1)
                return True
        except: continue
    
    # Phase 2: Open Options menu if it has a notification badge
    # Pokernow queues seat requests behind the Options (hamburger) menu
    has_badge = await cdp_safe(page, """() => {
        const allEls = document.querySelectorAll('button, a, div[role="button"], [class*="option"], [class*="menu"]');
        for (const el of allEls) {
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            // Check for badge child elements (red notification dot/number)
            const badge = el.querySelector('.badge, [class*="badge"], [class*="count"], [class*="notif"]');
            if (badge) {
                const num = parseInt(badge.textContent);
                if (num > 0) return {x: r.x + r.width/2, y: r.y + r.height/2, badge: num, text: el.textContent.trim().substring(0,30)};
            }
            // Check text for embedded numbers (e.g., "Options 2")
            const t = (el.textContent || '').trim();
            if (t.toLowerCase().includes('option') && /\\d+/.test(t)) {
                const numMatch = t.match(/(\\d+)/);
                if (numMatch) {
                    const num = parseInt(numMatch[1]);
                    if (num > 0) return {x: r.x + r.width/2, y: r.y + r.height/2, badge: num, text: t.substring(0,30)};
                }
            }
        }
        return null;
    }""")
    
    if has_badge:
        log(f"   \U0001f514 Options badge ({has_badge.get('badge')}) \u2014 opening menu...")
        try:
            await page.mouse.click(has_badge['x'], has_badge['y'])
            await asyncio.sleep(2)
            
            # Now look for Accept/Approve in the opened panel (retry 3x)
            for attempt in range(3):
                panel_buttons = await cdp_safe(page, """() => {
                    const results = [];
                    document.querySelectorAll('button, a, div[role="button"], span[role="button"]').forEach(b => {
                        const t = (b.textContent||'').trim();
                        const tl = t.toLowerCase();
                        const r = b.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) return;
                        if ((tl.includes('approve') || tl.includes('accept') || tl === 'yes' ||
                             tl === 'allow') &&
                            !tl.includes('cancel') && !tl.includes('deny') && !tl.includes('cookie') &&
                            !tl.includes('privacy') && t.length < 50) {
                            results.push({x: r.x + r.width/2, y: r.y + r.height/2, text: t});
                        }
                    });
                    return results;
                }""")
                
                if panel_buttons and len(panel_buttons) > 0:
                    for btn in panel_buttons:
                        try:
                            await page.mouse.click(btn['x'], btn['y'])
                            log(f"   \u2705 Host approved from Options: '{btn['text']}'")
                            approved_any = True
                            await asyncio.sleep(1.5)
                        except: pass
                    return True
                
                # Playwright selector fallback inside panel
                for sel in ['button:has-text("Approve")', 'button:has-text("Accept")',
                            'button:has-text("Yes")', '.green:has-text("Accept")']:
                    try:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            await el.click()
                            log(f"   \u2705 Host approved from panel (PW): {sel}")
                            approved_any = True
                            await asyncio.sleep(1)
                    except: continue
                
                if approved_any:
                    return True
                await asyncio.sleep(1)
            
            if not approved_any:
                panel_content = await cdp_safe(page, """() => {
                    const results = [];
                    document.querySelectorAll('button, a').forEach(b => {
                        const t = (b.textContent||'').trim();
                        const r = b.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && t.length > 0 && t.length < 80) {
                            results.push(t.substring(0,40) + ' @(' + Math.round(r.x) + ',' + Math.round(r.y) + ')');
                        }
                    });
                    return results;
                }""")
                log(f"   \U0001f50d Panel buttons after Options: {panel_content}")
        except Exception as e:
            log(f"   \u26a0\ufe0f Options menu interaction failed: {str(e)[:60]}")
    
    # Phase 2c (v12): Always try clicking "OPTIONS" text button even without badge
    # Pokernow may not show a visible badge count in all situations
    if not approved_any:
        try:
            opts_btn = await page.query_selector('button:has-text("OPTIONS"), button:has-text("Options")')
            if opts_btn and await opts_btn.is_visible():
                await opts_btn.click()
                await asyncio.sleep(1.5)
                # Look for Accept/Approve in the panel
                for _ in range(3):
                    accept_btns = await page.query_selector_all('button:has-text("Accept"), button:has-text("Approve")')
                    for abtn in accept_btns:
                        try:
                            if await abtn.is_visible():
                                await abtn.click()
                                log(f"   ✅ Host approved from Options menu (v12 fallback)")
                                approved_any = True
                                await asyncio.sleep(1)
                        except: pass
                    if approved_any:
                        break
                    await asyncio.sleep(0.5)
                # Close the options menu if no approvals found
                if not approved_any:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
        except: pass
    
    if approved_any:
        return True
    
    # Phase 3: Try notification area / chat-based request prompts
    notif_result = await cdp_safe(page, """() => {
        const notifs = document.querySelectorAll('[class*="notification"], [class*="request"], [class*="alert"], [class*="message"]');
        for (const n of notifs) {
            const btns = n.querySelectorAll('button, a');
            for (const b of btns) {
                const t = (b.textContent||'').trim().toLowerCase();
                const r = b.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                if (t.includes('accept') || t.includes('approve') || t === 'yes' || t === 'allow') {
                    b.click();
                    return 'notif:' + t;
                }
            }
        }
        return null;
    }""")
    if notif_result:
        log(f"   \u2705 Host approved via notification: {notif_result}")
        return True
    
    return approved_any


async def leave_seat(page, player_name):
    """Leave the current seat. Returns True if successfully left."""
    log(f"   🚪 {player_name}: Leaving seat...")
    left = await page.evaluate("""() => {
        const els = document.querySelectorAll('button, a, div[role="button"], span');
        for (const el of els) {
            const t = (el.textContent || '').trim().toLowerCase();
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            if (t.includes('leave seat') || t === 'leave' || t.includes('stand up') ||
                t.includes('leave table')) {
                el.click();
                return t;
            }
        }
        return null;
    }""")
    if left:
        log(f"   🚪 {player_name}: Clicked '{left}'")
        await asyncio.sleep(1.5)
        for sel in ['button:has-text("Yes")', 'button:has-text("Confirm")',
                    'button:has-text("OK")', 'button:has-text("Leave")']:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    log(f"   🚪 {player_name}: Confirmed leave")
                    break
            except: continue
        await asyncio.sleep(2)
        return True
    for sel in ['.leave-seat-button', 'button:has-text("LEAVE SEAT")',
                'a:has-text("LEAVE SEAT")', 'button:has-text("Stand Up")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                log(f"   🚪 {player_name}: Clicked '{sel}'")
                await asyncio.sleep(2)
                return True
        except: continue
    log(f"   ⚠️ {player_name}: No leave seat button found")
    return False


async def _fill_rebuy_form(page, player_name, amount):
    """Fill the seat/rebuy form (name + stack + confirm)."""
    for sel in ['input[placeholder="Your Name"]', 'input[placeholder*="Name"]',
                'input[placeholder="Your Nickname"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(click_count=3)
                await el.fill(player_name)
                log(f"   {player_name}: Filled name for rebuy")
                break
        except: continue
    await asyncio.sleep(0.3)
    amount_filled = False
    for sel in ['input[type="number"]', 'input[placeholder*="Stack"]',
                'input[placeholder*="stack"]', 'input[placeholder*="Amount"]',
                'input[placeholder="Intended Stack"]', 'input[placeholder="Your Stack"]']:
        try:
            inp = await page.query_selector(sel)
            if inp and await inp.is_visible():
                await inp.click(click_count=3)
                await inp.fill(str(amount))
                amount_filled = True
                break
        except: continue
    if not amount_filled:
        for sel in ['input[type="text"]']:
            try:
                els = await page.query_selector_all(sel)
                for inp in els:
                    if not await inp.is_visible(): continue
                    ph = (await inp.get_attribute('placeholder') or '').lower()
                    if any(x in ph for x in ['chat', 'search', 'name', 'nick', 'message']): continue
                    await inp.click(click_count=3)
                    await inp.fill(str(amount))
                    amount_filled = True
                    break
                if amount_filled: break
            except: continue
    await asyncio.sleep(0.5)
    for csel in ['button:has-text("Request the Seat")', 'button:has-text("Take the Seat")',
                 'button:has-text("Confirm")', 'button:has-text("OK")',
                 'input[type="submit"]']:
        try:
            btn = await page.query_selector(csel)
            if btn and await btn.is_visible():
                await btn.click()
                log(f"   💰 {player_name}: Confirmed rebuy ({csel})")
                await asyncio.sleep(2)
                return True
        except: continue
    log(f"   ⚠️ {player_name}: Rebuy form filled but no confirm button")
    return False


async def auto_rebuy(page, player_name, amount=1000, is_host=False):
    """Auto-rebuy when busted. Page-reload approach for SPA reliability.
    Strategy: leave-seat (if needed) → confirm → reload page → click seat → fill form.
    v10: Detects "cancel game ingress request" (pending request already submitted).
         Host uses "Take the Seat" (instant), non-host uses "Request the Seat" (needs approval).
         Skips "copy link", "join a live game" etc as submit buttons."""
    log(f"   💰 {player_name}: Rebuy attempt (v10)...")

    if not game_url_global:
        log(f"   ⚠️ {player_name}: No game URL for rebuy")
        return False

    # Step 1: Check current state — try direct rebuy buttons first, then leave seat
    step1_result = await cdp_safe(page, """() => {
        const result = {action: null, hasLeaveSeat: false, hasPending: false, btns: []};
        const allBtns = document.querySelectorAll('button, a, div[role="button"], input[type="submit"]');
        for (const el of allBtns) {
            const t = (el.textContent||'').trim().toLowerCase();
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            result.btns.push(t.substring(0, 40));

            // v10: Detect pending seat request — don't resit, just wait
            if (t.includes('cancel game ingress') || t.includes('cancel request') ||
                t.includes('pending') || t.includes('waiting for approval')) {
                result.hasPending = true;
            }

            // Direct rebuy buttons (pokernow may show these in some game modes)
            if (t.includes('re-buy') || t.includes('rebuy') || t.includes('add chips') ||
                t.includes('buy in') || t.includes('buy back') || t.includes('re-entry') ||
                t.includes('top up') || t.includes('sit back') || t.includes('back to game') ||
                t.includes('rejoin') || t.includes('re-join')) {
                el.click();
                result.action = 'rebuy_clicked:' + t;
                return result;
            }
            if (t.includes('leave seat')) result.hasLeaveSeat = true;
        }
        return result;
    }""")

    if not step1_result:
        log(f"   ⚠️ {player_name}: CDP call failed")
        return False

    action = step1_result.get('action', '')
    has_pending = step1_result.get('hasPending', False)
    log(f"   🔍 {player_name}: step1={action} pending={has_pending} btns={step1_result.get('btns',[])[: 6]}")

    # v12: If pending request exists, signal host and wait. After 3 failed waits, cancel and re-request.
    if has_pending:
        rebuy_pending.set()
        # Track pending wait count per player
        if not hasattr(auto_rebuy, '_pending_waits'):
            auto_rebuy._pending_waits = {}
        auto_rebuy._pending_waits[player_name] = auto_rebuy._pending_waits.get(player_name, 0) + 1
        wait_count = auto_rebuy._pending_waits[player_name]
        
        if wait_count >= 3:
            # v12: Cancel pending request and re-request fresh
            log(f"   🔄 {player_name}: Pending too long ({wait_count} waits) — canceling and re-requesting...")
            auto_rebuy._pending_waits[player_name] = 0
            # Click "cancel game ingress request" button
            await cdp_safe(page, """() => {
                document.querySelectorAll('button, a').forEach(el => {
                    const t = (el.textContent||'').trim().toLowerCase();
                    if (t.includes('cancel game ingress') || t.includes('cancel request')) {
                        el.click();
                    }
                });
            }""")
            await asyncio.sleep(2)
            # Reload and re-request
            async with cdp_semaphore:
                await page.goto(game_url_global, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)
            await dismiss_cookie_banner(page)
            await dismiss_alerts(page)
            # Fall through to normal seat-click flow below
        else:
            log(f"   ⏳ {player_name}: Seat request already pending — signaling host (wait {wait_count}/3)")
            await asyncio.sleep(8)
            # Check if we're now seated
            check = await cdp_safe(page, """() => {
                const yp = document.querySelector('.you-player');
                if (!yp) return null;
                const stack = yp.querySelector('p, div');
                return stack ? stack.textContent.trim() : '0';
            }""")
            if check and check != '0':
                log(f"   ✅ {player_name}: Now seated with stack {check}")
                rebuys_count[player_name] = rebuys_count.get(player_name, 0) + 1
                auto_rebuy._pending_waits[player_name] = 0
                return True
            return False

    # If a direct rebuy button was found and clicked, fill the form
    if action and action.startswith('rebuy_clicked'):
        await asyncio.sleep(2)
        ok = await _fill_rebuy_form_safe(page, player_name, amount)
        if ok:
            rebuys_count[player_name] = rebuys_count.get(player_name, 0) + 1
        return ok

    # Step 2: Leave seat if still seated (busted with 0 chips)
    if step1_result.get('hasLeaveSeat'):
        log(f"   🚪 {player_name}: Leaving seat before reload...")
        await cdp_safe(page, """() => {
            const btns = document.querySelectorAll('button, a, div[role="button"]');
            for (const el of btns) {
                const t = (el.textContent||'').trim().toLowerCase();
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && t.includes('leave seat')) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        await asyncio.sleep(1.5)

        # Confirm leaving
        await cdp_safe(page, """() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const t = (b.textContent||'').trim().toLowerCase();
                const r = b.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                if (t === 'yes' || t === 'confirm' || t === 'ok' || t === 'leave') {
                    b.click(); return true;
                }
            }
            return false;
        }""")
        await asyncio.sleep(2)

    # Step 3: RELOAD PAGE — key fix. The SPA needs a fresh load to show seat buttons.
    log(f"   🔄 {player_name}: Reloading page for clean seat selection...")
    try:
        async with cdp_semaphore:
            await page.goto(game_url_global, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await dismiss_cookie_banner(page)
        await dismiss_alerts(page)
        await asyncio.sleep(1)
    except Exception as e:
        log(f"   ⚠️ {player_name}: Reload failed: {str(e)[:60]}")
        return False

    # Step 4: Find and click a seat button (with retry)
    clicked_seat = False
    for seat_try in range(5):
        clicked_seat = await cdp_safe(page, """() => {
            const btns = document.querySelectorAll('.table-player-seat-button');
            for (const b of btns) {
                if (b.getBoundingClientRect().width > 0) {
                    b.click(); return true;
                }
            }
            return false;
        }""")
        if clicked_seat:
            break
        await asyncio.sleep(2)

    if not clicked_seat:
        log(f"   ⚠️ {player_name}: No seat buttons after reload (5 tries)")
        return False

    log(f"   🪑 {player_name}: Clicked seat button for rebuy")
    await asyncio.sleep(1.5)

    # Step 5: Fill the seat request form (name + stack + submit)
    ok = await _fill_rebuy_form_safe(page, player_name, amount)
    if ok:
        rebuys_count[player_name] = rebuys_count.get(player_name, 0) + 1
        if not is_host:
            # Signal host that a rebuy approval is needed
            rebuy_pending.set()
            log(f"   ✅ {player_name}: Rebuy seat request submitted (pending host approval)")
            # Wait for host to approve
            await asyncio.sleep(5)
        else:
            log(f"   ✅ {player_name}: Host re-seated (instant)")
            await asyncio.sleep(2)
        return True

    log(f"   ⚠️ {player_name}: Failed to fill rebuy seat form")
    return False


async def _fill_rebuy_form_safe(page, player_name, amount):
    """Fill rebuy form using a single cdp_safe evaluate() call."""
    result = await cdp_safe(page, """(params) => {
        const playerName = params.name;
        const stackAmt = params.stack;
        const r = {name: false, stack: false, submitted: false};

        function setInput(input, value) {
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(input, value);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }

        const inputs = document.querySelectorAll('input[type="text"], input[type="number"], input:not([type])');
        const visible = [];
        inputs.forEach(inp => {
            const rect = inp.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                visible.push({el: inp, ph: (inp.placeholder || '').toLowerCase()});
            }
        });

        // Fill name
        for (const vi of visible) {
            if (vi.ph.includes('name') || vi.ph.includes('nick')) {
                setInput(vi.el, playerName);
                r.name = true; break;
            }
        }
        // Fill stack
        for (const vi of visible) {
            if (vi.ph.includes('stack') || vi.ph.includes('amount') || vi.ph.includes('buy')) {
                setInput(vi.el, String(stackAmt));
                r.stack = true; break;
            }
        }
        // Fallback positional
        if (!r.name && visible.length >= 2) { setInput(visible[0].el, playerName); r.name = true; }
        if (!r.stack && visible.length >= 2) { setInput(visible[1].el, String(stackAmt)); r.stack = true; }
        if (!r.stack && visible.length === 1) { setInput(visible[0].el, String(stackAmt)); r.stack = true; }

        // Click submit — v10: strict matching, exclude unrelated buttons
        const buttons = document.querySelectorAll('button, input[type="submit"]');
        for (const btn of buttons) {
            const t = (btn.textContent || btn.value || '').trim().toLowerCase();
            const rect = btn.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            // v10: Skip unrelated buttons
            if (t.includes('copy') || t.includes('join a live') || t.includes('cancel') ||
                t.includes('leave') || t.includes('options') || t.includes('feedback') ||
                t.includes('sound') || t.includes('log') || t.includes('ledger') ||
                t.includes('poker club') || t.includes('shuffle') || t.includes('away')) continue;
            if (t.includes('request the seat') || t.includes('take the seat') ||
                t.includes('confirm') || t === 'ok' || t === 'sit' ||
                (btn.classList.contains('green') && btn.classList.contains('highlighted'))) {
                btn.click();
                r.submitted = true; r.btn = t; break;
            }
        }
        return r;
    }""", {"name": player_name, "stack": amount})

    if result and result.get('submitted'):
        log(f"   💰 {player_name}: Form submitted (btn={result.get('btn','?')})")
        await asyncio.sleep(2)
        return True
    log(f"   ⚠️ {player_name}: Form fill result: {result}")
    return False
async def try_rejoin(page, player_name, game_url, stack=1000):
    """Rejoin by reloading the game page. Uses cdp_safe for Errno 35 resilience."""
    log(f"   🔄 {player_name}: Rejoin via reload...")
    try:
        async with cdp_semaphore:
            await page.goto(game_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await dismiss_cookie_banner(page)
        await dismiss_alerts(page)
        await asyncio.sleep(1)

        has_seats = await cdp_safe(page, """() => {
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
    """Scrape game state with semaphore to prevent Errno 35."""
    try:
        from scrape import scrape_state
        async with cdp_semaphore:
            return await asyncio.wait_for(scrape_state(page), timeout=5.0)
    except Exception as e:
        err = str(e)
        if 'Errno 35' in err:
            await asyncio.sleep(random.uniform(1.0, 3.0))
        return {"is_my_turn": False}


async def execute_action_safe(page, action, amount=None):
    """Execute action with semaphore to prevent Errno 35. v11: dismiss banner before every action."""
    try:
        # v11: Always remove cookie banner before clicking action buttons
        await page.evaluate("() => { document.querySelectorAll('.alert-1-container').forEach(el => el.remove()); }")
        from act import execute_action
        async with cdp_semaphore:
            return await asyncio.wait_for(execute_action(page, action, amount), timeout=10.0)
    except Exception as e:
        err = str(e)
        if 'Errno 35' in err:
            await asyncio.sleep(random.uniform(1.0, 3.0))
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
    """
    Decision engine v12: bet capping, NIT postflop fix, STATION fold fix, chip tracking.
    
    v12 changes:
      - Max single bet = 2x pot on any street (unless all-in with <25% stack remaining)
      - NIT postflop: max raise = pot unless equity > 80%
      - STATION fold threshold 28 → 32 (stop calling with 4c3h, 8s3c)
      - Position + stack logged in action output
    
    v11 changes:
      - Re-raise cap: facing 4-bet+ preflop → call/fold only
      - Preflop thresholds lowered for 4-handed (0.92 multiway discount)
      - Position adjustments: BTN -7, CO -5, UTG +3, SB +3
    """
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
    bluff = profile["bluff_freq"]
    pos_mult = profile["position_aware"]
    in_pos = state.get("in_position", False)
    my_pos = state.get("my_position", "")
    style = profile["style"]

    # v11: Position-based adjustment (wider from late position, tighter from blinds)
    # BTN/CO get -5 to -8 equity threshold (play more hands)
    # SB/BB get +2 to +4 (play fewer hands OOP)
    # UTG gets +3 (tightest)
    POS_ADJUSTMENTS = {
        "BTN": -7, "BTN/SB": -3, "CO": -5, "MP": -2, "HJ": -1,
        "UTG": 3, "UTG+1": 2, "EP": 2,
        "SB": 3, "BB": 2,
    }
    pos_adj = POS_ADJUSTMENTS.get(my_pos, 0) * pos_mult

    # Parse call amount early (needed for raise cap check)
    call_amount = 0
    for a in state.get("actions", []):
        m = re.search(r"Call\s+(\d+)", a)
        if m: call_amount = int(m.group(1))

    # v11: Re-raise cap — prevent escalation wars
    # Heuristic: if the call amount is already large relative to the pot/street, cap raising.
    # Preflop: if call > 8x BB, we're facing a 4-bet+ → don't re-raise (call or fold)
    # Postflop: if call > 50% of pot AND pot > 10x BB, we're in re-raise territory → cap
    # Also count raises in game log as backup signal
    log_entries = state.get("log", [])
    raises_in_log = sum(1 for e in log_entries if "raise" in e.lower())
    
    raise_capped = False
    if street == "preflop" and call_amount > bb * 8:
        raise_capped = True  # Facing 4-bet+, just call or fold
    elif street != "preflop" and call_amount > pot * 0.5 and pot > bb * 10:
        raise_capped = True  # Pot already escalated significantly  
    elif raises_in_log >= 4:
        raise_capped = True  # Many raises in recent log (cross-street but still a signal)
    
    if raise_capped:
        can_raise = False  # Force call/fold only

    # v11: Per-style equity thresholds (recalibrated for 4-handed with 0.92 discount)
    # Lowered from v10 since the multiway discount is softer now
    PREFLOP_THRESHOLDS = {
        "NIT":     {"raise": 58, "call": 50, "fold": 45},
        "TAG":     {"raise": 52, "call": 44, "fold": 40},
        "LAG":     {"raise": 46, "call": 38, "fold": 34},
        "STATION": {"raise": 55, "call": 32, "fold": 32},  # v12: raised from 28 (was calling trash like 4c3h)
    }
    thresholds = PREFLOP_THRESHOLDS.get(style, PREFLOP_THRESHOLDS["TAG"])

    spr = my_stack / max(pot, 1)

    def calc_raise(context="open", eq=50):
        """BB-based raise sizing — never produces tiny raises."""
        if context == "open":
            # 2.5-3.5x BB depending on aggression
            mult = 2.5 + agg
            return int(bb * mult) + random.randint(-1, 2)
        elif context == "3bet":
            # 3x the incoming raise, minimum 7x BB
            return max(int(call_amount * 3), int(bb * 7))
        elif context == "cbet":
            # 50-66% pot, minimum 3x BB
            return max(int(pot * random.uniform(0.50, 0.66)), bb * 3)
        elif context == "value":
            # v10: 60-90% pot proportional to equity, minimum 3x BB
            eq_factor = min(1.0, max(0.0, (eq - 45) / 35.0))
            return max(int(pot * (0.60 + eq_factor * 0.30)), bb * 3)
        elif context == "bluff":
            # 33-50% pot, minimum 2.5x BB
            return max(int(pot * random.uniform(0.33, 0.50)), int(bb * 2.5))
        elif context == "allin_value":
            return my_stack
        return max(int(pot * 0.5), bb * 3)

    def cr(amt):
        """Clamp raise to [2xBB, min(2x pot, stack)].
        v12: Cap at 2x pot to prevent flop escalation to >1000 chips.
        Exception: allow all-in if stack < 25% of pot (short-stacked shove)."""
        amt = max(amt, bb * 2)
        # v12: Max bet = 2x pot (unless short-stacked all-in)
        if pot > 0 and my_stack > pot * 0.25:
            max_bet = max(pot * 2, bb * 6)  # floor of 6xBB to avoid tiny caps
            amt = min(amt, int(max_bet))
        return min(amt, my_stack)

    # ---- FREE CHECK (no call required) ----
    if can_check and not can_call:
        # Strong hands: always bet for value (60-80% pot)
        if equity > 60 and can_raise:
            return ("raise", cr(calc_raise("value", equity)))
        # Medium-strong hands: c-bet or thin value (v10: higher freq for TAG/LAG)
        if equity > 40 and can_raise:
            cbet_freq = agg * 0.85 if street == "flop" else agg * 0.6
            if random.random() < cbet_freq:
                return ("raise", cr(calc_raise("cbet")))
        # Drawing hands: semi-bluff on flop/turn (v10: also on turn)
        if has_draw and equity > 25 and can_raise:
            if street in ("flop", "turn") and random.random() < agg * 0.6:
                return ("raise", cr(calc_raise("bluff")))
        # Pure bluff on flop (rare, never NIT)
        if can_raise and random.random() < bluff * 0.4 and street == "flop" and style != "NIT":
            return ("raise", cr(calc_raise("bluff")))
        return ("check", None)

    # ---- SHORT STACK (SPR < 4) — push/fold ----
    if spr < 4:
        push_thresh = 50 - (agg * 5)  # LAG pushes wider
        if equity >= push_thresh:
            return ("raise", my_stack) if can_raise else ("call", None)
        if equity >= push_thresh - 10 and can_call and call_amount < my_stack * 0.3:
            return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    # ---- PREFLOP ----
    if street == "preflop":
        # v11: pos_adj is negative for late position (play wider) and positive for early (play tighter)
        # Subtracting pos_adj: BTN(-7) → thresh-(-7) = thresh+7 → need LESS equity = play wider ✓
        # Wait, that's wrong. Lower threshold = play more hands. So subtract pos_adj directly.
        # BTN pos_adj=-7: thresh - (-7) = thresh + 7 → HIGHER threshold → tighter. Wrong!
        # Fix: ADD pos_adj (which is negative for BTN → lowers threshold → wider)
        raise_thresh = thresholds["raise"] + pos_adj
        call_thresh  = thresholds["call"]  + pos_adj
        fold_thresh  = thresholds["fold"]  + pos_adj

        # Auto-fold trash
        if equity < fold_thresh:
            return ("check", None) if can_check else ("fold", None)

        # Premium hands — raise or 3-bet
        if equity >= raise_thresh:
            # v9: STATION never 3-bets preflop — they just call (calling station behavior)
            if style == "STATION":
                return ("call", None) if can_call else ("check", None)
            if can_raise and random.random() < agg + 0.2:
                if call_amount > 0:
                    # Facing a raise: 3-bet or call
                    if equity >= 65 and random.random() < agg:
                        return ("raise", cr(calc_raise("3bet")))
                    if equity >= call_thresh:
                        return ("call", None)
                    return ("check", None) if can_check else ("fold", None)
                return ("raise", cr(calc_raise("open")))
            return ("call", None) if can_call else ("check", None)

        # Playable hands — call within size limits
        elif equity >= call_thresh:
            if can_call:
                # Call up to 4x BB with decent hands, up to 8x with strong
                if call_amount <= bb * 4:
                    return ("call", None)
                elif equity >= call_thresh + 8 and call_amount <= bb * 8:
                    return ("call", None)
                return ("check", None) if can_check else ("fold", None)
            return ("check", None)

        # Marginal hands — only limp/call 1 BB
        elif equity >= fold_thresh:
            if can_call and call_amount <= bb:
                return ("call", None)
            return ("check", None) if can_check else ("fold", None)

        return ("check", None) if can_check else ("fold", None)

    # ---- POSTFLOP ---- (v12: NIT raise cap, bet cap, improved value betting)
    # Value threshold: how strong you need to be to bet/raise for value
    # v11: pos_adj is negative for IP (lower threshold = bet more) ✓
    value_thresh = 50 - (agg * 10) + pos_adj
    strong_thresh = 65  # clear value bet territory

    # v9: NIT should never raise on river without 70%+ equity
    nit_river_block = (style == "NIT" and street == "river" and equity < 70)
    
    # v12: NIT postflop raise cap — max raise = pot unless equity > 80%
    # This prevents NIT from raising 5564 on turn with 51% equity
    nit_postflop_block = (style == "NIT" and equity < 80)
    
    # v9: STATION should never raise large amounts — they call, not bet
    station_raise_block = (style == "STATION" and can_call)

    # Very strong hands — always bet/raise for value
    if equity >= strong_thresh:
        if can_raise:
            if nit_river_block:
                return ("call", None) if can_call else ("check", None)
            if station_raise_block and equity < 75:
                return ("call", None)
            # v12: NIT with <80% equity → small bet only (max pot-size), not big raise
            if nit_postflop_block:
                small_bet = min(int(pot * 0.5), my_stack)
                return ("raise", max(small_bet, bb * 2))
            return ("raise", cr(calc_raise("value", equity)))
        return ("call", None) if can_call else ("check", None)

    # Strong hands — bet for value most of the time
    if equity >= value_thresh:
        if can_raise and random.random() < agg + 0.25:
            if nit_river_block:
                return ("call", None) if can_call else ("check", None)
            if station_raise_block:
                return ("call", None)
            # v12: NIT cap at half-pot for value_thresh range (not strong enough for big bets)
            if nit_postflop_block:
                small_bet = min(int(pot * 0.4), my_stack)
                return ("raise", max(small_bet, bb * 2))
            return ("raise", cr(calc_raise("value", equity)))
        return ("call", None) if can_call else ("check", None)

    # Drawing hands — semi-bluff on flop/turn, call with pot odds
    if has_draw and equity >= 25:
        if can_raise and random.random() < agg * 0.5 and street in ("flop", "turn") and style != "NIT":
            return ("raise", cr(calc_raise("bluff")))
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            if pot_odds < equity + 10: return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    # Medium hands — call if pot odds justify
    if equity >= 28:
        if can_call:
            pot_odds = call_amount / max(pot + call_amount, 1) * 100
            bonus = 8 if style == "STATION" else 0
            # On river, require better pot odds (no speculative calling)
            if street == "river":
                if pot_odds < equity - 5 + bonus: return ("call", None)
            else:
                if pot_odds < equity + bonus: return ("call", None)
        return ("check", None) if can_check else ("fold", None)

    # Bluff opportunity (flop only, never NIT, rare)
    if can_raise and street == "flop" and random.random() < bluff * 0.35 and style != "NIT":
        return ("raise", cr(calc_raise("bluff")))

    # Station calling station on flop/turn with marginal hands
    if style == "STATION" and equity >= 20 and can_call and street in ("flop", "turn"):
        pot_odds = call_amount / max(pot + call_amount, 1) * 100
        if pot_odds < 35:
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
    is_busted = False  # v9: persists through seat transitions (fixes last_cards=() reset bug)
    last_host_check = 0  # v10: track when host last did proactive checks
    rebuy_cooldown_until = 0  # v10: after successful rebuy, skip bust detection briefly

    while not stop_event.is_set():
        try:
            await dismiss_alerts(page)
            if is_host:
                # v10: Host always tries to start/deal the next hand
                # This prevents stalls when all-in bust clears and game waits for deal
                await start_game(page)
                await host_approve_all(page)
                
                # v12: More aggressive rebuy approval — check every 15s or on signal
                # Reduced from 60s to catch rebuy requests faster after mass busts
                now = time.time()
                needs_approval_check = False
                if rebuy_pending is not None and rebuy_pending.is_set():
                    rebuy_pending.clear()
                    needs_approval_check = True
                elif now - last_host_check > 15:  # v12: 60s → 15s
                    needs_approval_check = True
                
                if needs_approval_check and now >= rebuy_cooldown_until:
                    try:
                        # v12: First try approval WITHOUT reloading (keeps game state intact)
                        approved = await host_approve_all(page)
                        if approved:
                            log(f"   ✅ Host: Approved rebuy seat request(s) (no reload)")
                            await start_game(page)
                            last_host_check = now
                        elif now - last_host_check > 20:  # v12: 60s → 20s
                            # Reload to catch queued requests not visible on current page
                            state_peek = await scrape_state_safe(page)
                            if not state_peek.get("is_my_turn"):
                                async with cdp_semaphore:
                                    await page.goto(game_url_global, wait_until="domcontentloaded", timeout=15000)
                                await asyncio.sleep(3)
                                await dismiss_cookie_banner(page)
                                await dismiss_alerts(page)
                                approved = await host_approve_all(page)
                                if approved:
                                    log(f"   ✅ Host: Approved rebuy seat request(s) (after reload)")
                                await start_game(page)
                                last_host_check = now
                    except Exception as e:
                        log(f"   ⚠️ Host: Rebuy approval check error: {str(e)[:60]}")

            # v11: Dismiss cookie banner every iteration to prevent click interception
            try:
                await page.evaluate("() => { document.querySelectorAll('.alert-1-container').forEach(el => el.remove()); }")
            except: pass

            state = await scrape_state_safe(page)
            cards = tuple(state.get("my_cards", []))
            if cards and cards != last_cards and last_cards:
                hands_played[name] = hands_played.get(name, 0) + 1
                # v12: Track stack at each new hand
                cur_stack = None
                for p in state.get("players", []):
                    if p.get("is_me"):
                        try: cur_stack = int(p["stack"])
                        except: pass
                if cur_stack is not None:
                    stack_history[name].append((hands_played[name], cur_stack))
                    if name not in starting_stacks:
                        starting_stacks[name] = cur_stack
                if hands_played[name] % 50 == 0:
                    # v12: Report stack changes every 50 hands
                    net = (cur_stack or 0) - starting_stacks.get(name, STARTING_STACK)
                    rebuys = rebuys_count.get(name, 0)
                    net_adj = net - (rebuys * STARTING_STACK)  # Subtract rebuy chips
                    log(f"   📊 {name} ({style}): {hands_played[name]} hands | stack={cur_stack} | net={net_adj:+d} ({rebuys} rebuys)")
                elif hands_played[name] % 25 == 0:
                    log(f"   📊 {name} ({style}): {hands_played[name]} hands")
                bust_time = None
                rebuy_attempts = 0
                is_busted = False
            last_cards = cards

            if state.get("is_my_turn"):
                if state.get("im_all_in"):
                    await asyncio.sleep(3); continue
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
                               state.get("board",[]) if state.get("board") else None,
                               max(1, sum(1 for p in state.get("players", [])
                                          if not p.get("is_me") and p.get("status","active") == "active")))
                pos_str = state.get("my_position", "?")
                stack_str = ""
                for p in state.get("players", []):
                    if p.get("is_me"):
                        try: stack_str = f" stk={int(p['stack'])}"
                        except: pass
                log(f"   {name}({style}) | {st} | {pos_str}{stack_str} | {' '.join(state.get('my_cards',['?']))} | eq={eq:.0f}% -> {action} {amount or ''} | {result}")

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

                # v10: Skip bust detection during rebuy cooldown
                if time.time() < rebuy_cooldown_until:
                    await asyncio.sleep(POLL_MS / 1000)
                    continue

                # v9: Use is_busted flag to persist through seat transitions.
                # Bug fix: after leaving seat, last_cards becomes () (falsy), which
                # previously caused the else branch to reset bust_time.
                newly_busted = (my_stack == 0 and is_seated) or                                (not is_seated and hands_played.get(name, 0) > 0 and not cards)
                
                if is_busted or newly_busted:
                    if not is_busted:
                        # First detection
                        is_busted = True
                        bust_time = time.time()
                        rebuy_attempts = 0
                        log(f"   ☠️ {name}: BUSTED (stack={my_stack}, seated={is_seated})")

                    elapsed = time.time() - bust_time
                    if elapsed > 5 and rebuy_attempts < 10:
                        rebuy_attempts += 1
                        # Stagger per-bot delay to avoid concurrent Playwright writes (Errno 35)
                        bot_idx = next((i for i, p in enumerate(BOT_PROFILES) if p["name"] == name), 0)
                        await asyncio.sleep(3 + bot_idx * 2 + random.uniform(0, 1.5))
                        try:
                            log(f"   💰 {name}: Rebuy attempt #{rebuy_attempts}...")
                            async with rebuy_lock:
                                rebuy_ok = await auto_rebuy(page, name, STARTING_STACK, is_host=is_host)
                            if rebuy_ok:
                                bust_time = None; rebuy_attempts = 0; is_busted = False
                                rebuy_cooldown_until = time.time() + 15  # v10: 15s cooldown
                                log(f"   ✅ {name}: Rebuy successful! (cooldown 15s)")
                                # v12: After host rebuy, immediately approve pending bot requests
                                if is_host:
                                    await asyncio.sleep(2)
                                    try:
                                        approved = await host_approve_all(page)
                                        if approved:
                                            log(f"   ✅ Host: Post-rebuy approval sweep successful")
                                        # Also try reload + approve for queued requests
                                        async with cdp_semaphore:
                                            await page.goto(game_url_global, wait_until="domcontentloaded", timeout=15000)
                                        await asyncio.sleep(2)
                                        await dismiss_cookie_banner(page)
                                        await dismiss_alerts(page)
                                        approved2 = await host_approve_all(page)
                                        if approved2:
                                            log(f"   ✅ Host: Post-rebuy approval sweep (reload) successful")
                                        await start_game(page)
                                    except Exception as e:
                                        log(f"   ⚠️ Host: Post-rebuy approval error: {str(e)[:60]}")
                                await asyncio.sleep(3); continue
                        except Exception as rebuy_err:
                            log(f"   ⚠️ {name}: Rebuy error: {str(rebuy_err)[:60]}")
                        await asyncio.sleep(8)
                    elif rebuy_attempts >= 10:
                        # Reset after long timeout to allow retry
                        if elapsed > 120: rebuy_attempts = 0; bust_time = time.time()
                        else: await asyncio.sleep(10)
                else:
                    bust_time = None; rebuy_attempts = 0; is_busted = False
                await asyncio.sleep(POLL_MS / 1000)

        except Exception as e:
            errors += 1
            err_str = str(e)
            # Detect fatal browser/page closure — stop loop
            if 'has been closed' in err_str or 'Target closed' in err_str:
                if errors == 1:
                    log(f"   ⚠️ {name}: Browser/page closed — exiting loop")
                if errors > 3:
                    log(f"   🛑 {name}: Browser permanently closed after {errors} attempts")
                    break
                await asyncio.sleep(10)
                continue
            if errors % 5 == 1:
                log(f"   ⚠️ {name} error ({errors}): {err_str[:80]}")
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
        # v13: Log slider stats
        try:
            from act import get_slider_stats
            ss = get_slider_stats()
            att = ss.get("attempts", 0)
            if att > 0:
                suc = ss.get("successes", 0)
                log(f"   🎚️ Slider: {suc}/{att} ({100*suc/att:.0f}%) | T1:{ss.get('tier1_ok',0)} T2:{ss.get('tier2_ok',0)} T3:{ss.get('tier3_ok',0)} | Fallback calls:{ss.get('fallback_calls',0)}")
        except: pass


async def main():
    global rebuy_lock, rebuy_pending, cdp_semaphore
    rebuy_lock = asyncio.Lock()
    rebuy_pending = asyncio.Event()
    cdp_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent CDP calls across all bots
    os.makedirs(LOG_DIR, exist_ok=True)
    log("=" * 60)
    log("🃏 Poker Now Multi-Bot Arena v13.0 (slider rewrite + 5000 stacks)")
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
        # Kill any lingering bot browser processes (NOT openclaw browser)
        import subprocess
        # Only kill Chrome/Chromium using our bot profile dirs
        bot_profile_path = os.path.expanduser("~/Projects/poker-now-agent/.browser_profiles")
        subprocess.run(
            ["pkill", "-9", "-f", f"--user-data-dir={bot_profile_path}"],
            capture_output=True)
        await asyncio.sleep(1)
        log("🌐 Launching host browser with stealth...")
        host_browser, host_page = await make_stealth_page(pw, headless=HEADLESS, profile_id=0)
        browsers.append(host_browser)
        pages.append(host_page)
        
        host_name = BOT_PROFILES[0]["name"]
        global game_url_global
        
        # Only use --url flag for existing game (don't auto-load stale URLs from /tmp)
        pre_url = os.environ.get('POKER_GAME_URL', '')
        
        if pre_url and '/games/' in pre_url:
            game_url_global = pre_url
            log(f"   🔗 Validating existing game: {game_url_global}")
            await host_page.goto(game_url_global, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await dismiss_cookie_banner(host_page)
            await dismiss_alerts(host_page)
            # Validate game is active (has table elements)
            is_active = await host_page.evaluate("""() => {
                return document.querySelector('.table-player') !== null ||
                       document.querySelector('.table-cards') !== null ||
                       document.querySelector('.table-pot-size') !== null;
            }""")
            if not is_active:
                log("   ⚠️ Existing game is dead/invalid, creating new one...")
                game_url_global = await create_game(host_page, host_name)
        else:
            game_url_global = await create_game(host_page, host_name)

            # Retry with fresh profile if creation failed (reCAPTCHA flagged)
            if not game_url_global or "/games/" not in game_url_global:
                for retry in range(2):
                    log(f"   🔄 Retry {retry+1}/2: Trying with fresh profile...")
                    # Close old browser
                    try:
                        await host_browser.close()
                        browsers.remove(host_browser)
                    except: pass

                    # Delete flagged profile and create fresh
                    import shutil
                    old_profile = os.path.join(PROFILE_DIR, "bot_0")
                    if os.path.exists(old_profile):
                        shutil.rmtree(old_profile, ignore_errors=True)
                        log(f"   🗑️ Cleared flagged profile: {old_profile}")

                    await asyncio.sleep(random.uniform(10, 20))  # Cool-down

                    host_browser, host_page = await make_stealth_page(pw, headless=HEADLESS, profile_id=0)
                    browsers.insert(0, host_browser)
                    pages[0] = host_page if pages else pages.append(host_page)

                    game_url_global = await create_game(host_page, host_name)
                    if game_url_global and "/games/" in game_url_global:
                        log("   ✅ Game created on retry!")
                        break

        if not game_url_global or "/games/" not in game_url_global:
            log("❌ Failed to create game after all retries. Waiting 60s before restart...")
            await asyncio.sleep(60)
            return

        await asyncio.sleep(2)
        await dismiss_cookie_banner(host_page)
        await dismiss_waiting_overlay(host_page)
        await dismiss_alerts(host_page)
        await asyncio.sleep(1)

        # Host sits (may fail on name input but host is game creator, auto-seated on start)
        host_seated = await seat_at_table(host_page, host_name, STARTING_STACK, seat_number=1, is_host=True)
        if not host_seated:
            log("   ⚠️ Host seating form incomplete — host is game creator, will be auto-seated on start")
        await asyncio.sleep(2)

        # Step 2: Launch remaining bots SEQUENTIALLY with immediate approval
        # Key fix (v6): join each bot, then immediately approve from host
        # before joining the next one. Prevents race conditions and ensures
        # each bot is properly seated.

        async def check_host_alive(hp, game_url):
            """Verify host page is alive and on the game URL."""
            try:
                current_url = hp.url
                if '/games/' not in current_url:
                    log(f"   \u26a0\ufe0f Host page navigated away: {current_url}")
                    await hp.goto(game_url, wait_until='domcontentloaded', timeout=20000)
                    await asyncio.sleep(2)
                    await dismiss_cookie_banner(hp)
                    await dismiss_waiting_overlay(hp)
                # Quick DOM check
                alive = await asyncio.wait_for(
                    hp.evaluate('() => document.readyState'),
                    timeout=5.0
                )
                return alive is not None
            except Exception as e:
                log(f"   \u26a0\ufe0f Host health check failed: {str(e)[:60]}")
                return False

        async def approve_bot(hp, bot_name, max_wait=25):
            """Approve a specific bot's seat request. Polls host page for
            approve/accept buttons up to max_wait seconds.
            Uses host_approve_all which handles both inline buttons AND
            the Options menu notification badge pattern."""
            deadline = time.time() + max_wait
            attempts = 0
            while time.time() < deadline:
                attempts += 1
                try:
                    # host_approve_all now handles:
                    # 1. Inline Accept buttons (first request)
                    # 2. Options menu badge -> open -> Accept (subsequent requests)
                    # 3. Notification area buttons
                    # Give it more time (10s) since it may need to open the Options menu
                    result = await asyncio.wait_for(host_approve_all(hp), timeout=10.0)
                    if result:
                        log(f"   \u2705 Approved {bot_name} seat request (attempt {attempts})")
                        return True
                except asyncio.TimeoutError:
                    log(f"   \u23f3 Approval attempt {attempts} timed out for {bot_name}")
                except Exception as e:
                    if 'has been closed' in str(e):
                        return False
                    log(f"   \u26a0\ufe0f Approval error for {bot_name}: {str(e)[:60]}")
                await asyncio.sleep(2)
        
            # Take screenshot on failure for diagnostics
            try:
                await hp.screenshot(path=os.path.join(LOG_DIR, f"approve_fail_{bot_name}_{int(time.time())}.png"))
            except: pass
            log(f"   \u26a0\ufe0f Could not find approval button for {bot_name} within {max_wait}s")
            return False

        async def count_seated_players(hp):
            """Count seated players on host page with timeout protection."""
            try:
                return await asyncio.wait_for(hp.evaluate("""() => {
                    let c = 0;
                    const names = [];
                    document.querySelectorAll('.table-player').forEach(p => {
                        if (p.classList.contains('you-player')) {
                            c++;
                            const nm = p.querySelector('a');
                            names.push(nm ? nm.textContent.trim() : '(you)');
                            return;
                        }
                        const name = p.querySelector('a');
                        if (name && name.textContent.trim()) {
                            c++;
                            names.push(name.textContent.trim());
                        }
                    });
                    const seatBtns = document.querySelectorAll('.table-player-seat-button');
                    let visibleSeats = 0;
                    seatBtns.forEach(b => {
                        if (b.getBoundingClientRect().width > 0) visibleSeats++;
                    });
                    return {count: c, names: names, emptySeats: visibleSeats};
                }"""), timeout=8.0)
            except:
                return {'count': 0, 'names': [], 'emptySeats': -1}

        for i in range(1, NUM_BOTS):
            bot_name = BOT_PROFILES[i]["name"]

            # Health check host page before each bot join
            host_ok = await check_host_alive(host_page, game_url_global)
            if not host_ok:
                log(f"   \u26a0\ufe0f Host page unhealthy before {bot_name} \u2014 recovering...")
                try:
                    await host_page.goto(game_url_global, wait_until='domcontentloaded', timeout=20000)
                    await asyncio.sleep(2)
                    await dismiss_cookie_banner(host_page)
                    await dismiss_waiting_overlay(host_page)
                except Exception as e:
                    log(f"   \u274c Host recovery failed: {str(e)[:60]}")

            log(f"\U0001f310 Launching browser for {bot_name}...")
            bot_browser, bot_page = await make_stealth_page(pw, headless=HEADLESS, profile_id=i)
            browsers.append(bot_browser)
            pages.append(bot_page)

            log(f"\U0001f916 {bot_name} joining...")
            try:
                await asyncio.wait_for(
                    bot_page.goto(game_url_global, wait_until="domcontentloaded"),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                log(f"   \u26a0\ufe0f {bot_name}: Page load timed out \u2014 continuing anyway")
            except Exception as e:
                log(f"   \u26a0\ufe0f {bot_name}: Page load error: {str(e)[:60]}")

            await asyncio.sleep(3)
            await dismiss_cookie_banner(bot_page)
            await dismiss_waiting_overlay(bot_page)
            await dismiss_alerts(bot_page)

            # Quick recaptcha check (joining existing game rarely triggers)
            try:
                await asyncio.wait_for(
                    wait_for_recaptcha_clear(bot_page, timeout=10),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                log(f"   \u26a0\ufe0f {bot_name}: reCAPTCHA wait timed out \u2014 continuing")
            await asyncio.sleep(1)

            # Seat the bot
            await seat_at_table(bot_page, bot_name, STARTING_STACK, seat_number=i+1, is_host=False)
            await asyncio.sleep(2)

            # IMMEDIATELY approve from host page
            log(f"   \U0001f511 Approving {bot_name} from host page...")
            await approve_bot(host_page, bot_name, max_wait=25)
            await asyncio.sleep(2)

            # Reload host page after approval to ensure clean state for next bot
            # The host page often goes blank/stale after clicking Accept
            await asyncio.sleep(2)
            try:
                log(f"   \U0001f504 Reloading host page after {bot_name} approval...")
                await host_page.goto(game_url_global, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)
                await dismiss_cookie_banner(host_page)
                await dismiss_waiting_overlay(host_page)
                await dismiss_alerts(host_page)
            except Exception as e:
                log(f"   \u26a0\ufe0f Host reload failed: {str(e)[:60]}")
            
            # Verify seat count after each bot
            seat_info = await count_seated_players(host_page)
            seated_now = seat_info.get('count', 0)
            seated_names = seat_info.get('names', [])
            log(f"   \U0001f4ca After {bot_name}: {seated_now} seated ({', '.join(seated_names)})")

        # Final comprehensive approval sweep (catch any missed)
        # Reload host page to get a clean state for final sweep
        log("   \U0001f504 Reloading host for final approval sweep...")
        try:
            await host_page.goto(game_url_global, wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(3)
            await dismiss_cookie_banner(host_page)
            await dismiss_waiting_overlay(host_page)
            await dismiss_alerts(host_page)
        except Exception as e:
            log(f"   \u26a0\ufe0f Pre-sweep reload failed: {str(e)[:60]}")
        
        log("   \U0001f504 Final approval sweep...")
        for _ in range(5):
            approved = await host_approve_all(host_page)
            if not approved:
                break
            await asyncio.sleep(1.5)

        await asyncio.sleep(3)

        # Final seat count with full diagnostics
        seat_info = await count_seated_players(host_page)
        seated = seat_info.get('count', 0)
        seat_names = seat_info.get('names', [])
        empty_seats = seat_info.get('emptySeats', 0)
        log(f"   \U0001f4ca Final: Seated {seated}/{NUM_BOTS} ({', '.join(seat_names)}) | Empty seats: {empty_seats}")

        # Diagnostic: capture host page state
        try:
            host_url = host_page.url
            log(f"   \U0001f50d Host URL: {host_url}")
            await host_page.screenshot(path=os.path.join(LOG_DIR, f"pre_start_{int(time.time())}.png"))
            dom_diag = await asyncio.wait_for(host_page.evaluate("""() => {
                return {
                    title: document.title,
                    bodyClasses: document.body ? document.body.className : 'none',
                    tablePlayerCount: document.querySelectorAll('.table-player').length,
                    youPlayer: !!document.querySelector('.you-player'),
                    iframes: document.querySelectorAll('iframe').length,
                    bodyText: (document.body ? document.body.innerText : '').substring(0, 200)
                };
            }"""), timeout=5.0)
            log(f"   \U0001f50d DOM: {dom_diag}")
        except Exception as e:
            log(f"   \u26a0\ufe0f Diagnostic failed: {str(e)[:60]}")

        if seated < 2:
            log(f"\u26a0\ufe0f Only {seated} seated. Attempting recovery...")
            try:
                await host_page.reload(wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(3)
                await dismiss_cookie_banner(host_page)
                await dismiss_waiting_overlay(host_page)
                seat_info = await count_seated_players(host_page)
                seated = seat_info.get('count', 0)
                seat_names = seat_info.get('names', [])
                log(f"   \U0001f4ca After reload: {seated}/{NUM_BOTS} ({', '.join(seat_names)})")
            except Exception as e:
                log(f"   \u26a0\ufe0f Reload recovery failed: {str(e)[:60]}")
            await approve_seat_requests(host_page, [p["name"] for p in BOT_PROFILES[:NUM_BOTS]], timeout=15)

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
        log(f"\n{'='*60}\n📊 FINAL SESSION REPORT | {total} hands")
        log(f"{'─'*60}")
        log(f"   {'Bot':<12} {'Style':<8} {'Hands':>6} {'Rebuys':>7} {'Fold%':>6} {'Net Chips':>10}")
        log(f"   {'─'*12} {'─'*8} {'─'*6} {'─'*7} {'─'*6} {'─'*10}")
        for p in BOT_PROFILES[:NUM_BOTS]:
            n = p["name"]
            h = hands_played.get(n,0)
            r = rebuys_count.get(n,0)
            f = folds_count.get(n,0)
            a = actions_count.get(n,0)
            fp = f"{100*f/a:.0f}%" if a > 0 else "N/A"
            # v12: Net chip calculation
            last_stack = stack_history[n][-1][1] if stack_history[n] else 0
            initial = starting_stacks.get(n, STARTING_STACK)
            net = last_stack - initial - (r * STARTING_STACK)  # Subtract rebuy chips
            log(f"   {n:<12} {p['style']:<8} {h:>6} {r:>7} {fp:>6} {net:>+10}")
        # v12: Determine winner
        results = []
        for p in BOT_PROFILES[:NUM_BOTS]:
            n = p["name"]
            last_stack = stack_history[n][-1][1] if stack_history[n] else 0
            r = rebuys_count.get(n, 0)
            net = last_stack - starting_stacks.get(n, STARTING_STACK) - (r * STARTING_STACK)
            results.append((n, p["style"], net))
        results.sort(key=lambda x: x[2], reverse=True)
        if results:
            log(f"\n   🏆 Winner: {results[0][0]} ({results[0][1]}) with {results[0][2]:+d} chips")
            log(f"   💀 Loser:  {results[-1][0]} ({results[-1][1]}) with {results[-1][2]:+d} chips")
        # v13: Final slider stats
        try:
            from act import get_slider_stats
            ss = get_slider_stats()
            att = ss.get("attempts", 0)
            if att > 0:
                suc = ss.get("successes", 0)
                log(f"\n   🎚️ SLIDER STATS: {suc}/{att} accurate ({100*suc/att:.0f}%)")
                log(f"      Tier 1 (mouse):  {ss.get('tier1_ok',0)}")
                log(f"      Tier 2 (arrows): {ss.get('tier2_ok',0)}")
                log(f"      Tier 3 (text):   {ss.get('tier3_ok',0)}")
                log(f"      Fallback calls:  {ss.get('fallback_calls',0)}")
        except: pass
        log(f"{'='*60}")
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

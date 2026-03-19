"""
Create pokernow game with automatic reCAPTCHA audio challenge solving.
Uses Google's speech recognition to transcribe audio challenges.
"""
import asyncio
import random
import os
import time
import sys
import json
import tempfile
import urllib.request
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False
    print("WARNING: SpeechRecognition not available, can't solve audio challenges")

PROFILE_DIR = os.path.expanduser("~/Projects/poker-now-agent/.browser_profiles")
LOG_DIR = os.path.expanduser("~/Projects/poker-now-agent/logs")


async def solve_recaptcha_audio(page, max_attempts=3):
    """Try to solve reCAPTCHA v2 via audio challenge."""
    if not HAS_SR:
        return False

    for attempt in range(max_attempts):
        print(f"   🔊 Audio solve attempt {attempt+1}/{max_attempts}")

        # Find the bframe (challenge frame)
        bframe = None
        for frame in page.frames:
            furl = frame.url or ''
            if 'recaptcha' in furl and 'bframe' in furl:
                bframe = frame
                break

        if not bframe:
            print("   No reCAPTCHA bframe found")
            return False

        # Click audio button
        try:
            audio_btn = await bframe.query_selector('#recaptcha-audio-button')
            if audio_btn and await audio_btn.is_visible():
                await audio_btn.click()
                print("   Clicked audio button")
                await asyncio.sleep(3)
            else:
                # Maybe already in audio mode
                pass
        except Exception as e:
            print(f"   Audio button click error: {e}")

        # Wait for audio challenge to load
        await asyncio.sleep(2)

        # Get audio URL from the audio challenge
        audio_url = None
        try:
            audio_url = await bframe.evaluate("""() => {
                const audio = document.querySelector('#audio-source');
                return audio ? audio.src : null;
            }""")
        except Exception as e:
            print(f"   Get audio URL error: {e}")

        if not audio_url:
            print("   No audio URL found")
            await asyncio.sleep(2)
            continue

        print(f"   Audio URL: {audio_url[:80]}...")

        # Download audio
        try:
            audio_path = os.path.join(tempfile.gettempdir(), f"captcha_audio_{int(time.time())}.mp3")
            urllib.request.urlretrieve(audio_url, audio_path)
            print(f"   Downloaded audio to {audio_path}")
        except Exception as e:
            print(f"   Download error: {e}")
            continue

        # Transcribe using Google's free speech recognition
        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            print(f"   Transcribed: '{text}'")
        except sr.UnknownValueError:
            print("   Could not understand audio")
            # Try replay
            try:
                replay_btn = await bframe.query_selector('#recaptcha-reload-button')
                if replay_btn:
                    await replay_btn.click()
                    await asyncio.sleep(3)
            except: pass
            continue
        except Exception as e:
            print(f"   Transcription error: {e}")
            continue

        # Type the answer
        try:
            response_input = await bframe.query_selector('#audio-response')
            if response_input:
                await response_input.click()
                await asyncio.sleep(0.3)
                for ch in text:
                    await bframe.evaluate(f"""() => {{
                        const inp = document.querySelector('#audio-response');
                        if (inp) {{
                            inp.value += '{ch}';
                            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                    }}""")
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                print(f"   Typed answer: {text}")
            else:
                print("   No response input found")
                continue
        except Exception as e:
            print(f"   Type error: {e}")
            continue

        # Click verify
        await asyncio.sleep(0.5)
        try:
            verify_btn = await bframe.query_selector('#recaptcha-verify-button')
            if verify_btn:
                await verify_btn.click()
                print("   Clicked Verify")
                await asyncio.sleep(5)
            else:
                print("   No verify button found")
                continue
        except Exception as e:
            print(f"   Verify error: {e}")
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
            print("   ✅ reCAPTCHA solved!")
            return True
        else:
            print("   ⚠️ Still blocked after verify")
            await asyncio.sleep(2)

    return False


async def create_game_with_solver():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    pw = await async_playwright().start()
    user_data_dir = os.path.join(PROFILE_DIR, "bot_0")
    os.makedirs(user_data_dir, exist_ok=True)

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    use_chrome = os.path.exists(chrome_path)

    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir,
        headless=False,
        executable_path=chrome_path if use_chrome else None,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox',
              '--disable-infobars', '--disable-dev-shm-usage'],
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ignore_default_args=['--enable-automation'],
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await Stealth().apply_stealth_async(page)
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    # Quick Google pre-warm
    print("🌐 Pre-warming with Google...")
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(2)
        await page.mouse.move(400, 300, steps=10)
        await asyncio.sleep(1)
    except: pass

    # Visit pokernow
    print("🎰 Navigating to pokernow...")
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(3, 5))

    # Dismiss cookie
    await page.evaluate("() => { const a = document.querySelector('.alert-1-container'); if(a) a.remove(); }")
    await asyncio.sleep(1)

    # Mouse movements
    for _ in range(5):
        await page.mouse.move(random.randint(100, 1000), random.randint(100, 600), steps=random.randint(5, 15))
        await asyncio.sleep(random.uniform(0.2, 0.5))

    # Click Start a New Game
    for sel in ['a:has-text("Start a New Game")', 'a.main-ctn-game-button']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print("   Clicked: Start a New Game")
                break
        except: continue

    await asyncio.sleep(random.uniform(3, 5))

    # Fill nickname
    for sel in ['input[placeholder="Your Nickname"]', 'input[type="text"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.3)
                for ch in "Clawhi":
                    await page.keyboard.type(ch, delay=random.randint(50, 150))
                print("   Filled: Clawhi")
                break
        except: continue

    await asyncio.sleep(1)

    # Click Create Game
    for sel in ['button:has-text("Create Game")', 'button.button-1.green']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print("   Clicked: Create Game")
                break
        except: continue

    # Wait, check for reCAPTCHA, solve if needed
    print("⏳ Waiting for game creation...")
    for i in range(180):
        if "/games/" in page.url:
            game_url = page.url
            print(f"\n✅ GAME CREATED: {game_url}")
            with open("/tmp/poker_game_url.txt", "w") as f:
                f.write(game_url)
            await ctx.close(); await pw.stop()
            return game_url

        if i in (10, 30, 50, 80, 120):
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
                print(f"   reCAPTCHA challenge at {i}s — trying audio solve...")
                solved = await solve_recaptcha_audio(page)
                if solved:
                    print("   ✅ Solved! Waiting for redirect...")
                    # Re-submit form if still on start-game
                    if "/start-game" in page.url:
                        for sel in ['button:has-text("Create Game")', 'button.button-1.green']:
                            try:
                                el = await page.query_selector(sel)
                                if el and await el.is_visible():
                                    await el.click()
                                    print("   Re-submitted")
                                    break
                            except: continue
                else:
                    print(f"   ⚠️ Audio solve failed at attempt {i}s")

        await asyncio.sleep(1)

    print("❌ Timed out")
    await page.screenshot(path=os.path.join(LOG_DIR, "solver_timeout.png"))
    await ctx.close(); await pw.stop()
    return None


if __name__ == "__main__":
    url = asyncio.run(create_game_with_solver())
    if url:
        print(f"\nRun: python3 multi_bot.py --url '{url}'")
    else:
        print("\nFailed")
        sys.exit(1)

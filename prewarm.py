"""
Pre-warm browser profile for pokernow reCAPTCHA trust.
Visits the site, interacts naturally, and attempts game creation.
If reCAPTCHA challenge appears, tries audio challenge approach.
"""
import asyncio
import random
import os
import time
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROFILE_DIR = os.path.expanduser("~/Projects/poker-now-agent/.browser_profiles")
LOG_DIR = os.path.expanduser("~/Projects/poker-now-agent/logs")


async def prewarm_and_create():
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
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-infobars',
            '--disable-dev-shm-usage',
        ],
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ignore_default_args=['--enable-automation'],
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await Stealth().apply_stealth_async(page)
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    
    print("Phase 1: visiting Google first (builds reCAPTCHA trust)...")
    
    # Step 1: Visit Google first (helps reCAPTCHA trust)
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))
        search_box = await page.query_selector('textarea[name="q"], input[name="q"]')
        if search_box:
            await search_box.click()
            await asyncio.sleep(0.5)
            for ch in "poker now online free":
                await page.keyboard.type(ch, delay=random.randint(30, 120))
            await asyncio.sleep(1)
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(3, 5))
            # Click first result or just browse
            await page.mouse.wheel(0, random.randint(200, 400))
            await asyncio.sleep(2)
    except Exception as e:
        print(f"   Google pre-warm: {e}")
    
    # Step 2: Visit pokernow.club
    print("Phase 2: visiting pokernow.club...")
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(3, 5))
    
    # Dismiss cookie banner
    await page.evaluate("""() => {
        const alert = document.querySelector('.alert-1-container');
        if (alert) alert.remove();
    }""")
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
    
    # Mouse movements + scrolling
    print("Phase 3: simulating human browsing...")
    for _ in range(random.randint(5, 10)):
        x = random.randint(100, 1100)
        y = random.randint(100, 600)
        await page.mouse.move(x, y, steps=random.randint(8, 20))
        await asyncio.sleep(random.uniform(0.2, 0.8))
    await page.mouse.wheel(0, random.randint(200, 500))
    await asyncio.sleep(random.uniform(1, 3))
    await page.mouse.wheel(0, random.randint(-500, -200))
    await asyncio.sleep(random.uniform(2, 4))
    
    # Now try to create game
    print("Phase 4: creating game...")
    create_clicked = False
    for sel in ['a:has-text("Start a New Game")', 'a.main-ctn-game-button']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                box = await el.bounding_box()
                if box:
                    await page.mouse.move(
                        box['x'] + box['width']/2 + random.randint(-3, 3),
                        box['y'] + box['height']/2 + random.randint(-2, 2),
                        steps=random.randint(10, 25))
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                await el.click()
                create_clicked = True
                print("   Clicked: Start a New Game")
                break
        except: continue
    
    if not create_clicked:
        print("   No create button found")
        await page.screenshot(path=os.path.join(LOG_DIR, "prewarm_fail.png"))
        await ctx.close(); await pw.stop()
        return None
    
    await asyncio.sleep(random.uniform(3, 5))
    
    # Mouse movement on start-game page
    for _ in range(4):
        await page.mouse.move(random.randint(200, 800), random.randint(200, 600),
                              steps=random.randint(5, 15))
        await asyncio.sleep(random.uniform(0.3, 0.6))
    
    # Fill nickname char by char
    for sel in ['input[placeholder="Your Nickname"]', 'input[placeholder*="ick"]', 'input[type="text"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.5)
                for ch in "Clawhi":
                    await page.keyboard.type(ch, delay=random.randint(50, 150))
                print("   Filled nickname: Clawhi")
                break
        except: continue
    
    await asyncio.sleep(random.uniform(1, 2))
    
    # Click Create Game
    for sel in ['button:has-text("Create Game")', 'button.button-1.green']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                box = await el.bounding_box()
                if box:
                    await page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2,
                                          steps=random.randint(8, 15))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                await el.click()
                print("   Clicked: Create Game")
                break
        except: continue
    
    # Wait for redirect or reCAPTCHA
    print("Waiting for game creation (up to 180s)...")
    for i in range(180):
        if "/games/" in page.url:
            game_url = page.url
            print(f"Game created: {game_url}")
            with open("/tmp/poker_game_url.txt", "w") as f:
                f.write(game_url)
            await ctx.close(); await pw.stop()
            return game_url
        
        if i in (15, 45, 90):
            # Check for challenge
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
                print(f"   reCAPTCHA challenge at {i}s — screenshotting...")
                await page.screenshot(path=os.path.join(LOG_DIR, f"captcha_pw_{int(time.time())}.png"))
                
                # Try audio challenge
                for frame in page.frames:
                    furl = frame.url or ''
                    if 'recaptcha' in furl and 'bframe' in furl:
                        try:
                            audio_btn = await frame.query_selector('#recaptcha-audio-button')
                            if audio_btn and await audio_btn.is_visible():
                                await audio_btn.click()
                                print("   Clicked audio challenge button")
                                await asyncio.sleep(5)
                                await page.screenshot(path=os.path.join(LOG_DIR, f"captcha_audio_{int(time.time())}.png"))
                        except Exception as e:
                            print(f"   Audio error: {e}")
        
        await asyncio.sleep(1)
    
    print("Game creation timed out")
    await page.screenshot(path=os.path.join(LOG_DIR, f"prewarm_timeout.png"))
    await ctx.close(); await pw.stop()
    return None


if __name__ == "__main__":
    url = asyncio.run(prewarm_and_create())
    if url:
        print(f"\nUse: python3 multi_bot.py --url '{url}'")
    else:
        print("\nFailed to create game")
        sys.exit(1)

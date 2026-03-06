"""
Diagnostic script: Launch pokernow.club, create a game, and capture DOM at each seating step.
Purpose: Identify exact selectors for the join/seat flow.
"""
import asyncio
import time
import json
import os
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = "/tmp/poker_diag"

async def dump_dom(page, label):
    """Save screenshot + relevant DOM HTML to files."""
    ts = int(time.time())
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    await page.screenshot(path=f"{SCREENSHOTS_DIR}/{label}_{ts}.png")
    
    html = await page.evaluate("""() => {
        const results = {};
        results.buttons = [];
        document.querySelectorAll('button, a, input[type="submit"]').forEach(el => {
            const rect = el.getBoundingClientRect();
            const vis = rect.width > 0 && rect.height > 0;
            if (vis || el.offsetParent !== null) {
                results.buttons.push({
                    tag: el.tagName,
                    text: el.textContent?.trim()?.substring(0, 80),
                    classes: el.className,
                    id: el.id,
                    href: el.href || null,
                    visible: vis
                });
            }
        });
        results.inputs = [];
        document.querySelectorAll('input, textarea').forEach(el => {
            results.inputs.push({
                type: el.type, placeholder: el.placeholder, name: el.name,
                classes: el.className, id: el.id, value: el.value,
                visible: el.offsetParent !== null
            });
        });
        results.seats = [];
        document.querySelectorAll('[class*="table-player"], [class*="seat"]').forEach(el => {
            results.seats.push({
                classes: el.className,
                text: el.textContent?.trim()?.substring(0, 120),
                innerHTML: el.innerHTML?.substring(0, 500)
            });
        });
        results.alerts = [];
        document.querySelectorAll('[class*="alert"], [class*="modal"], [class*="dialog"], [class*="popup"], [class*="overlay"]').forEach(el => {
            results.alerts.push({
                classes: el.className,
                text: el.textContent?.trim()?.substring(0, 200),
                visible: el.offsetParent !== null
            });
        });
        results.url = window.location.href;
        results.bodyClasses = document.body?.className || '';
        // Get full page outer HTML (first 50k chars) for deep inspection
        results.fullHTML = document.documentElement.outerHTML?.substring(0, 50000);
        return results;
    }""")
    
    with open(f"{SCREENSHOTS_DIR}/{label}_{ts}.json", "w") as f:
        json.dump(html, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"STEP: {label} | URL: {html.get('url','?')}")
    print(f"Visible Buttons ({len([b for b in html.get('buttons',[]) if b.get('visible')])}):")
    for b in html.get('buttons', []):
        if b.get('visible') and b.get('text'):
            print(f"  [{b['tag']}] '{b['text'][:60]}' class='{str(b.get('classes',''))[:60]}'")
    print(f"Visible Inputs:")
    for inp in html.get('inputs', []):
        if inp.get('visible'):
            print(f"  type={inp['type']} ph='{inp.get('placeholder','')}' class='{str(inp.get('classes',''))[:40]}'")
    print(f"Seat elements ({len(html.get('seats', []))}):")
    for s in html.get('seats', []):
        print(f"  class='{s['classes'][:80]}' text='{s['text'][:80]}'")
    print(f"Alerts ({len([a for a in html.get('alerts',[]) if a.get('visible')])}):")
    for a in html.get('alerts', []):
        if a.get('visible'):
            print(f"  '{a['classes'][:60]}' text='{a['text'][:80]}'")
    print(f"{'='*60}\n")
    return html


async def main():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    print("🔍 Poker Now Seating Flow Diagnostic\n")
    
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    
    # Step 1: Homepage
    await page.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)
    await dump_dom(page, "01_homepage")
    
    # Dismiss banners
    await page.evaluate("document.querySelector('.alert-1-container')?.remove()")
    await asyncio.sleep(0.5)
    for sel in ["button:has-text('Got it')", "button:has-text('Accept')", "button:has-text('I agree')", "button:has-text('OK')"]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.5)
        except: pass
    
    await dump_dom(page, "02_after_dismiss")
    
    # Step 2: Click create game
    for sel in ['a:has-text("START A NEW GAME")', 'a:has-text("New Quick Game")', 'a:has-text("Create")',
                'button:has-text("Create")', 'a[href*="create"]', 'a[href*="start"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Created via: {sel}")
                await asyncio.sleep(4)
                break
        except: continue
    
    # Also try all links
    if "/create" not in page.url and "/games/" not in page.url:
        links = await page.query_selector_all('a')
        for link in links:
            try:
                text = (await link.text_content() or '').strip().lower()
                href = (await link.get_attribute('href') or '')
                if 'new' in text or 'start' in text or 'create' in text or 'create' in href:
                    print(f"  Found link: '{text}' href='{href}'")
                    await link.click()
                    await asyncio.sleep(4)
                    break
            except: continue
    
    await dump_dom(page, "03_create_page")
    
    # Step 3: Fill name if prompted
    for sel in ['input[placeholder*="name"]', 'input[placeholder*="Name"]', 'input[placeholder*="nick"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill("HostBot")
                print(f"  Filled name")
                break
        except: continue
    
    # Submit
    for sel in ['button:has-text("Create")', 'button:has-text("Start")', 'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Submitted: {sel}")
                await asyncio.sleep(5)
                break
        except: continue
    
    # Wait for game URL
    game_url = None
    for _ in range(20):
        if "/games/" in page.url:
            game_url = page.url
            break
        await asyncio.sleep(1)
    
    if not game_url:
        print("❌ Failed to create game")
        await dump_dom(page, "03b_stuck")
        await browser.close()
        await pw.stop()
        return
    
    print(f"\n✅ Game URL: {game_url}\n")
    await asyncio.sleep(3)
    
    # Step 4: Dismiss alerts on game page
    await page.evaluate("document.querySelector('.alert-1-container')?.remove()")
    await asyncio.sleep(1)
    for sel in ["button:has-text('Got it')", "button:has-text('OK')", "button:has-text('Confirm')"]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.5)
        except: pass
    
    await dump_dom(page, "04_game_page_host")
    
    # Step 5: Host sits down - capture exact selectors
    print("HOST SEATING:")
    # Try clicking on empty seat area
    for sel in ['.table-player-seat-button', 'button:has-text("Take the Seat")',
                'button:has-text("Take a Seat")', 'button:has-text("Sit")',
                '.table-player.empty-seat', '.empty-seat-button',
                '[class*="seat-button"]', '.table-player-empty']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.click()
                    print(f"  Clicked seat: {sel}")
                    await asyncio.sleep(2)
                    break
        except: continue
    
    await dump_dom(page, "05_after_seat_click")
    
    # Look for stack/buy-in input
    for sel in ['input[type="number"]', 'input[placeholder*="stack"]', 'input[placeholder*="Stack"]',
                'input[placeholder*="buy"]', 'input[placeholder*="Buy"]', 'input[placeholder*="chip"]',
                'input.stack-input', 'input[type="text"]']:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    ph = await el.get_attribute('placeholder') or ''
                    val = await el.get_attribute('value') or ''
                    cls = await el.get_attribute('class') or ''
                    print(f"  Found input: ph='{ph}' val='{val}' class='{cls}'")
                    await el.fill("1000")
                    await asyncio.sleep(0.5)
                    break
        except: continue
    
    # Confirm
    for sel in ['button:has-text("Confirm")', 'button:has-text("OK")', 'button:has-text("Sit Down")',
                'button:has-text("Buy")', 'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Confirmed: {sel}")
                await asyncio.sleep(2)
                break
        except: continue
    
    await dump_dom(page, "06_host_seated")
    
    # Step 6: Bot joins
    print("\nBOT JOINING:")
    bot_browser = await pw.chromium.launch(headless=False)
    bot_ctx = await bot_browser.new_context(viewport={"width": 1280, "height": 800})
    bot_page = await bot_ctx.new_page()
    bot_page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    
    await bot_page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)
    
    await bot_page.evaluate("document.querySelector('.alert-1-container')?.remove()")
    await asyncio.sleep(1)
    for sel in ["button:has-text('Got it')", "button:has-text('OK')", "button:has-text('Accept')"]:
        try:
            el = await bot_page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.5)
        except: pass
    
    await dump_dom(bot_page, "07_bot_arrived")
    
    # Bot enters name
    for sel in ['input[placeholder*="name"]', 'input[placeholder*="Name"]', 'input[placeholder*="nick"]', 'input[type="text"]']:
        try:
            els = await bot_page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.fill("TestBot")
                    print(f"  Bot name filled: {sel}")
                    break
        except: continue
    
    # Submit join
    for sel in ['button:has-text("Join")', 'button:has-text("Enter")', 'button:has-text("Play")',
                'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await bot_page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Bot join clicked: {sel}")
                await asyncio.sleep(4)
                break
        except: continue
    
    await bot_page.evaluate("document.querySelector('.alert-1-container')?.remove()")
    await asyncio.sleep(1)
    await dump_dom(bot_page, "08_bot_in_game")
    
    # Bot clicks empty seat
    for sel in ['.table-player-seat-button', 'button:has-text("Sit")', '.table-player.empty-seat',
                '.empty-seat-button', '[class*="seat-button"]', '.table-player-empty',
                'button:has-text("Take")']:
        try:
            els = await bot_page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.click()
                    print(f"  Bot clicked seat: {sel}")
                    await asyncio.sleep(2)
                    break
        except: continue
    
    await dump_dom(bot_page, "09_bot_seat_clicked")
    
    # Bot fills stack
    for sel in ['input[type="number"]', 'input[placeholder*="stack"]', 'input[placeholder*="Stack"]',
                'input[placeholder*="buy"]', 'input.stack-input', 'input[type="text"]']:
        try:
            els = await bot_page.query_selector_all(sel)
            for el in els:
                if await el.is_visible():
                    await el.fill("1000")
                    print(f"  Bot stack filled")
                    await asyncio.sleep(0.5)
                    break
        except: continue
    
    # Confirm
    for sel in ['button:has-text("Confirm")', 'button:has-text("OK")', 'button:has-text("Sit Down")',
                'button:has-text("Buy")', 'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await bot_page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Bot confirmed seat: {sel}")
                await asyncio.sleep(2)
                break
        except: continue
    
    await dump_dom(bot_page, "10_bot_seated")
    await dump_dom(page, "11_host_after_bot_seated")
    
    # Try starting the game from host
    print("\nSTARTING GAME:")
    for sel in ['button:has-text("Start")', 'button:has-text("Start Game")', 'button:has-text("Deal")',
                '.start-game', 'button:has-text("Begin")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Started game: {sel}")
                await asyncio.sleep(3)
                break
        except: continue
    
    await dump_dom(page, "12_game_started_host")
    await dump_dom(bot_page, "13_game_started_bot")
    
    print("\n🔍 Diagnostic complete. Keeping browsers open for 20s...")
    await asyncio.sleep(20)
    
    await bot_browser.close()
    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(main())

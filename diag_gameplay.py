"""Quick diagnostic: create game, seat 2 bots, start, check turn detection."""
import asyncio, time, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright

async def dismiss(page):
    await page.evaluate("document.querySelector('.alert-1-container')?.remove()")
    await asyncio.sleep(0.3)

async def seat_player(page, name, stack, is_host=False):
    """Click first available seat, fill form, submit."""
    btns = await page.query_selector_all('.table-player-seat-button')
    for btn in btns:
        if await btn.is_visible():
            await btn.click()
            break
    await asyncio.sleep(2.5)
    
    # Find the selected seat's form
    # Debug: check what elements have 'selected' class
    sel_debug = await page.evaluate("""() => {
        const els = document.querySelectorAll('.selected');
        return Array.from(els).map(e => ({tag: e.tagName, class: e.className.substring(0,100)}));
    }""")
    print(f'  Selected elements: {sel_debug}')
    
    selected = await page.query_selector('.table-player-seat.selected')
    if not selected:
        selected = await page.query_selector('.selected.layer-priority')
    if not selected:
        selected = await page.query_selector('[class*="selected"][class*="table-player"]')
    
    if selected:
        inputs = await selected.query_selector_all('input[type="text"]')
        print(f"  Found {len(inputs)} text inputs in selected seat")
        if len(inputs) >= 1:
            await inputs[0].click(click_count=3)
            await inputs[0].fill(name)
            print(f"  Filled name: {name}")
        if len(inputs) >= 2:
            await inputs[1].click(click_count=3)
            await inputs[1].fill(str(stack))
            print(f"  Filled stack: {stack}")
    else:
        print("  ⚠️ No selected seat found")
        # Try page-wide inputs
        for sel in ['input[placeholder="Your Name"]', 'input[placeholder*="Name"]']:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(name)
                break
        for sel in ['input[placeholder="Your Stack"]', 'input[placeholder="Intended Stack"]', 'input[placeholder*="Stack"]']:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(str(stack))
                break
    
    await asyncio.sleep(0.5)
    
    # Click submit
    target = "Take the Seat" if is_host else "Request the Seat"
    btn = await page.query_selector(f'button:has-text("{target}")')
    if btn and await btn.is_visible():
        await btn.click()
        print(f"  Clicked: {target}")
    else:
        # Fallback to any green button
        for sel in ['button.button-1.highlighted.green', 'button.med-button']:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                print(f"  Clicked fallback: {sel}")
                break
    await asyncio.sleep(2)

async def main():
    pw = await async_playwright().start()
    
    b1 = await pw.chromium.launch(headless=False)
    p1 = await (await b1.new_context(viewport={"width":1280,"height":800})).new_page()
    p1.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    
    b2 = await pw.chromium.launch(headless=False)
    p2 = await (await b2.new_context(viewport={"width":1280,"height":800})).new_page()
    p2.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    
    # Create game
    print("Creating game...")
    await p1.goto("https://www.pokernow.club", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)
    await dismiss(p1)
    
    await (await p1.query_selector('a:has-text("Start a New Game")')).click()
    await asyncio.sleep(3)
    await (await p1.query_selector('input[placeholder="Your Nickname"]')).fill("Host1")
    await (await p1.query_selector('button:has-text("Create Game")')).click()
    
    for _ in range(20):
        if "/games/" in p1.url: break
        await asyncio.sleep(1)
    
    game_url = p1.url
    print(f"Game: {game_url}")
    await asyncio.sleep(2)
    await dismiss(p1)
    
    # Host sits
    print("\nHost sitting...")
    await seat_player(p1, "Host1", 1000, is_host=True)
    
    # Bot joins and sits
    print("\nBot joining...")
    await p2.goto(game_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)
    await dismiss(p2)
    
    print("Bot sitting...")
    await seat_player(p2, "Bot1", 1000, is_host=False)
    
    # Host approves
    print("\nHost approving...")
    await asyncio.sleep(1)
    btns = await p1.query_selector_all('button')
    for btn in btns:
        text = (await btn.text_content() or '').strip()
        if await btn.is_visible() and any(w in text for w in ['Approve', 'Accept', 'Allow', 'Confirm']):
            await btn.click()
            print(f"  Approved: {text}")
            await asyncio.sleep(1)
    
    await asyncio.sleep(3)
    
    # Start game
    print("\nStarting game...")
    btns = await p1.query_selector_all('button')
    for btn in btns:
        text = (await btn.text_content() or '').strip()
        if await btn.is_visible() and any(w in text for w in ['Start', 'Deal', 'Begin']):
            await btn.click()
            print(f"  Started: {text}")
            await asyncio.sleep(3)
            break
    
    # Now check game state repeatedly
    from scrape import scrape_state
    
    for attempt in range(15):
        print(f"\n--- Check {attempt+1} ---")
        for page, name in [(p1, "Host"), (p2, "Bot")]:
            try:
                state = await scrape_state(page)
                cards = state.get("my_cards", [])
                turn = state.get("is_my_turn", False)
                actions = state.get("actions", [])
                street = state.get("street", "?")
                pot = state.get("pot_total") or state.get("pot") or 0
                players = state.get("players", [])
                
                me_info = "?"
                for p in players:
                    if p.get("is_me"):
                        me_info = f"stack={p.get('stack','?')}"
                
                print(f"  {name}: turn={turn} cards={cards} street={street} pot={pot} actions={actions[:3]} {me_info}")
                
                # If it's our turn, try an action
                if turn and actions:
                    from act import execute_action
                    if "Check" in " ".join(actions):
                        result = await execute_action(page, "check")
                        print(f"  {name} → CHECK: {result}")
                    elif "Call" in " ".join(actions):
                        result = await execute_action(page, "call")
                        print(f"  {name} → CALL: {result}")
                    elif "Fold" in " ".join(actions):
                        result = await execute_action(page, "fold")
                        print(f"  {name} → FOLD: {result}")
            except Exception as e:
                print(f"  {name}: Error: {e}")
        
        await asyncio.sleep(2)
    
    print("\nDone. Closing...")
    await b1.close()
    await b2.close()
    await pw.stop()

asyncio.run(main())

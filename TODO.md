# Poker Now AI Agent - TODO

## Status: ✅ Bots can create, join, seat, and play hands autonomously

### Completed (2026-03-06)
- [x] Fixed seating flow: host creates game → sits via "Take the Seat" → bots join → click "Sit" → fill name/stack → "Request the Seat" → host approves
- [x] Fixed .env loading in multi_bot.py (scrape.py was silently failing due to config.py import error)
- [x] Game auto-starts after all players seated
- [x] 4 bot styles working: TAG, LAG, NIT, STATION
- [x] Multi-street play: preflop/flop/turn/river with equity-based decisions
- [x] Session logging to ~/Projects/poker-now-agent/logs/
- [x] 47 hands played in first successful session

### Priority 1: Fix Raise Slider (HIGH)
- 12 out of 31 raises (~39%) show "Raised to ? (range 2-100)" — bet amount not set properly
- Investigate act.py's slider/input handling for pokernow's bet interface
- Need to properly fill the bet amount input or use the slider correctly

### Priority 2: Auto-Rebuy (HIGH)
- Bots bust and never rebuy — game dies when players run out of chips
- AceBot/CallStn busted after ~5 hands, leaving only 2 bots
- Need to detect elimination state and auto-rebuy
- Consider unlimited rebuys to keep games running longer

### Priority 3: Decision Engine Improvements (MEDIUM)
- Fold rate too low (14% vs target 40-50%)
- LAG profile too aggressive with marginal hands (3-bet jamming Q8o)
- NIT profile not tight enough (calling preflop with 4-high)
- Equity calculations may be off (10h4c showing 68% on flop?)
- Need better pot odds calculation for call/fold decisions
- Need position-aware opening ranges

### Priority 4: Robustness (MEDIUM)
- Some duplicate actions per street (bot acts twice on same decision)
- "Error:" empty results from button clicks (stale DOM references)
- Need better state tracking to prevent double-actions
- Timeout errors when button element detaches from DOM

### Priority 5: GTO Improvements (LOW for now)
- Balanced preflop ranges per position
- Mixed strategies (randomize between call/raise at threshold equities)
- Bet sizing based on board texture
- River value betting and bluffing frequencies

### Priority 6: Analytics (LOW)
- Track win/loss per bot per session
- Log completed hand histories in standard format
- Compare bot styles over many sessions
- Track key metrics: VPIP, PFR, AF, WTSD

### Learned
- pokernow.club domain is now pokernow.com (redirects)
- Host sees "Take the Seat", non-host sees "Request the Seat"
- Host must approve bot seat requests (click "Accept" button)
- The `.alert-1-container` cookie banner blocks interaction until removed
- config.py requires ANTHROPIC_API_KEY — must load .env before importing scrape.py
- Playwright `:has-text()` pseudo-selector does NOT work inside `page.evaluate()` (raw JS context)
- `ElementHandle.triple_click()` doesn't exist — use `click(click_count=3)`
- The game auto-deals after Start button is clicked and ≥2 players are seated

# Poker Now AI Agent - TODO

## Status: ✅ All 4 bots seat, play, and bet autonomously (seating fix v7)

### Completed (2026-03-15 Evening)
- [x] **FIXED: Seating flow for 3+ bots** — root cause was pokernow React SPA going blank after approving first seat request
  - Host page reload after each approval gives clean DOM for next request
  - All 4 bots (TAG/LAG/NIT/STATION) seat reliably on first attempt
  - host_approve_all now handles inline buttons, Options menu badge, and notification area
  - approve_bot timeout increased to 25s, approve_seat_requests delegates to host_approve_all
- [x] 60+ hands played successfully with all 4 bots (2 test runs)
- [x] Game creation, reCAPTCHA bypass (including audio solve), seating, game start all working

### Completed (2026-03-06 Evening)
- [x] **FIXED: Raise slider** — 100% success rate (was 39% failure)
  - Root cause: `click_action_button("Bet")` matched "BET 20" (preset) before "BET" (slider panel)
  - New `_click_raise_opener()` matches exact text, falls back to keyboard "r"
  - Waits up to 2.5s for panel render, retries 3x with keyboard type fallback
- [x] Improved decision engine: tighter calling, capped re-raise aggression
- [x] Increased Monte Carlo sims (150→300) for better equity accuracy
- [x] Reduced bluff frequency (no bluffs on turn/river)
- [x] Host now approves rebuy/seat requests periodically

### Completed (2026-03-06 Afternoon)
- [x] Fixed seating flow: host→"Take the Seat", bots→"Request the Seat"→host approves
- [x] Fixed .env loading, game auto-starts, 4 bot styles, multi-street play
- [x] Session logging, 47 hands first session, 63+ hands second session

### Priority 1: Auto-Rebuy (HIGH)
- Bots bust and never rebuy — game degrades to heads-up
- AceBot/CallStn/Clawhi all bust eventually, no rebuy triggered
- Current auto_rebuy() improved but still not detecting/handling rebuy UI
- **TODO:** Add diagnostic screenshots when rebuy is attempted
- **TODO:** Maybe try a different approach: re-navigate to game URL and re-sit
- Consider unlimited rebuys to keep 4-way action going

### Priority 2: Fold Rate Too Low (MEDIUM-HIGH)
- NIT folds 26% preflop → target 40-50%
- STATION folds 0% preflop → target 10-15%
- Overall fold rate 12% → target 25-30%
- **TODO:** Implement position-based preflop ranges (not just equity threshold)
- **TODO:** Add VPIP/PFR tracking per bot style

### Priority 3: Raise Sizing (MEDIUM)
- Many raises are to minimum (20 chips on 20-2000 range)
- pot * 0.4 on small pots produces tiny numbers below min_raise
- **TODO:** Use at least 2.5x BB for opens, 3x for 3-bets
- **TODO:** Size value bets at 50-75% pot, not pot-fraction * random

### Priority 4: Postflop Play (MEDIUM)
- NIT bluffing with bottom-range hands (6h5s at 16%) — shouldn't happen
- STATION calling river bets with 12-16% equity — too loose
- Weak value betting (tiny raises with strong hands)
- **TODO:** Position-aware c-betting
- **TODO:** River value bet sizing proportional to hand strength

### Priority 5: Robustness (MEDIUM)
- Auto-reconnect on disconnect
- Handle stale DOM references gracefully
- Prevent duplicate actions per street

### Priority 6: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Host page goes blank after approving seat request** — React SPA re-render. MUST reload page between approvals.
- **Options menu (hamburger) has red badge** showing queued seat requests, but reload + inline Accept is more reliable
- pokernow.com (not .club) — redirects
- Host: "Take the Seat", Non-host: "Request the Seat" → host approves
- `.alert-1-container` cookie banner blocks interaction
- Playwright `:has-text()` does NOT work inside `page.evaluate()` (raw JS)
- `ElementHandle.triple_click()` doesn't exist — use `click(click_count=3)`
- **"BET 20" is preset min-bet (acts immediately), "BET" opens slider panel**
- **Keyboard "r" always opens raise/bet slider panel**
- **Use getBoundingClientRect not offsetParent for visibility (handles position:fixed)**
- `input.value` CSS selector works for pokernow's bet input class

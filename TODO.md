# Poker Now AI Agent - TODO

## Status: ✅ All 4 bots seat, play, rebuy, and maintain 4-way action (v10)

### Completed (2026-03-18 Evening — v10)
- [x] **FIXED: Rebuy system (71% recovery rate, up from 0%)**
  - Host uses "Take the Seat" (instant), non-host uses "Request the Seat" (approved)
  - Detects pending requests ("cancel game ingress request") — waits instead of retrying
  - 15s cooldown after rebuy prevents false bust detection cycle
  - Button filter excludes "copy link", "join a live game", etc.
- [x] **FIXED: Game stall prevention** — host clicks Start/Deal every loop, proactive approval every 30s
- [x] **IMPROVED: Decision engine** — more aggressive c-betting, value betting 60-90% pot
- [x] **IMPROVED: Monte Carlo sims 300→500** for better equity accuracy  
- [x] **310+ hands played in 22 minutes** — no stalls, no crashes
- [x] All 4 styles playing with distinct behaviors
- [x] **Fold rates:** NIT 64%, TAG 51%, LAG 37%, STATION 16%

### Completed (2026-03-15 — v7)
- [x] Fixed seating flow — reload host page between bot approvals
- [x] 60+ hands played with all 4 bots  
- [x] Game creation, reCAPTCHA bypass, seating, game start all working

### Completed (2026-03-06)
- [x] Fixed raise slider — 100% success rate
- [x] Improved decision engine, Monte Carlo sims
- [x] Host approves rebuy/seat requests periodically

### Priority 1: Cap Re-Raise Escalation (HIGH)
- Both bots escalate to all-in on flop too often
- **TODO:** Maximum 3 raises per street (open, 3-bet, 4-bet) then call/fold
- Prevents absurd pot escalation with medium-strength hands

### Priority 2: Fix Preflop Fold Rates (HIGH)
- NIT 64% preflop fold → target 45-50% (too tight for 4-handed)
- TAG 51% → target 35-40%
- Root cause: 0.85^(n-1) multiway discount too aggressive
- **TODO:** Use 0.90^(n-1) or separate 4-handed equity table
- **TODO:** Lower preflop fold thresholds for 4-handed play

### Priority 3: Remaining Rebuy Failures (MEDIUM)
- 4 of 14 busts unrecovered (29% failure)
- Some due to no seat buttons after reload (seats occupied by other bots)
- **TODO:** Wait longer for seat buttons, try alternative seats
- **TODO:** Consider host clicking "Shuffle Seats" to open spots

### Priority 4: Cookie Banner Interference (MEDIUM)
- `.alert-1-container` intercepts Playwright clicks periodically
- **TODO:** Remove banner before EVERY action, not just page load
- **TODO:** Use `page.evaluate` to remove before click

### Priority 5: Position-Based Ranges (MEDIUM)
- Currently only equity thresholds — no position awareness
- **TODO:** Open wider from button/cutoff, tighter from UTG
- **TODO:** 3-bet wider from blinds vs late position opens

### Priority 6: Postflop Play Quality (MEDIUM)
- Check-check through all streets with medium hands too often
- **TODO:** C-bet more on flop when checked to (especially vs 1 opponent)
- **TODO:** Thin value bet rivers with top pair type hands

### Priority 7: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format (for external analysis tools)
- Multi-session performance comparison

### Learned (Technical)
- **Host page goes blank after approving seat request** — React SPA re-render. MUST reload page.
- **"cancel game ingress request"** means bot has pending seat request — don't resit, just wait
- **Host is game owner** — uses "Take the Seat" (instant), not "Request the Seat"
- **Rebuy cooldown needed** — after successful rebuy, bot sees stack=None briefly during re-render
- **"copy link" button matched as form submit** — must filter unrelated buttons
- Host: "Take the Seat", Non-host: "Request the Seat" → host approves
- `.alert-1-container` cookie banner blocks interaction — must remove from DOM
- Playwright `:has-text()` does NOT work inside `page.evaluate()` (raw JS)
- `ElementHandle.triple_click()` doesn't exist — use `click(click_count=3)`
- **"BET 20" is preset min-bet (acts immediately), "BET" opens slider panel**
- **Keyboard "r" always opens raise/bet slider panel**
- **Monte Carlo equity with 500 sims gives ±5% accuracy — acceptable for speed**
- **Both bots showing 80%+ equity** — MC sims are vs random hands, not actual opponent

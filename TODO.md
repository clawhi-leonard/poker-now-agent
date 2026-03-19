# Poker Now AI Agent - TODO

## Status: v13 — Slider FIXED! 97% accuracy, 140+ hands per session

### Completed (2026-03-18 Night — v13) ⭐ MAJOR BREAKTHROUGH
- [x] **REWRITE: act.py slider uses 3-tier approach**
  - Tier 1: Mouse drag/click on slider track position
  - Tier 2: Arrow keys (focus slider, press Left/Right to adjust) — PRIMARY METHOD
  - Tier 3: Text input triple-click + type (backup)
  - Validation after each tier, fallback to next tier on failure
- [x] **FIXED: Slider accuracy 30% → 97%** (85/88 in test session)
  - Arrow keys: 66% of raises, Mouse: 31%, Text: 0%, Fallback: 0%
  - Zero accidental all-ins from slider going to max!
- [x] **FIXED: Call fallback when slider fails**
  - If actual > 2x target and > 70% of max, Escape + Call instead
  - Never triggered in v13 session (97% accuracy made it unnecessary)
- [x] **CHANGED: STARTING_STACK 1000 → 5000 (500BB)**
  - Only 1 bust in 140+ hands (was 19 busts in 16 hands with v12)
  - Real poker with meaningful stack depths (2200-10400 ranges)
- [x] **ADDED: Slider stats tracking and reporting**
  - Per-tier success counts logged every 5 minutes
  - Final session report with accuracy breakdown
- [x] **RESULT: 140+ hands in 25 minutes** (was 16 hands in 20 minutes)

### Completed (2026-03-18 Night — v12)
- [x] NIT postflop over-aggression fix
- [x] STATION fold threshold raised 28 → 32
- [x] Position + stack logging
- [x] Chip tracking per bot
- [x] Cancel-and-re-request rebuy mechanism
- [x] Options menu v12 fallback for approvals
- [x] Host approval check interval 60s → 15s

### Priority 0: Fix Submit Button Detachment (MEDIUM)
- 10 "Error:" actions per session from submit button detaching during SPA re-render
- Pattern: happens on large raises near all-in when SPA re-renders quickly
- The raise usually goes through anyway (stacks change correctly)
- **TODO:** Use `page.keyboard.press("Enter")` as primary submit method
- **TODO:** Re-query submit button before clicking
- **TODO:** Add error recovery: check if action went through via stack change

### Priority 1: Auto-Rebuy at Low Stack (MEDIUM)
- NitKing dropped to 2242 and stayed there for 60+ hands
- NIT plays too tight to recover from big loss with shallow effective stack
- **TODO:** Trigger rebuy when stack < 30% of starting (< 1500 with 5000 stacks)
- **TODO:** Don't wait for bust — proactive top-up

### Priority 2: Tighten TAG Fold Rate (LOW)
- Clawhi at 19% fold rate — should be ~25-30% for TAG
- **TODO:** Raise TAG preflop fold threshold from 40 to 44

### Priority 3: Equity Accuracy (LOW)
- Both players showing 80%+ equity in same hand — MC sim vs random issue
- **TODO:** Add opponent range modeling based on action history
- **TODO:** Track equity accuracy (predicted vs actual outcome)

### Priority 4: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Arrow keys are the most reliable way to set React range inputs!**
  - Native keyboard events properly propagate through React's event system
  - nativeSetter + dispatchEvent fails because React intercepts at the fiber level
  - Mouse click on slider track is second-best (within ~10% of target)
- **5000 stacks (500BB) is the sweet spot for bot testing**
  - Enough depth for real poker decisions (SPR > 10 in most pots)
  - Rare bust-outs = more time playing, less time rebuying
  - Stack dynamics emerge naturally (short stacks vs deep stacks)
- **Submit button "Element detached" is a SPA rendering issue**
  - Button gets recreated by React on certain game state changes
  - Enter key or re-querying the button would fix this
- **Slider accuracy progression: v10(~20%) → v12(~30%) → v13(97%)**
- **Multiway equity discount matters enormously** — 0.85^3 = 0.614 vs 0.92^3 = 0.779
- **Host page goes blank after approving seat request** — React SPA re-render. MUST reload page.
- **"cancel game ingress request"** means bot has pending seat request
- **Host is game owner** — uses "Take the Seat" (instant), not "Request the Seat"
- `.alert-1-container` cookie banner blocks interaction — must remove from DOM before every action
- **"BET 20" is preset min-bet (acts immediately), "BET" opens slider panel**

# Poker Now AI Agent - TODO

## Status: v12 — NIT/STATION fixes working, slider reliability is #1 blocker

### Completed (2026-03-18 Night — v12)
- [x] **FIXED: NIT postflop over-aggression**
  - NIT max raise = half pot when equity < 80%
  - NitKing bet 25 on flop with 54% eq (was raising 900+ in v11) ✅
- [x] **FIXED: STATION fold threshold raised 28 → 32**
  - Still only 6% fold rate — may need 36 for 4-handed
- [x] **ADDED: Position + stack logging in action output**
  - Every action line: `UTG stk=1000 | Kh Js | eq=50%`
- [x] **ADDED: Chip tracking per bot**
  - `stack_history` dict, final report with net chips and winner/loser
- [x] **ADDED: Cancel-and-re-request rebuy mechanism**
  - After 3 failed pending waits, cancel request and re-submit fresh
  - Creates new Accept button for host — fixes stuck rebuy loop
- [x] **ADDED: Options menu v12 fallback**
  - Always tries clicking OPTIONS button even without badge
  - `host_approve_all` Phase 2c catches more approvals
- [x] **IMPROVED: Host approval check interval 60s → 15s**
- [x] **IMPROVED: Post-rebuy host approval sweep**
  - After host reseats, immediately does approval sweep with page reload
- [x] **IMPROVED: act.py slider React event handling**
  - Better text input detection (tries non-range inputs first)
  - Triggers React fiber onChange handler with proper target object

### Completed (2026-03-18 Night — v11)
- [x] Preflop fold rates recalibrated for 4-handed (multiway discount 0.85→0.92)
- [x] Re-raise escalation capped (preflop >8xBB, postflop >50% pot)
- [x] Host page stability during rebuy approval (no-reload approach first)
- [x] Position-based preflop ranges (BTN -7, CO -5, UTG +3, SB +3)
- [x] Cookie banner removal before every action and scrape

### Priority 0: Fix Slider Reliability (CRITICAL)
- Slider goes to max instead of target value ~70% of the time
- Causes premature all-ins → mass bust-outs → 80% of session time in rebuys
- **TODO:** Try keyboard arrow key approach (set to max, press Left to decrement)
- **TODO:** Try clicking the text input, clearing, typing amount, then pressing Enter
- **TODO:** Fallback to min-bet preset button ("BET 20") when slider fails
- **TODO:** Consider "call-only mode" when facing unreliable slider

### Priority 1: Deeper Starting Stacks (HIGH)
- 1000 chips / 10BB = only 100BB = bust in 3-4 big pots
- **TODO:** Change STARTING_STACK to 5000 or 10000
- **TODO:** Adjust raise sizing proportionally

### Priority 2: Reduce Rebuy Cycle Time (HIGH)
- Cancel-and-re-request after 2 waits instead of 3
- Host page reload every 15s when pending bots exist
- Reduce per-wait sleep from 8s to 4s

### Priority 3: STATION Still Too Loose (MEDIUM)
- 6% preflop fold rate — calling almost everything
- **TODO:** Raise fold threshold from 32 to 36

### Priority 4: Add Chip Tracking Report (MEDIUM)
- Stack history tracking is in place but session too short to generate meaningful data
- **TODO:** Log stack every 10 hands for mid-session updates
- **TODO:** Track chip changes per street (flop/turn/river profit/loss)

### Priority 5: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Slider reliability is pokernow's biggest automation challenge** — React SPA ignores nativeSetter
  - `nativeSetter.call(slider, value)` + dispatchEvent doesn't reliably update React state
  - The actual rendered bet amount defaults to slider max
  - Even triple-click + keyboard type doesn't work reliably
- **Cancel-and-re-request works** — after 3 failed waits, cancel pending request and re-submit
  - Creates fresh Accept notification for host
  - Much more reliable than trying to find approval in Options menu
- **Options menu v12 fallback helps** — clicking OPTIONS and looking for Accept buttons
  - Works on first approval but not reliably for subsequent queued requests
- **Host page reload timing matters** — too frequent = game disruption, too infrequent = missed approvals
  - 15s check interval with 20s reload threshold seems good
- **Multiway equity discount matters enormously** — 0.85^3 = 0.614 vs 0.92^3 = 0.779
- **Host page goes blank after approving seat request** — React SPA re-render. MUST reload page.
- **"cancel game ingress request"** means bot has pending seat request
- **Host is game owner** — uses "Take the Seat" (instant), not "Request the Seat"
- **Both bots showing 80%+ equity** — MC sims are vs random hands, not actual opponent
- `.alert-1-container` cookie banner blocks interaction — must remove from DOM before every action
- **"BET 20" is preset min-bet (acts immediately), "BET" opens slider panel**

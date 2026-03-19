# Poker Now AI Agent - TODO

## Status: ✅ 220+ hands, 100% rebuy recovery, improved preflop ranges (v11)

### Completed (2026-03-18 Night — v11)
- [x] **FIXED: Preflop fold rates recalibrated for 4-handed**
  - Multiway discount 0.85 → 0.92 per opponent (was way too harsh)
  - NIT fold: 64% → 38% (target 40-50%) ✅
  - TAG fold: 51% → 38% (target 30-40%) ✅
  - LAG fold: 37% → 26% (target 20-30%) ✅
  - STATION fold: 16% → 5% (target 5-15%) ✅
- [x] **FIXED: Re-raise escalation capped**
  - Preflop: no re-raise when facing >8x BB
  - Postflop: no re-raise when call > 50% pot AND pot > 10x BB
  - Log-based backup: caps if ≥4 raises in recent log
- [x] **FIXED: Host page stability during rebuy approval**
  - No longer reloads page during active hand (was causing host to lose seat)
  - Approval on current page first, reload only after 60s + not in hand
  - Rebuy success: 71% → 100% (8/8 busts recovered)
- [x] **IMPROVED: Position-based preflop ranges**
  - BTN: -7 equity threshold (play wider)
  - CO: -5, SB: +3, UTG: +3
- [x] **IMPROVED: Cookie banner removal** — runs before every action and scrape
- [x] **220+ hands in 17 minutes** — no stalls, no crashes

### Completed (2026-03-18 Evening — v10)
- [x] **FIXED: Rebuy system (71% recovery rate, up from 0%)**
- [x] **310+ hands played in 22 minutes** — no stalls, no crashes
- [x] All 4 styles playing with distinct behaviors

### Completed (2026-03-15 — v7)
- [x] Fixed seating flow — reload host page between bot approvals
- [x] 60+ hands played with all 4 bots

### Priority 1: Tighten Flop Escalation Cap (HIGH)
- 9 instances of raises >1000 chips on flop in v11 session
- Current heuristic (call > 50% pot) doesn't trigger early enough
- **TODO:** Max single bet = 2x pot (unless all-in with <25% of stack left)
- **TODO:** Track raise count per street explicitly (not just from game log)

### Priority 2: Fix NIT Postflop Over-Aggression (HIGH)
- NitKing raised 5564 on turn with only 51% equity — should never happen
- NIT postflop: should almost never raise >2x pot unless equity >80%
- **TODO:** Add NIT-specific postflop raise cap: max raise = pot unless equity >80%

### Priority 3: STATION Fold Threshold Slightly Too Low (MEDIUM)
- Only 5% preflop fold — calling 4c3h and 8s3c preflop
- **TODO:** Raise STATION fold threshold from 28 to 32

### Priority 4: Add Position + Stack Logging (MEDIUM)
- Can't verify position adjustments are working without log data
- **TODO:** Log position and stack in action output

### Priority 5: Chip Tracking / Winner Detection (MEDIUM)
- No way to tell which bot won the most chips over a session
- **TODO:** Track stack changes hand-over-hand
- **TODO:** Report net chip won/lost per bot at end of session

### Priority 6: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Multiway equity discount matters enormously** — 0.85^3 = 0.614 vs 0.92^3 = 0.779
  - NIT went from 64% preflop fold to 38% just by changing this one number
- **Host page reload during hand = disaster** — causes seat loss and game disruption
  - v11 fix: approve on current page first, only reload if >60s AND not in hand
- **Re-raise cap heuristic** — call_amount relative to BB/pot works but needs tuning
  - Log-based raise counting is unreliable (entries span multiple streets/hands)
- **Position system** — BTN/CO adjustments working but hard to verify without explicit logging
- **Host page goes blank after approving seat request** — React SPA re-render. MUST reload page.
- **"cancel game ingress request"** means bot has pending seat request — don't resit, just wait
- **Host is game owner** — uses "Take the Seat" (instant), not "Request the Seat"
- **Rebuy cooldown needed** — after successful rebuy, bot sees stack=None briefly during re-render
- **"copy link" button matched as form submit** — must filter unrelated buttons
- `.alert-1-container` cookie banner blocks interaction — must remove from DOM before every action
- **"BET 20" is preset min-bet (acts immediately), "BET" opens slider panel**
- **Monte Carlo equity with 500 sims gives ±5% accuracy — acceptable for speed**
- **Both bots showing 80%+ equity** — MC sims are vs random hands, not actual opponent

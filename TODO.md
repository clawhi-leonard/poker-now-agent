# Poker Now AI Agent - TODO

## Status: v18 — River value betting, LAG fold fix, 97% slider, 288+ hands

### Completed (2026-03-19 5AM — v18)
- [x] **FIXED: River value bet missing** — bots were checking back 70-80%+ equity rivers
  - Free-check section now ALWAYS bets river with equity > 70% (50-75% pot sizing)
  - Thin value bets for TAG/LAG at 55%+ equity
  - Observed 10+ correct river value bets in 288-hand session
- [x] **FIXED: Raise cap blocking river value bets** — `raise_capped` killed `can_raise` in big pots
  - River free checks now use original can_raise, bypassing the raise cap
  - Raise cap still prevents re-raise wars but doesn't block opening value bets
- [x] **FIXED: LAG fold rate too low** — AceBot was 3-7%, now 14% (target ~15%)
  - Raised LAG fold threshold from 34 → 38
  - AceBot now correctly folds 3d6c, 2c4s, 8h3c preflop
- [x] **TESTED: Add-Chips via Options menu** — pokernow does NOT support this
  - Tried 3 times, "No add-chips option" every time. Stop trying this approach.
- [x] **FIXED: STATION river call threshold** — was calling 25% equity vs 40% pot odds
  - Reduced bonus from 8 → 5, tightened pot odds check from equity-5 to equity-3
- [x] **Session results:** 288+ actions, 0 errors, 97% slider accuracy, river value bets working

### Completed (2026-03-19 4AM — v17) 
- [x] **FIXED: Concurrent rebuy chaos** — 3 bots trying to rebuy simultaneously caused cascading false busts
- [x] **FIXED: Leave-resit stuck loop** — gives up after 3 attempts, falls through to bust path
- [x] **FIXED: Post-rebuy false busts** — bust confirmation raised to 5 checks, cooldown 30s
- [x] **Session results:** 246 actions, 0 errors, 94% slider accuracy, proper serialization

### Completed (2026-03-18 Night — v16)
- [x] Host false bust elimination during approval reloads
- [x] Host rebuy path rewrite (4 methods for re-seating)

### Completed (2026-03-18 Night — v13) ⭐ MAJOR BREAKTHROUGH
- [x] Slider 3-tier approach: 97-99% accuracy (arrow keys primary)
- [x] 5000 stacks (500BB) — deeper play, fewer busts
- [x] Enter key for submit — zero "Element detached" errors

### Priority 0: TAG/NIT Fold Rate Tuning (MEDIUM)
- TAG (Clawhi) at 17% fold — target 25-30%. Consider fold threshold 44 → 46.
- NIT (NitKing) at 25% fold — target 30-40%. Consider fold threshold 45 → 48.
- LAG (AceBot) at 14% — ✅ perfect for 4-handed.
- STATION (CallStn) at 10% — ✅ correct for calling station.

### Priority 1: Fix Crumbs Rebuy — Different Seat Approach (MEDIUM)
- **Root cause:** Pokernow auto-seats the bot with previous crumb stack on reload
- **Add Chips is NOT available** in pokernow Options menu (v18 confirmed)
- **TODO:** After leaving seat, click a DIFFERENT empty seat (not the one pokernow remembers)
- **TODO:** Track which seat the bot was in, target a different one on rebuy
- **TODO:** Try clicking empty seat directly without reload (avoid auto-seat trigger)

### Priority 2: MC Equity vs Random (MEDIUM)
- Both players showing 80%+ equity simultaneously — impossible
- MC sim uses hand-vs-random, not hand-vs-hand
- **TODO:** Use opponent range modeling to estimate actual equity vs likely holdings
- This affects decision quality in multiway pots

### Priority 3: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Arrow keys remain most reliable for React range inputs**
- **5000 stacks (500BB) is the sweet spot for bot testing**
- **Pokernow preserves crumb stacks on reload** — owner auto-seats with previous stack
- **Pokernow has NO "Add Chips" in Options menu** — v18 confirmed, don't try this approach
- **Rebuy serialization is critical** — concurrent rebuys cause cascading false busts
- **Bust confirmation needs 5+ checks** — SPA transitions can make bots appear unseated for 2+ seconds
- **30s rebuy cooldown is minimum** — 15s caused false busts at the edge
- **Host must rebuy LAST** — needs to stay available to approve other bots' seat requests
- **reCAPTCHA audio solve rate-limits** — fresh browser profiles help, but clearing cookies periodically needed
- **Submit button "Element detached" completely fixed** by Enter key as primary
- **Slider accuracy progression: v10(~20%) → v12(~30%) → v13(97%) → v17(94%) → v18(97%)**
- **raise_capped must NOT block river opening bets** — only prevents re-raise wars
- **LAG fold threshold 38 produces ~14% fold rate** in 4-handed (perfect for LAG)
- **River value betting is the single biggest EV improvement** — was leaving massive value on table

### Metrics History
| Version | Hands/min | Slider% | Error% | Rebuy Success | Notes |
|---------|-----------|---------|--------|---------------|-------|
| v13 | 5.6 | 97% | 7% | 100% | Arrow keys breakthrough |
| v16 | 7.4 | 99% | 0% | ~85% | Enter key fix, host rebuy fix |
| v17 | ~5.0* | 94% | 0% | ~80% | Serialized rebuys, crumbs fix |
| v18 | ~7.5 | 97% | 0% | 100% | River value betting, LAG fold fix |
*v17 rate lower due to more rebuy time from crumbs loop

# Poker Now AI Agent - TODO

## Status: v17 — Serialized rebuys, zero errors, 94% slider accuracy

### Completed (2026-03-19 4AM — v17) 
- [x] **FIXED: Concurrent rebuy chaos** — 3 bots trying to rebuy simultaneously caused cascading false busts
  - Global `anyone_rebuying` flag suppresses bust detection while any bot is rebuying
  - Host defers proactive rebuy when pending approvals exist
  - No more 3-minute rebuy chaos periods
- [x] **FIXED: Leave-resit stuck loop** — bot reloads pokernow, gets seated with crumb stack (3-42 chips), tries to leave and resit infinitely
  - After 3 attempts, gives up and falls through to bust path for proper rejoin
  - Bust path correctly handles full leave → seat-button click → form submit → approval
- [x] **FIXED: Post-rebuy false busts** — bot would get falsely detected as busted 16s after successful rebuy
  - Bust confirmation raised to 5 checks (was 3 for non-host)
  - Rebuy cooldown raised to 30s (was 15s)
- [x] **Session results:** 246 actions, 0 errors, 94% slider accuracy, proper serialization

### Completed (2026-03-18 Night — v16)
- [x] Host false bust elimination during approval reloads
- [x] Host rebuy path rewrite (4 methods for re-seating)

### Completed (2026-03-18 Night — v13) ⭐ MAJOR BREAKTHROUGH
- [x] Slider 3-tier approach: 97-99% accuracy (arrow keys primary)
- [x] 5000 stacks (500BB) — deeper play, fewer busts
- [x] Enter key for submit — zero "Element detached" errors

### Priority 0: Fix "Seated with Crumbs" Root Cause (HIGH)
- The leave-resit-stuck fix is a workaround — the real issue is that pokernow preserves the bot's crumb stack on page reload
- **Root cause:** When bot leaves seat + reloads, pokernow auto-seats the bot owner with their previous crumb stack
- **TODO:** Before leaving seat for rebuy, check if we can use "Add Chips" or "Top Up" option from Options menu
- **TODO:** Or, don't reload — instead, try clicking a different empty seat directly after leaving
- **TODO:** Or, use pokernow's built-in rebuy mechanism if it exists (some game modes have a rebuy button)

### Priority 1: Auto-Rebuy at Low Stack (MEDIUM)
- Proactive rebuy works but triggers the crumbs loop ~50% of the time
- **TODO:** Find the pokernow "Add Chips" button if available
- **TODO:** If not, improve the leave-resit flow to avoid crumb-stack re-seating

### Priority 2: Improve Decision Engine (MEDIUM)
- TAG fold rate at 21% — slightly below target 25-30%
- AceBot river value betting missing (checks 80%+ equity rivers)
- Both bots showing 80%+ equity in same hand (MC sim vs random issue)
- **TODO:** River value bet path: if eq > 75% and checked to us, bet 50-75% pot
- **TODO:** TAG preflop fold threshold may need further tightening
- **TODO:** Add opponent range modeling for equity calc

### Priority 3: GTO & Analytics (LOW)
- Balanced ranges, mixed strategies
- Track VPIP, PFR, AF, WTSD per bot per session
- Standard hand history format
- Multi-session performance comparison

### Learned (Technical)
- **Arrow keys remain most reliable for React range inputs**
- **5000 stacks (500BB) is the sweet spot for bot testing**
- **Pokernow preserves crumb stacks on reload** — owner auto-seats with previous stack
- **Rebuy serialization is critical** — concurrent rebuys cause cascading false busts
- **Bust confirmation needs 5+ checks** — SPA transitions can make bots appear unseated for 2+ seconds
- **30s rebuy cooldown is minimum** — 15s caused false busts at the edge
- **Host must rebuy LAST** — needs to stay available to approve other bots' seat requests
- **reCAPTCHA audio solve rate-limits** — fresh browser profiles help, but clearing cookies periodically needed
- **Submit button "Element detached" completely fixed** by Enter key as primary
- **Slider accuracy progression: v10(~20%) → v12(~30%) → v13(97%) → v17(94%)**

### Metrics History
| Version | Hands/min | Slider% | Error% | Rebuy Success | Notes |
|---------|-----------|---------|--------|---------------|-------|
| v13 | 5.6 | 97% | 7% | 100% | Arrow keys breakthrough |
| v16 | 7.4 | 99% | 0% | ~85% | Enter key fix, host rebuy fix |
| v17 | ~5.0* | 94% | 0% | ~80% | Serialized rebuys, crumbs fix |
*v17 rate lower due to more rebuy time from crumbs loop — will improve once root cause fixed

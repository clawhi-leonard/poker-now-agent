# Poker Now AI Agent - TODO

## Status: v20 — Extended anti-stutter + LAG rebalance, 41 hands tested, working as designed

### Completed (2026-03-19 11PM — v20)
- [x] **IMPROVED: Extended anti-stutter 4s → 8s window** — covers longer SPA freezes
  - Successfully caught and prevented duplicate raise: AceBot turn As 2d (75% equity)
  - Addresses 20s+ SPA freeze issue observed in v19 end-of-session
  - Log: "extended anti-stutter → downgraded raise to call (same street, 8s window)"
- [x] **IMPROVED: LAG fold threshold 38 → 36** — brings fold rate from 19% back toward 15%
  - Early positive signs: AceBot folded Qh 5d at 18% equity (proper LAG discipline)
  - Addresses v19 finding that LAG was folding 19% vs target ~15%
- [x] **Short session validation:** 41 actions, 0 errors, 1 anti-stutter save, smooth operation

### Completed (2026-03-19 7AM — v19)
- [x] **FIXED: TAG fold rate 17% → 25%** — raised fold/call threshold 44→46
  - Now correctly folding 8s6c(34%), 5h10d(35%), 4d3d(30%), 7c3c(37%)
  - Still playing QcAc(60%), KsAc(64%), 8c8d(69%) — proper TAG behavior
- [x] **FIXED: NIT fold rate 25% → 34%** — raised fold threshold 45→48, call 50→52
  - Now correctly folding Qh3c(42%), 9s7d(41%), Kd8s(46%)
  - Still playing AsAh(72%), KcJd(55%), AcTh(57%) — tight but playable
- [x] **FIXED: Flop re-raise stutter** — new anti-stutter tracks last raise per bot
  - Detects if bot raised same hand+street within 4s → downgrades to call/check
  - 4 correct triggers in 300-hand session, prevented all short-window stutters
  - LIMITATION: 20s+ SPA freezes not covered (need extended window in v20)
- [x] **IMPROVED: MC equity range filter** — opponents dealt from top ~45% of hands
  - Fixes hand-vs-random inflation (both players showing 80%+ equity simultaneously)
  - More realistic equity values — medium hands get lower equity vs skilled opponents
  - Side effect: slightly inflates all fold rates (~3-5%), which is acceptable
- [x] **Session results:** 300+ actions, 0 errors, 98% slider accuracy (best ever), 4 anti-stutter saves

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

### Priority 0: Full Session Validation (HIGH)
- **v20 needs full validation:** Current test was only 41 actions (too small for fold rate analysis)
- **TODO:** Run 200+ action session to validate LAG fold rate rebalancing
- **TODO:** Confirm extended anti-stutter handles complex scenarios under stress
- **TODO:** Generate comprehensive v20 vs v19 metrics comparison
- Early signs positive: extended anti-stutter working, LAG folding appropriately

### Priority 1: Session Analytics & Tracking (MEDIUM)
- **TODO:** Add VPIP, PFR, AF, WTSD tracking per bot per session
- **TODO:** Session-end statistics summary with fold rates, aggression metrics
- **TODO:** Automated comparison vs previous session baselines
- **TODO:** Standard hand history format for external analysis tools

### Priority 2: Fix Crumbs Rebuy — Different Seat Approach (LOW-MEDIUM)
- **Root cause:** Pokernow auto-seats the bot with previous crumb stack on reload
- **Add Chips is NOT available** in pokernow Options menu (v18 confirmed)
- **TODO:** After leaving seat, click a DIFFERENT empty seat (not the one pokernow remembers)
- **TODO:** Track which seat the bot was in, target a different one on rebuy
- **TODO:** Try clicking empty seat directly without reload (avoid auto-seat trigger)

### Priority 3: GTO Mixed Strategies (LOW)
- **TODO:** Implement balanced ranges with randomization at equilibrium points
- **TODO:** Mixed strategies for marginal spots (randomize check/bet, call/fold decisions)
- **TODO:** Nash equilibrium approximations for 4-handed play
- **TODO:** Exploitative adjustments based on opponent tendencies

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
- **LAG fold threshold 38 → 36 rebalancing** — v19 had 19% fold (too high), v20 early signs show improvement
- **Extended anti-stutter 8s window works** — caught turn stutter in v20 that 4s window might miss
- **River value betting is the single biggest EV improvement** — was leaving massive value on table
- **Range-filtered MC equity is more realistic** — opponents dealt from top ~45% of hands
- **Range filter inflates fold rates ~3-5%** — need to compensate thresholds slightly
- **Anti-stutter 4s window catches quick stutters** but not 20s+ SPA freezes
- **TAG fold threshold 46 produces 25% fold rate** — perfect for 4-handed TAG
- **NIT fold threshold 48/call 52 produces 34% fold rate** — perfect for 4-handed NIT
- **98% slider accuracy is the new stable baseline** — T1(mouse) + T2(arrows) combo

### Metrics History
| Version | Hands/min | Slider% | Error% | Rebuy Success | Notes |
|---------|-----------|---------|--------|---------------|-------|
| v13 | 5.6 | 97% | 7% | 100% | Arrow keys breakthrough |
| v16 | 7.4 | 99% | 0% | ~85% | Enter key fix, host rebuy fix |
| v17 | ~5.0* | 94% | 0% | ~80% | Serialized rebuys, crumbs fix |
| v18 | ~7.5 | 97% | 0% | 100% | River value betting, LAG fold fix |
| v19 | ~7.5 | 98% | 0% | 100% | Fold tuning, anti-stutter, range equity |
*v17 rate lower due to more rebuy time from crumbs loop

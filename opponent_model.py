"""
Adaptive Opponent Modeling — learns and exploits.

Tracks per-player, per-street stats. Persists to disk.
After enough data, shifts from balanced → exploitative.

Key concepts from Team26:
- Bayesian hand strength estimation
- Opponent behavior classification (passive/aggressive/balanced)
- Dynamic threshold adjustment
"""
import json
import os
import time
from collections import defaultdict

STATS_FILE = os.path.join(os.path.dirname(__file__), "opponent_stats.json")
MIN_HANDS_TO_EXPLOIT = 15  # need this many data points before exploiting


def _empty_player():
    return {
        "hands": 0,
        "preflop": {"raises": 0, "calls": 0, "folds": 0, "checks": 0},
        "flop":    {"raises": 0, "calls": 0, "folds": 0, "checks": 0},
        "turn":    {"raises": 0, "calls": 0, "folds": 0, "checks": 0},
        "river":   {"raises": 0, "calls": 0, "folds": 0, "checks": 0},
        # Specific patterns
        "cbet_opportunities": 0,  # times they were preflop raiser and saw flop
        "cbets": 0,               # times they bet the flop after raising pre
        "fold_to_raise": 0,       # times they folded facing a raise
        "raise_faced": 0,         # times they faced a raise
        "check_raise": 0,         # times they check-raised
        "check_then_acted": 0,    # times they checked then had a chance to act
        # Showdown data
        "showdowns": 0,
        "showdown_wins": 0,
        "went_to_showdown_after_raise": 0,
        "won_showdown_after_raise": 0,
        "last_seen": 0,
    }


class OpponentModel:
    def __init__(self):
        self.players = {}
        self.current_hand = {}  # per-player actions this hand
        self.hand_raiser = None  # who raised preflop
        self.opp_hand_strength = {}  # Bayesian estimate per player
        self._load()

    # ---- Persistence ----

    def _load(self):
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, "r") as f:
                    self.players = json.load(f)
                print(f"   📊 Loaded stats for {len(self.players)} opponents")
        except:
            self.players = {}

    def save(self):
        try:
            with open(STATS_FILE, "w") as f:
                json.dump(self.players, f, indent=2)
        except:
            pass

    # ---- Recording ----

    def ensure_player(self, name):
        if name not in self.players:
            self.players[name] = _empty_player()

    def new_hand(self):
        """Call at start of each new hand."""
        for name in self.opp_hand_strength:
            self.opp_hand_strength[name] = 0.5
        self.opp_hand_strength = {}
        self.current_hand = {}
        self.hand_raiser = None
        # Increment hand count for all seated players
        # (caller should call new_hand_for_player separately)

    def record_action(self, player, action, street):
        """Record an opponent's action."""
        self.ensure_player(player)
        p = self.players[player]
        p["last_seen"] = int(time.time())
        
        act = action.lower().strip()
        
        # Normalize
        if "raise" in act or "bet" in act:
            act_key = "raises"
        elif "call" in act:
            act_key = "calls"
        elif "fold" in act:
            act_key = "folds"
        elif "check" in act:
            act_key = "checks"
        else:
            return

        if street in p:
            p[street][act_key] = p[street].get(act_key, 0) + 1

        # Track patterns
        if act_key == "raises" and street == "preflop":
            self.hand_raiser = player

        # C-bet tracking
        if street == "flop" and self.hand_raiser == player:
            p["cbet_opportunities"] = p.get("cbet_opportunities", 0) + 1
            if act_key == "raises":
                p["cbets"] = p.get("cbets", 0) + 1

        # Fold to raise
        if act_key == "folds":
            # Check if they faced a raise (approximate)
            p["fold_to_raise"] = p.get("fold_to_raise", 0) + 1
        
        if act_key in ("raises", "calls", "folds"):
            p["raise_faced"] = p.get("raise_faced", 0) + 1

        # Track in current hand
        if player not in self.current_hand:
            self.current_hand[player] = []
        self.current_hand[player].append((street, act_key))

        # Update Bayesian hand strength
        self._update_hand_strength(player, act_key, street)

    def record_showdown(self, player, won):
        """Record showdown result."""
        self.ensure_player(player)
        p = self.players[player]
        p["showdowns"] = p.get("showdowns", 0) + 1
        if won:
            p["showdown_wins"] = p.get("showdown_wins", 0) + 1

    def end_hand(self):
        """Call at end of hand. Saves periodically."""
        for name in self.current_hand:
            self.ensure_player(name)
            self.players[name]["hands"] = self.players[name].get("hands", 0) + 1
        self.save()

    # ---- Bayesian Hand Strength (Team26 approach) ----

    def _update_hand_strength(self, player, act_key, street):
        """Update estimated hand strength based on action."""
        if player not in self.opp_hand_strength:
            self.opp_hand_strength[player] = 0.5

        # Multipliers by street (later streets = stronger signal)
        raise_mult = {"preflop": 1.10, "flop": 1.25, "turn": 1.40, "river": 1.60}
        call_mult  = {"preflop": 1.02, "flop": 1.05, "turn": 1.08, "river": 1.10}
        check_mult = 0.92
        
        hs = self.opp_hand_strength[player]
        
        if act_key == "raises":
            # Adjust based on player type — aggressive players raise with worse hands
            agg = self.get_aggression(player)
            adj = raise_mult.get(street, 1.2) * (1.0 - agg * 0.3)  # less credit to aggro players
            hs = min(0.90, hs * adj)
        elif act_key == "calls":
            hs = min(0.80, hs * call_mult.get(street, 1.05))
        elif act_key == "checks":
            hs *= check_mult
        elif act_key == "folds":
            hs = 0.0  # they're out

        self.opp_hand_strength[player] = max(0.05, min(0.95, hs))

    def get_opp_hand_strength(self, player=None):
        """Get estimated hand strength of opponent(s). 0.0-1.0."""
        if player:
            return self.opp_hand_strength.get(player, 0.5)
        if not self.opp_hand_strength:
            return 0.5
        # Return max opponent strength (worst case)
        active = {k: v for k, v in self.opp_hand_strength.items() if v > 0.0}
        return max(active.values()) if active else 0.5

    # ---- Player Profiling ----

    def _total_actions(self, player, street=None):
        if player not in self.players:
            return 0
        p = self.players[player]
        if street:
            s = p.get(street, {})
            return s.get("raises", 0) + s.get("calls", 0) + s.get("folds", 0) + s.get("checks", 0)
        total = 0
        for st in ["preflop", "flop", "turn", "river"]:
            total += self._total_actions(player, st)
        return total

    def get_vpip(self, player):
        """Voluntarily put $ in pot preflop (raise or call, not blind)."""
        if player not in self.players:
            return 0.5
        pre = self.players[player].get("preflop", {})
        total = pre.get("raises", 0) + pre.get("calls", 0) + pre.get("folds", 0)
        if total == 0:
            return 0.5
        return (pre.get("raises", 0) + pre.get("calls", 0)) / total

    def get_pfr(self, player):
        """Preflop raise %."""
        if player not in self.players:
            return 0.3
        pre = self.players[player].get("preflop", {})
        total = pre.get("raises", 0) + pre.get("calls", 0) + pre.get("folds", 0)
        if total == 0:
            return 0.3
        return pre.get("raises", 0) / total

    def get_aggression(self, player):
        """Overall aggression factor (raises / (raises + calls + checks))."""
        if player not in self.players:
            return 0.3
        p = self.players[player]
        raises = sum(p.get(st, {}).get("raises", 0) for st in ["preflop","flop","turn","river"])
        passive = sum(p.get(st, {}).get("calls", 0) + p.get(st, {}).get("checks", 0) 
                      for st in ["preflop","flop","turn","river"])
        total = raises + passive
        if total == 0:
            return 0.3
        return raises / total

    def get_fold_to_raise(self, player):
        """How often they fold when facing aggression."""
        if player not in self.players:
            return 0.3
        p = self.players[player]
        faced = p.get("raise_faced", 0)
        if faced < 3:
            return 0.3
        return p.get("fold_to_raise", 0) / faced

    def get_cbet_pct(self, player):
        """C-bet frequency."""
        if player not in self.players:
            return 0.5
        p = self.players[player]
        opps = p.get("cbet_opportunities", 0)
        if opps < 3:
            return 0.5
        return p.get("cbets", 0) / opps

    def get_showdown_winrate(self, player):
        if player not in self.players:
            return 0.5
        p = self.players[player]
        if p.get("showdowns", 0) < 3:
            return 0.5
        return p.get("showdown_wins", 0) / p["showdowns"]

    # ---- Player Classification ----

    def classify(self, player):
        """
        Returns player type:
        - "rock": tight-passive (low VPIP, low aggression)
        - "nit": very tight (folds a lot)
        - "TAG": tight-aggressive
        - "LAG": loose-aggressive
        - "station": loose-passive (calls everything)
        - "maniac": hyper-aggressive
        - "unknown": not enough data
        """
        if player not in self.players or self.players[player].get("hands", 0) < MIN_HANDS_TO_EXPLOIT:
            return "unknown"
        
        vpip = self.get_vpip(player)
        agg = self.get_aggression(player)
        fold = self.get_fold_to_raise(player)
        
        if vpip < 0.25:
            return "nit" if fold > 0.5 else "rock"
        elif vpip < 0.45:
            return "TAG" if agg > 0.35 else "rock"
        else:
            if agg > 0.50:
                return "maniac" if agg > 0.65 else "LAG"
            else:
                return "station"

    # ---- Exploit Adjustments ----

    def get_adjustments(self, player):
        """
        Returns strategy adjustments based on opponent type.
        Format: dict with threshold modifiers.
        """
        ptype = self.classify(player)
        
        if ptype == "unknown":
            return {"bluff_freq": 0.15, "call_wider": 0, "raise_more": 0, "fold_more": 0, "desc": "balanced (no data)"}
        
        if ptype == "nit":
            return {
                "bluff_freq": 0.35,      # bluff them a LOT — they fold
                "call_wider": -10,        # call TIGHTER vs their bets (they have it)
                "raise_more": 5,          # raise lighter (steal)
                "fold_more": 10,          # fold more vs their raises
                "desc": f"NIT — steal often, respect their raises"
            }
        
        if ptype == "rock":
            return {
                "bluff_freq": 0.25,
                "call_wider": -5,
                "raise_more": 3,
                "fold_more": 5,
                "desc": f"ROCK — moderate stealing, cautious vs aggression"
            }
        
        if ptype == "TAG":
            return {
                "bluff_freq": 0.12,
                "call_wider": 0,
                "raise_more": 0,
                "fold_more": 0,
                "desc": f"TAG — play solid, avoid fancy plays"
            }
        
        if ptype == "LAG":
            return {
                "bluff_freq": 0.08,       # don't bluff bluffers
                "call_wider": 10,          # call wider (they bet with less)
                "raise_more": -3,
                "fold_more": -5,           # fold less vs their aggression
                "desc": f"LAG — call down lighter, trap more"
            }
        
        if ptype == "station":
            return {
                "bluff_freq": 0.03,       # NEVER bluff a station
                "call_wider": 0,
                "raise_more": 5,           # value raise thinner
                "fold_more": 5,            # respect their rare raises
                "desc": f"STATION — pure value, no bluffs"
            }
        
        if ptype == "maniac":
            return {
                "bluff_freq": 0.02,
                "call_wider": 15,          # call MUCH wider
                "raise_more": -5,
                "fold_more": -10,          # almost never fold to them
                "desc": f"MANIAC — let them hang themselves, call wide"
            }
        
        return {"bluff_freq": 0.15, "call_wider": 0, "raise_more": 0, "fold_more": 0, "desc": "balanced"}

    # ---- Summary ----

    def summary(self):
        """Return readable summary of all tracked opponents."""
        lines = []
        for name, p in self.players.items():
            hands = p.get("hands", 0)
            if hands < 2:
                continue
            ptype = self.classify(name)
            vpip = self.get_vpip(name)
            agg = self.get_aggression(name)
            ftr = self.get_fold_to_raise(name)
            lines.append(f"{name}: {ptype} | VPIP={vpip:.0%} AGG={agg:.0%} FTR={ftr:.0%} ({hands}h)")
        return "\n".join(lines) if lines else "No opponent data yet"

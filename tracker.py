"""
Session & PnL Tracker for Poker Bot(s)

Tracks per-session:
  - Start/end time
  - Starting/ending stack
  - Rebuys
  - Net PnL (end_stack - start_stack - rebuys * buy_in)
  - Hands played, actions, VPIP/PFR
  - Bot version/config changes
  - Opponent profiles seen

All data persisted to JSON for dashboard consumption.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
CHANGELOG_FILE = DATA_DIR / "changelog.json"

def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    if not SESSIONS_FILE.exists():
        SESSIONS_FILE.write_text("[]")
    if not CHANGELOG_FILE.exists():
        CHANGELOG_FILE.write_text("[]")


class SessionTracker:
    """Track a single poker session."""
    
    def __init__(self, bot_name="Clawhi", buy_in=1000, bot_version="v3", mode="single"):
        ensure_data_dir()
        self.session = {
            "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "bot_name": bot_name,
            "bot_version": bot_version,
            "mode": mode,  # "single" or "multi"
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "buy_in": buy_in,
            "starting_stack": buy_in,
            "ending_stack": None,
            "rebuys": 0,
            "hands_played": 0,
            "actions": {
                "preflop": {"fold": 0, "call": 0, "raise": 0, "check": 0},
                "flop": {"fold": 0, "call": 0, "raise": 0, "check": 0},
                "turn": {"fold": 0, "call": 0, "raise": 0, "check": 0},
                "river": {"fold": 0, "call": 0, "raise": 0, "check": 0}
            },
            "stack_history": [],  # [(hand_num, stack, timestamp)]
            "pnl": 0,
            "pnl_per_hand": 0,
            "bb_per_100": 0,
            "bb_size": 10,
            "peak_stack": buy_in,
            "min_stack": buy_in,
            "llm_calls": 0,
            "local_decisions": 0,
            "opponents": [],
            "notes": ""
        }
        self._hand_num = 0
    
    def new_hand(self, stack=None):
        """Called at start of each new hand."""
        self._hand_num += 1
        self.session["hands_played"] = self._hand_num
        if stack is not None:
            self.record_stack(stack)
    
    def record_stack(self, stack):
        """Record current stack value."""
        self.session["stack_history"].append({
            "hand": self._hand_num,
            "stack": stack,
            "time": time.time()
        })
        if stack > self.session["peak_stack"]:
            self.session["peak_stack"] = stack
        if stack < self.session["min_stack"]:
            self.session["min_stack"] = stack
        self.session["ending_stack"] = stack
    
    def record_action(self, street, action):
        """Record an action (fold/call/raise/check) on a street."""
        street = street.lower()
        action = action.lower()
        if street in self.session["actions"] and action in self.session["actions"][street]:
            self.session["actions"][street][action] += 1
    
    def record_rebuy(self, amount=None):
        """Record a rebuy."""
        self.session["rebuys"] += 1
        if amount:
            self.session["buy_in"] = amount  # update in case it changed
    
    def record_llm_call(self):
        self.session["llm_calls"] += 1
    
    def record_local_decision(self):
        self.session["local_decisions"] += 1
    
    def set_opponents(self, opponents):
        """Set list of opponent names/styles seen."""
        self.session["opponents"] = opponents
    
    def end_session(self, ending_stack=None, notes=""):
        """Finalize session and save."""
        self.session["end_time"] = datetime.now().isoformat()
        if ending_stack is not None:
            self.session["ending_stack"] = ending_stack
        
        es = self.session["ending_stack"] or 0
        buy_in = self.session["buy_in"]
        rebuys = self.session["rebuys"]
        total_invested = buy_in + (rebuys * buy_in)
        
        self.session["pnl"] = es - total_invested
        hands = self.session["hands_played"]
        bb = self.session["bb_size"]
        
        self.session["pnl_per_hand"] = round(self.session["pnl"] / max(hands, 1), 2)
        self.session["bb_per_100"] = round((self.session["pnl"] / max(bb, 1)) / max(hands, 1) * 100, 2)
        self.session["notes"] = notes
        
        # Calculate VPIP/PFR
        pf = self.session["actions"]["preflop"]
        pf_total = pf["fold"] + pf["call"] + pf["raise"] + pf["check"]
        self.session["vpip"] = round((pf["call"] + pf["raise"]) / max(pf_total, 1) * 100, 1)
        self.session["pfr"] = round(pf["raise"] / max(pf_total, 1) * 100, 1)
        
        # Save
        self._save()
        return self.session
    
    def _save(self):
        """Append session to sessions file."""
        sessions = load_sessions()
        sessions.append(self.session)
        SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def load_sessions():
    """Load all sessions."""
    ensure_data_dir()
    try:
        return json.loads(SESSIONS_FILE.read_text())
    except:
        return []


def get_dashboard_data():
    """Aggregate data for dashboard consumption."""
    sessions = load_sessions()
    if not sessions:
        return {"sessions": [], "totals": {}, "pnl_chart": []}
    
    total_pnl = 0
    total_hands = 0
    total_invested = 0
    pnl_chart = []
    
    for s in sessions:
        pnl = s.get("pnl", 0)
        total_pnl += pnl
        total_hands += s.get("hands_played", 0)
        total_invested += s.get("buy_in", 0) * (1 + s.get("rebuys", 0))
        pnl_chart.append({
            "session_id": s["id"],
            "date": s.get("start_time", ""),
            "pnl": pnl,
            "cumulative_pnl": total_pnl,
            "hands": s.get("hands_played", 0)
        })
    
    # Aggregate VPIP/PFR across all sessions
    total_pf_actions = 0
    total_vpip_actions = 0
    total_pfr_actions = 0
    for s in sessions:
        pf = s.get("actions", {}).get("preflop", {})
        t = pf.get("fold", 0) + pf.get("call", 0) + pf.get("raise", 0) + pf.get("check", 0)
        total_pf_actions += t
        total_vpip_actions += pf.get("call", 0) + pf.get("raise", 0)
        total_pfr_actions += pf.get("raise", 0)
    
    bb_size = sessions[-1].get("bb_size", 10) if sessions else 10
    
    return {
        "sessions": sessions,
        "totals": {
            "total_sessions": len(sessions),
            "total_hands": total_hands,
            "total_pnl": total_pnl,
            "total_invested": total_invested,
            "roi": round(total_pnl / max(total_invested, 1) * 100, 1),
            "pnl_per_hand": round(total_pnl / max(total_hands, 1), 2),
            "bb_per_100": round((total_pnl / max(bb_size, 1)) / max(total_hands, 1) * 100, 2),
            "vpip": round(total_vpip_actions / max(total_pf_actions, 1) * 100, 1),
            "pfr": round(total_pfr_actions / max(total_pf_actions, 1) * 100, 1),
            "total_llm_calls": sum(s.get("llm_calls", 0) for s in sessions),
            "total_local_decisions": sum(s.get("local_decisions", 0) for s in sessions),
            "best_session": max(s.get("pnl", 0) for s in sessions),
            "worst_session": min(s.get("pnl", 0) for s in sessions),
            "winning_sessions": sum(1 for s in sessions if s.get("pnl", 0) > 0),
            "losing_sessions": sum(1 for s in sessions if s.get("pnl", 0) < 0)
        },
        "pnl_chart": pnl_chart
    }


def log_config_change(version, description, changes):
    """Log a bot configuration change for A/B tracking."""
    ensure_data_dir()
    try:
        changelog = json.loads(CHANGELOG_FILE.read_text())
    except:
        changelog = []
    
    changelog.append({
        "timestamp": datetime.now().isoformat(),
        "version": version,
        "description": description,
        "changes": changes,
        "session_at_change": len(load_sessions())
    })
    
    CHANGELOG_FILE.write_text(json.dumps(changelog, indent=2))


def get_changelog():
    """Get config changelog."""
    ensure_data_dir()
    try:
        return json.loads(CHANGELOG_FILE.read_text())
    except:
        return []

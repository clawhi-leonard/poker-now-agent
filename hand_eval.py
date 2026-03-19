"""
Hand evaluation engine — NO API calls. Pure math.
Preflop: lookup table (instant)
Postflop: Monte Carlo simulation (fast, local)

Inspired by Team26 poker-ai approach.
"""
import random
from itertools import combinations

# ---- Preflop Equity Tables (heads-up, from caniwin.com) ----

PREFLOP_OFFSUIT = {
    "AA":84.93,"KK":82.11,"QQ":79.63,"JJ":77.15,"TT":74.66,"99":71.66,
    "88":68.71,"77":65.72,"AK":64.46,"AQ":63.50,"AJ":62.53,"66":62.70,
    "AT":61.56,"KQ":60.43,"A9":59.44,"KJ":59.44,"55":59.64,"A8":58.37,
    "KT":58.49,"A7":57.16,"QJ":56.90,"K9":56.40,"A6":55.87,"A5":55.74,
    "QT":55.94,"44":56.25,"A4":54.73,"K8":54.43,"A3":53.85,"Q9":53.86,
    "JT":53.82,"K7":53.41,"A2":52.94,"K6":52.29,"33":52.83,"Q8":51.93,
    "K5":51.25,"J9":51.63,"K4":50.22,"Q7":49.90,"T9":49.81,"J8":49.71,
    "K3":49.33,"Q6":48.99,"K2":48.42,"22":48.38,"Q5":47.95,"T8":47.81,
    "J7":47.72,"Q4":46.92,"Q3":46.02,"98":46.06,"T7":45.82,"J6":45.71,
    "Q2":45.10,"J5":44.90,"97":44.07,"J4":43.86,"T6":43.84,"J3":42.96,
    "87":42.69,"96":42.10,"J2":42.04,"T5":41.85,"T4":41.05,"86":40.69,
    "95":40.13,"T3":40.15,"76":39.95,"T2":39.23,"85":38.74,"94":38.08,
    "75":37.67,"93":37.42,"65":37.01,"84":36.70,"92":36.51,"74":35.66,
    "54":35.07,"64":35.00,"83":34.74,"82":34.08,"73":33.71,"53":33.16,
    "63":33.06,"43":32.06,"72":31.71,"52":31.19,"62":31.07,"42":30.11,
    "32":29.23
}

PREFLOP_SUITED = {
    "AK":66.21,"AQ":65.31,"AJ":64.39,"AT":62.22,"KQ":62.40,"A9":61.50,
    "KJ":61.47,"A8":60.50,"KT":60.58,"A7":59.38,"QJ":59.07,"K9":58.63,
    "A6":58.17,"A5":58.06,"QT":58.17,"A4":57.13,"K8":56.79,"A3":56.33,
    "Q9":56.22,"K7":55.84,"JT":56.15,"A2":56.15,"K6":54.80,"Q8":54.41,
    "K5":53.83,"J9":54.11,"K4":52.88,"Q7":52.52,"K3":52.07,"T9":52.37,
    "J8":52.31,"Q6":51.67,"K2":51.23,"Q5":50.71,"T8":50.50,"J7":50.45,
    "Q4":49.76,"Q3":48.93,"98":48.85,"T7":48.65,"J6":48.57,"Q2":48.10,
    "J5":47.82,"97":46.99,"J4":46.86,"T6":46.80,"J3":46.04,"87":45.68,
    "96":45.15,"J2":45.20,"T5":44.93,"T4":44.20,"86":43.81,"95":43.31,
    "T3":43.37,"76":42.82,"T2":42.54,"85":41.99,"94":41.40,"75":40.97,
    "93":40.80,"65":40.34,"84":40.34,"92":39.97,"74":39.10,"54":38.53,
    "64":38.48,"83":38.28,"82":37.67,"73":37.30,"53":36.75,"63":36.68,
    "43":35.72,"72":35.43,"52":34.92,"62":34.83,"42":33.91,"32":33.09
}

RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"T":10,"J":11,"Q":12,"K":13,"A":14}

def normalize_card(card_str):
    """Convert 'Ks' -> ('K','s'), '10h' -> ('T','h')"""
    card_str = card_str.strip()
    if len(card_str) == 3 and card_str[:2] == "10":
        return ("T", card_str[2].lower())
    return (card_str[:-1].upper(), card_str[-1].lower())

def preflop_equity(card1_str, card2_str, num_opponents=1):
    """Look up preflop equity. Returns 0-100. Instant."""
    c1 = normalize_card(card1_str)
    c2 = normalize_card(card2_str)
    
    r1, s1 = c1
    r2, s2 = c2
    
    # Normalize order (higher rank first)
    v1, v2 = RANK_ORDER.get(r1, 0), RANK_ORDER.get(r2, 0)
    if v1 < v2:
        r1, r2 = r2, r1
        s1, s2 = s2, s1
    
    # Pair
    if r1 == r2:
        key = r1 + r2
        eq = PREFLOP_OFFSUIT.get(key, 50.0)
    elif s1 == s2:
        key = r1 + r2
        eq = PREFLOP_SUITED.get(key, 50.0)
    else:
        key = r1 + r2
        eq = PREFLOP_OFFSUIT.get(key, 50.0)
    
    # Adjust for multi-way (rough approximation)
    if num_opponents > 1:
        eq = eq * (0.85 ** (num_opponents - 1))
    
    return eq


# ---- Postflop Hand Evaluation ----

def hand_rank(cards, plo_hole=None, plo_board=None):
    """
    Evaluate hand, return (rank, kickers) tuple for comparison.
    
    For PLO: pass plo_hole (4 cards) and plo_board (3-5 cards).
    Must use exactly 2 from hole + 3 from board.
    
    For NLHE: pass all cards together (5-7), picks best 5.
    
    Ranks: 9=straight flush, 8=quads, 7=full house, 6=flush, 5=straight,
           4=trips, 3=two pair, 2=pair, 1=high card
    """
    if plo_hole and plo_board:
        # PLO: must use exactly 2 hole + 3 board
        best = (0, [])
        for hole_combo in combinations(plo_hole, 2):
            for board_combo in combinations(plo_board, 3):
                hand = list(hole_combo) + list(board_combo)
                rank = _eval_5(hand)
                if rank > best:
                    best = rank
        return best
    
    if len(cards) < 5:
        return (0, [])
    
    best = (0, [])
    for combo in combinations(cards, 5):
        rank = _eval_5(combo)
        if rank > best:
            best = rank
    return best

def _eval_5(cards):
    """Evaluate exactly 5 cards."""
    ranks = sorted([RANK_ORDER.get(c[0], 0) for c in cards], reverse=True)
    suits = [c[1] for c in cards]
    
    is_flush = len(set(suits)) == 1
    
    # Check straight
    is_straight = False
    straight_high = 0
    unique_ranks = sorted(set(ranks), reverse=True)
    if len(unique_ranks) >= 5:
        for i in range(len(unique_ranks) - 4):
            if unique_ranks[i] - unique_ranks[i+4] == 4:
                is_straight = True
                straight_high = unique_ranks[i]
                break
    # Wheel (A-2-3-4-5)
    if set([14,5,4,3,2]).issubset(set(ranks)):
        is_straight = True
        straight_high = 5
    
    from collections import Counter
    rc = Counter(ranks)
    groups = sorted(rc.items(), key=lambda x: (x[1], x[0]), reverse=True)
    
    if is_straight and is_flush:
        return (9, [straight_high])
    
    if groups[0][1] == 4:
        return (8, [groups[0][0], groups[1][0]])
    
    if groups[0][1] == 3 and groups[1][1] >= 2:
        return (7, [groups[0][0], groups[1][0]])
    
    if is_flush:
        return (6, ranks)
    
    if is_straight:
        return (5, [straight_high])
    
    if groups[0][1] == 3:
        kickers = sorted([g[0] for g in groups[1:]], reverse=True)
        return (4, [groups[0][0]] + kickers)
    
    if groups[0][1] == 2 and groups[1][1] == 2:
        pair_ranks = sorted([groups[0][0], groups[1][0]], reverse=True)
        kicker = [g[0] for g in groups if g[1] == 1]
        return (3, pair_ranks + kicker)
    
    if groups[0][1] == 2:
        kickers = sorted([g[0] for g in groups[1:]], reverse=True)
        return (2, [groups[0][0]] + kickers)
    
    return (1, ranks)


# ---- Monte Carlo Win Rate ----

ALL_CARDS = [(r, s) for r in RANK_ORDER.keys() for s in ['h','s','d','c'] if r != 'T' or True]
# Remove dups — "10" and "T" map to same
DECK = []
for s in ['h','s','d','c']:
    for r in ['2','3','4','5','6','7','8','9','T','J','Q','K','A']:
        DECK.append((r, s))


def monte_carlo_equity(my_cards, board_cards, num_opponents=1, simulations=200, is_plo=False):
    """
    Monte Carlo simulation of win rate. Returns 0.0-1.0.
    For PLO: must use exactly 2 hole + 3 board. Opponents get 4 cards too.
    For NLHE: best 5 from 7.
    """
    my = [normalize_card(c) if isinstance(c, str) else c for c in my_cards]
    board = [normalize_card(c) if isinstance(c, str) else c for c in board_cards]
    
    used = set()
    for c in my + board:
        used.add(c)
    
    remaining = [c for c in DECK if c not in used]
    cards_to_deal = 5 - len(board)
    opp_hole_count = 4 if is_plo else 2
    
    wins = 0
    ties = 0
    
    for _ in range(simulations):
        random.shuffle(remaining)
        idx = 0
        
        sim_board = board + remaining[idx:idx+cards_to_deal]
        idx += cards_to_deal
        
        if is_plo:
            my_hand = hand_rank(None, plo_hole=my, plo_board=sim_board)
        else:
            my_hand = hand_rank(my + sim_board)
        
        beaten_all = True
        tied_any = False
        for opp in range(num_opponents):
            opp_cards = remaining[idx:idx+opp_hole_count]
            idx += opp_hole_count
            if idx > len(remaining):
                break
            if is_plo:
                opp_hand = hand_rank(None, plo_hole=list(opp_cards), plo_board=sim_board)
            else:
                opp_hand = hand_rank(list(opp_cards) + sim_board)
            if opp_hand > my_hand:
                beaten_all = False
                break
            elif opp_hand == my_hand:
                tied_any = True
        
        if beaten_all:
            if tied_any:
                ties += 1
            else:
                wins += 1
    
    return (wins + ties * 0.5) / max(simulations, 1)


def get_equity(my_cards_str, board_cards_str=None, num_opponents=1):
    """
    Main entry point. Returns equity 0-100.
    Auto-detects PLO (4 cards) vs NLHE (2 cards).
    Preflop NLHE: uses lookup table (instant)
    Preflop PLO: uses Monte Carlo with fewer sims
    Postflop: uses Monte Carlo (fast)
    """
    is_plo = len(my_cards_str) == 4
    
    if not board_cards_str or len(board_cards_str) == 0:
        # Preflop
        if is_plo:
            # PLO preflop — quick MC (100 sims, ~50ms)
            eq = monte_carlo_equity(my_cards_str, [], num_opponents, simulations=100, is_plo=True)
            return eq * 100
        else:
            return preflop_equity(my_cards_str[0], my_cards_str[1], num_opponents)
    else:
        # Postflop — Monte Carlo
        sims = 200 if is_plo else 500  # more sims for better accuracy
        eq = monte_carlo_equity(my_cards_str, board_cards_str, num_opponents, simulations=sims, is_plo=is_plo)
        return eq * 100


# ---- Draw Detection ----

def detect_draws(my_cards_str, board_cards_str):
    """Detect flush draws, straight draws, etc. Returns list of draw descriptions."""
    if not board_cards_str:
        return []
    
    my = [normalize_card(c) for c in my_cards_str]
    board = [normalize_card(c) for c in board_cards_str]
    all_cards = my + board
    
    draws = []
    
    # Flush draw
    from collections import Counter
    suits = [c[1] for c in all_cards]
    sc = Counter(suits)
    for suit, count in sc.items():
        if count == 4:
            my_in_suit = sum(1 for c in my if c[1] == suit)
            if my_in_suit >= 1:
                draws.append("flush draw")
        elif count >= 5:
            my_in_suit = sum(1 for c in my if c[1] == suit)
            if my_in_suit >= 1:
                draws.append("flush!")
    
    # Straight draw
    vals = sorted(set(RANK_ORDER.get(c[0], 0) for c in all_cards))
    my_vals = set(RANK_ORDER.get(c[0], 0) for c in my)
    
    # Check for OESD (open-ended straight draw) or gutshot
    for start in range(2, 11):
        needed = set(range(start, start+5))
        have = needed.intersection(set(vals))
        missing = needed - set(vals)
        if len(have) == 4 and len(missing) == 1:
            # We contribute to this
            if my_vals.intersection(have):
                if min(missing) > min(needed) and max(missing) < max(needed):
                    draws.append("gutshot")
                else:
                    draws.append("OESD")
                break
    
    return list(set(draws))


if __name__ == "__main__":
    # Test
    print(f"AK offsuit preflop: {preflop_equity('Ah', 'Ks')}%")
    print(f"AK suited preflop: {preflop_equity('Ah', 'Kh')}%")
    print(f"72 offsuit preflop: {preflop_equity('7h', '2c')}%")
    print(f"AA preflop: {preflop_equity('Ah', 'As')}%")
    
    # Postflop test
    eq = get_equity(['Ah', 'Kh'], ['Qh', 'Jh', '2c'])
    print(f"AKh on Qh Jh 2c: {eq:.1f}% (flush draw + overcards)")
    
    draws = detect_draws(['Ah', 'Kh'], ['Qh', 'Jh', '2c'])
    print(f"Draws: {draws}")

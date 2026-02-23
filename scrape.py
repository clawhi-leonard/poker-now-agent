"""
Scrape Poker Now DOM into minimal text for LLM consumption.
Connects via CDP, grabs accessibility tree, parses to structured state.
Optimized for speed — no unnecessary processing.
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright
from config import CDP_ENDPOINT, PLAYER_NAME

SUIT_MAP = {"h": "♥", "s": "♠", "d": "♦", "c": "♣"}


async def get_poker_page():
    """Connect to existing browser and find poker tab."""
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "pokernow.com" in page.url:
                return pw, page
    raise RuntimeError("No Poker Now tab found")


async def scrape_state(page) -> dict:
    """Extract game state from the page using JS for maximum speed."""
    # Single JS call — extracts everything from DOM in one shot for speed.
    # Poker Now uses React with specific class names. We also use fallback
    # selectors since the DOM structure can vary between game modes.
    state = await page.evaluate("""() => {
        const result = {
            is_my_turn: false,
            actions: [],
            my_cards: [],
            board: [],
            players: [],
            pot: null,
            pot_total: null,
            game_type: null,
            street: null,
            my_hand_strength: null,
            chat: []
        };

        // Game type — .table-game-type is the confirmed class
        const gtEl = document.querySelector('.table-game-type');
        if (gtEl) result.game_type = gtEl.textContent.trim();

        // Pot — .table-pot-size contains main pot + total
        const potArea = document.querySelector('.table-pot-size');
        if (potArea) {
            const nums = potArea.textContent.match(/\\d+/g);
            if (nums && nums.length >= 1) result.pot = parseInt(nums[0]);
            if (nums && nums.length >= 2) result.pot_total = parseInt(nums[nums.length - 1]);
        }

        // Board cards — inside .table-cards, each card is a child div
        // Card structure: div > (value div + suit div)
        const boardArea = document.querySelector('.table-cards');
        if (boardArea) {
            boardArea.querySelectorAll(':scope > div').forEach(card => {
                const children = card.querySelectorAll(':scope > div, :scope > span');
                if (children.length >= 2) {
                    const val = children[0]?.textContent?.trim() || '';
                    const suit = children[1]?.textContent?.trim() || '';
                    if (val && /^[2-9TJQKA]$/.test(val)) result.board.push(val + suit);
                }
            });
        }

        // Find our seat — look for a .table-player that has our cards visible
        // Our player has card elements with visible values (opponents' cards are hidden)
        document.querySelectorAll('.table-player').forEach(player => {
            const nameEl = player.querySelector('a');
            if (!nameEl) return; // empty seat

            const name = nameEl.textContent.trim();
            const stackText = player.textContent;
            const stackMatch = stackText.match(/(?:^|\\s)(\\d+)(?:\\s|$)/g);

            // Find stack value — it's in a specific child, usually after the name
            let stack = '?';
            player.querySelectorAll('p, div').forEach(el => {
                const t = el.textContent.trim();
                if (/^\\d+$/.test(t) && parseInt(t) > 0 && parseInt(t) < 100000) {
                    stack = t;
                }
            });

            // Detect cards on this player (only our cards are face-up)
            const cards = [];
            player.querySelectorAll('div').forEach(cardDiv => {
                const subs = cardDiv.querySelectorAll(':scope > div, :scope > span');
                if (subs.length === 3) { // value, suit-icon, suit-letter format
                    const v = subs[0]?.textContent?.trim();
                    const s = subs[2]?.textContent?.trim();
                    if (v && /^[2-9TJQKA]$/.test(v) && s && /^[hsdc]$/.test(s)) {
                        cards.push(v + s);
                    }
                }
                if (subs.length === 2) {
                    const v = subs[0]?.textContent?.trim();
                    const s = subs[1]?.textContent?.trim();
                    if (v && /^[2-9TJQKA]$/.test(v) && s && /^[hsdc]$/.test(s)) {
                        cards.push(v + s);
                    }
                }
            });

            const p = { name, stack, bet: '0', status: 'active' };

            // Current bet
            const betEl = player.querySelector('[class*=bet-value]');
            if (betEl) {
                const bm = betEl.textContent.match(/\\d+/);
                if (bm) p.bet = bm[0];
            }

            // Status text (fold, check, quitting, etc.)
            const statusTexts = ['Fold', 'check', 'Quitting', 'Away', 'Sitting Out'];
            player.querySelectorAll('p, div').forEach(el => {
                const t = el.textContent.trim();
                statusTexts.forEach(st => {
                    if (t.toLowerCase().includes(st.toLowerCase())) p.status = t;
                });
            });

            // Dealer button
            if (player.querySelector('[class*=dealer]')) p.dealer = true;

            // If this player has visible cards, it's us
            if (cards.length >= 2) {
                p.is_me = true;
                result.my_cards = cards;
            }

            result.players.push(p);
        });

        // Action buttons — .action-buttons container
        const actionArea = document.querySelector('.action-buttons');
        if (actionArea) {
            // "Your Turn" text means it's our action
            if (actionArea.textContent.includes('Your Turn')) {
                result.is_my_turn = true;
            }

            actionArea.querySelectorAll('button').forEach(btn => {
                if (btn.disabled) return;
                const text = btn.textContent.trim();
                if (text && !text.includes('Extra Time') && text.length < 30) {
                    result.actions.push(text);
                    // If we see Check/Call/Bet/Raise/Fold buttons, it's our turn
                    if (/Check|Call|Bet|Raise|Fold/i.test(text)) {
                        result.is_my_turn = true;
                    }
                }
            });
        }

        // Hand strength — look for text near our cards
        document.querySelectorAll('.table-player').forEach(p => {
            if (p.querySelector('a')?.textContent?.trim() && result.my_cards.length > 0) {
                p.querySelectorAll('div, span').forEach(el => {
                    const t = el.textContent.trim().toLowerCase();
                    const handTypes = ['flush', 'straight', 'pair', 'two pair', 'trips',
                        'full house', 'quads', 'high card', 'set', 'boat'];
                    handTypes.forEach(ht => {
                        if (t.includes(ht) && t.length < 30) result.my_hand_strength = el.textContent.trim();
                    });
                });
            }
        });

        // Chat (last 5 messages)
        document.querySelectorAll('[class*=chat-message-container]').forEach(msg => {
            const author = msg.querySelector('a')?.textContent?.trim() || 'System';
            const body = msg.querySelector('[class*=chat-message-body], [class*=message-text]');
            const text = body?.textContent?.trim() || msg.textContent?.trim()?.substring(0, 100) || '';
            if (text && result.chat.length < 5) result.chat.push(author + ': ' + text);
        });

        return result;
    }""")

    # Determine street from board count
    board_count = len(state.get("board", []))
    if board_count == 0:
        state["street"] = "preflop"
    elif board_count == 3:
        state["street"] = "flop"
    elif board_count == 4:
        state["street"] = "turn"
    elif board_count == 5:
        state["street"] = "river"

    return state


def state_to_text(state: dict) -> str:
    """Convert state dict to minimal text prompt for the LLM."""
    lines = []
    if state.get("game_type"):
        lines.append(f"Game: {state['game_type']}")

    lines.append(f"Street: {state.get('street', '?')}")

    if state.get("board"):
        lines.append(f"Board: {' '.join(state['board'])}")

    if state.get("my_cards"):
        lines.append(f"My cards: {' '.join(state['my_cards'])}")

    if state.get("my_hand_strength"):
        lines.append(f"Made hand: {state['my_hand_strength']}")

    pot_str = state.get("pot", "0")
    if state.get("pot_total"):
        pot_str = str(state["pot_total"])
    lines.append(f"Pot: {pot_str}")

    lines.append("Players:")
    for p in state.get("players", []):
        marker = " (ME)" if p.get("is_me") else ""
        dealer = " [D]" if p.get("dealer") else ""
        bet = f" bet:{p['bet']}" if p.get("bet") and p["bet"] != "0" else ""
        status = f" ({p['status']})" if p.get("status") and p["status"] not in ("active", "") else ""
        lines.append(f"  {p['name']}{marker}{dealer}: stack {p['stack']}{bet}{status}")

    if state.get("is_my_turn"):
        lines.append(f"\nMY TURN. Available: {', '.join(state.get('actions', []))}")
    else:
        lines.append("\nWaiting for opponent.")

    return "\n".join(lines)


async def get_state_text():
    """One-shot: connect, scrape, return text. For CLI use."""
    pw, page = await get_poker_page()
    state = await scrape_state(page)
    text = state_to_text(state)
    await pw.stop()
    return state, text


if __name__ == "__main__":
    state, text = asyncio.run(get_state_text())
    print(text)
    print("\n--- Raw JSON ---")
    print(json.dumps(state, indent=2))

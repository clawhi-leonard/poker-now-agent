"""
Poker Agent — LLM plays Poker Now in real-time.

Loop: scrape state → if my turn → call Claude with tools → execute action → repeat
Designed for minimum latency.
"""
import asyncio
import json
import time
import sys
import anthropic
from config import CDP_ENDPOINT, PLAYER_NAME, MODEL
from scrape import get_poker_page, scrape_state, state_to_text
from act import execute_action, send_chat

SYSTEM_PROMPT = """You are an expert Pot Limit Omaha (PLO) and No Limit Hold'em poker player sitting at an online table.

You will receive the current game state and must decide your action INSTANTLY.

## PLO Rules
- You have 4 hole cards. You MUST use exactly 2 hole cards + 3 board cards to make a hand.
- Pot Limit: maximum raise = current pot size.
- Stronger average hands than Hold'em — adjust accordingly.

## Strategy Guidelines
- **Preflop**: Play tight-aggressive. Premium hands: double-suited rundowns (e.g. JT98ds), high pairs with suits (AAxx suited), connected suited cards. Fold trash (disconnected, unsuited, danglers).
- **Postflop**: Bet/raise with nut hands and strong draws (13+ outs). Check/call with medium strength. Fold weak hands facing bets.
- **Position**: Play more hands in position (dealer/button). Tighter out of position.
- **Pot odds**: If pot odds > your equity to win, call. Otherwise fold.
- **Aggression**: When you bet/raise, size it to put pressure. Don't min-bet with monsters.
- **Bluffing**: Semi-bluff with big draws. Pure bluff rarely in PLO (opponents usually have something).

## Critical Rules
1. THINK FAST. You have seconds to act.
2. Call the take_action tool with your decision. ONE action per turn.
3. Be aggressive with strong hands/draws. Don't slow-play nuts.
4. In PLO, top pair alone is usually not strong enough to stack off.
5. Consider what the NUTS is on every board and whether you have it or a draw to it.

When evaluating your hand, remember PLO rules: enumerate which 2 of your 4 cards combine with the board to make the best hand."""

TOOLS = [
    {
        "name": "take_action",
        "description": "Execute a poker action at the table. Use 'check', 'fold', 'call', or 'raise'. For raise/bet, include the amount.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check", "fold", "call", "raise"],
                    "description": "The poker action to take"
                },
                "amount": {
                    "type": "integer",
                    "description": "Raise/bet amount (only for raise action)"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief reasoning for the action (1 sentence max)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_chat",
        "description": "Send a chat message to the table. Use sparingly for banter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Chat message to send"
                }
            },
            "required": ["message"]
        }
    }
]

client = anthropic.Anthropic()


async def decide_and_act(page, state: dict, state_text: str) -> str:
    """Send state to Claude, get tool call, execute it. Returns action taken."""
    t0 = time.time()

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=[
            {"role": "user", "content": f"GAME STATE:\n{state_text}\n\nDecide your action NOW. Use the take_action tool."}
        ]
    )

    api_ms = int((time.time() - t0) * 1000)

    # Extract tool use
    for block in response.content:
        if block.type == "tool_use":
            if block.name == "take_action":
                action = block.input.get("action", "check")
                amount = block.input.get("amount")
                reasoning = block.input.get("reasoning", "")

                result = await execute_action(page, action, amount)
                total_ms = int((time.time() - t0) * 1000)
                log = f"[{total_ms}ms | API:{api_ms}ms] {result}"
                if reasoning:
                    log += f" — {reasoning}"
                return log

            elif block.name == "send_chat":
                msg = block.input.get("message", "")
                result = await send_chat(page, msg)
                return f"[chat] {result}"

    # Fallback: if Claude responded with text instead of tool
    text_response = " ".join(b.text for b in response.content if hasattr(b, "text"))
    return f"[no action] Claude said: {text_response[:100]}"


async def run(poll_ms: int = 250, max_hands: int = 0):
    """
    Main loop. Polls game state every poll_ms.
    When it's our turn, calls Claude and acts.
    """
    print(f"🃏 Poker Agent starting | Player: {PLAYER_NAME} | Model: {MODEL}")
    print(f"   Poll interval: {poll_ms}ms | Max hands: {'∞' if max_hands == 0 else max_hands}")
    print(f"   Connecting to browser at {CDP_ENDPOINT}...")

    pw, page = await get_poker_page()
    print(f"   ✅ Connected to Poker Now tab")
    print(f"   Watching for our turn...\n")

    hands_played = 0
    last_action_street = None
    last_board = None
    was_my_turn = False

    try:
        while True:
            state = await scrape_state(page)
            board_key = tuple(state.get("board", []))

            # Detect new hand
            if board_key != last_board and state.get("street") == "preflop" and last_board is not None:
                hands_played += 1
                if max_hands and hands_played >= max_hands:
                    print(f"\n🏁 Played {hands_played} hands. Stopping.")
                    break
                last_action_street = None

            last_board = board_key

            if state.get("is_my_turn"):
                current_street = state.get("street")

                # Don't re-act on the same street (avoid double-acting)
                if current_street != last_action_street:
                    text = state_to_text(state)
                    print(f"📍 {current_street.upper()} | Board: {' '.join(state.get('board', ['--']))}")
                    print(f"   Cards: {' '.join(state.get('my_cards', []))}")
                    print(f"   Pot: {state.get('pot_total', state.get('pot', '?'))}")

                    result = await decide_and_act(page, state, text)
                    print(f"   → {result}\n")
                    last_action_street = current_street
                    was_my_turn = True

                    # Brief pause after acting to let DOM update
                    await asyncio.sleep(0.3)
                    continue
                else:
                    # Same street, still our turn — might be re-raised
                    # Re-scrape to check if the action buttons changed
                    if was_my_turn:
                        await asyncio.sleep(0.5)
                        state2 = await scrape_state(page)
                        if state2.get("is_my_turn"):
                            # Still our turn — opponent might have raised
                            text = state_to_text(state2)
                            print(f"📍 {current_street.upper()} (re-action) | Board: {' '.join(state2.get('board', ['--']))}")
                            result = await decide_and_act(page, state2, text)
                            print(f"   → {result}\n")
            else:
                was_my_turn = False

            await asyncio.sleep(poll_ms / 1000)

    except KeyboardInterrupt:
        print("\n👋 Stopping agent.")
    finally:
        await pw.stop()


if __name__ == "__main__":
    poll = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    max_h = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    asyncio.run(run(poll_ms=poll, max_hands=max_h))

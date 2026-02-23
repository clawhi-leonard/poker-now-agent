# Poker Now AI Agent

An LLM-powered poker player for [Poker Now](https://pokernow.com). Claude reads the game state from the browser and decides actions in real-time.

## How it works

```
Browser (Poker Now) → scrape.py reads DOM → agent.py sends state to Claude → Claude calls take_action tool → act.py clicks buttons
```

No hard-coded strategy. The LLM IS the brain.

## Setup

```bash
pip install playwright anthropic
playwright install chromium
export ANTHROPIC_API_KEY=sk-...
```

## Usage

```bash
# Start the agent (polls every 250ms, plays forever)
python agent.py

# Custom poll interval (100ms) and limit (50 hands)
python agent.py 100 50

# Just read current state
python scrape.py
```

## Requirements
- A Poker Now game open in a browser with CDP enabled (port 18800)
- Anthropic API key
- You must already be seated at the table

## Files
- `agent.py` — Main loop: poll → detect turn → call Claude → act
- `scrape.py` — DOM → structured game state
- `act.py` — Execute actions via keyboard shortcuts
- `config.py` — CDP endpoint, player name, model

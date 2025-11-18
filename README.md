# Sports Betting Edge Toolkit

The most comprehensive sports betting analytics suite for Slovak bettors. Track +EV opportunities, arbitrage, CLV, bankroll management, and more.

## Features

- **Live Odds Scraping**: Tipsport, Fortuna, Niké, DOXXbet, Pinnacle, Bet365
- **+EV Detection**: Compare soft books against sharp (Pinnacle) odds
- **Arbitrage Scanner**: Find guaranteed profit surebets
- **CLV Tracker**: Track Closing Line Value (the best predictor of long-term profit)
- **Kelly Criterion**: Optimal stake sizing with risk management
- **Bonus Hunter**: Rollover optimizer for Slovak bookmaker bonuses
- **Telegram Bot**: Instant notifications for opportunities
- **Full Dashboard**: Streamlit-based analytics interface
- **CSV Import**: Import history from Tipsport/Niké exports

## Quick Start

### 1. Install Dependencies

```bash
# Clone the repository
git clone https://github.com/yourusername/Sports-Betting-Edge-Toolkit.git
cd Sports-Betting-Edge-Toolkit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install requirements
pip install -r requirements.txt

# Install Playwright browsers (for Pinnacle/Bet365)
playwright install chromium
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

Add your Telegram bot credentials:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Run the Dashboard

```bash
python run.py dashboard
```

Open http://localhost:8501 in your browser.

### 4. Run the Scanner

```bash
# Single scan
python run.py scan

# Continuous monitoring (24/7)
python run.py monitor --interval 60

# With Telegram notifications
python run.py scan --min-ev 2.0
```

## Detailed Setup Guide

### System Requirements

- Python 3.9+
- 4GB RAM minimum
- Chrome/Chromium (for Pinnacle/Bet365 scraping)

### Setting Up Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token to `.env`
4. Get your chat ID:
   - Message @userinfobot
   - Copy the ID to `.env`

### For Slovak Bookmakers

Tipsport, Fortuna, Niké, and DOXXbet work without authentication for basic odds scraping. For full features, add credentials to `.env`.

### For Pinnacle/Bet365 (VPN Required)

These books may require VPN from Slovakia. The toolkit uses Playwright for browser automation since they block standard requests.

## Usage Examples

### Finding +EV Opportunities

```python
from src.scrapers.odds_aggregator import OddsAggregator
from src.analyzers.ev_calculator import EVCalculator
import asyncio

async def find_value():
    # Scrape all books
    aggregator = OddsAggregator()
    events = await aggregator.scrape_all('football')

    all_events = events.get('football', [])

    # Find +EV
    calculator = EVCalculator({'min_ev_percentage': 2.0})
    opportunities = calculator.find_ev_opportunities(all_events)

    for opp in opportunities:
        print(f"+{opp.ev_percentage:.1f}% EV: {opp.event.home_team} vs {opp.event.away_team}")
        print(f"  {opp.selection} @ {opp.offered_odds} ({opp.bookmaker})")
        print(f"  Recommended stake: €{opp.recommended_stake}")

asyncio.run(find_value())
```

### Kelly Stake Calculator

```python
from src.bankroll.kelly_criterion import BankrollManager

bm = BankrollManager()
bm.set_bankroll(1000)  # €1000 starting bankroll

# Calculate optimal stake
recommendation = bm.calculate_stake(
    probability=0.55,  # 55% true probability
    odds=2.10,         # Decimal odds
    kelly_fraction=0.25  # Quarter Kelly
)

print(f"Recommended stake: €{recommendation.recommended}")
print(f"EV: {recommendation.ev_percentage}%")
```

### Import Betting History

```python
from src.importers.tipsport_importer import TipsportImporter
from src.database.db_manager import DatabaseManager

db = DatabaseManager()
importer = TipsportImporter(db)

# Import from Tipsport CSV export
count = importer.import_tipsport_csv('my_tipsport_history.csv')
print(f"Imported {count} bets")
```

### Track Bonuses

```python
from src.bonus.rollover_optimizer import BonusHunter, RolloverOptimizer

optimizer = RolloverOptimizer()

# Evaluate a bonus
ev = optimizer.calculate_bonus_ev(
    bonus_amount=100,        # €100 bonus
    wagering_requirement=5,  # 5x rollover
    max_odds=1.50           # Max odds for rollover
)

print(f"Expected value: €{ev['expected_value']:.2f}")
print(f"Profitable: {ev['is_profitable']}")
```

## Running 24/7 (Cheap)

### Option 1: Old Laptop (Free)

1. Install Ubuntu Server or use existing OS
2. Clone repo and install dependencies
3. Run with screen/tmux:

```bash
screen -S betting
python run.py monitor
# Press Ctrl+A, D to detach
```

### Option 2: Raspberry Pi (~€50)

Perfect for 24/7 operation with minimal power consumption.

```bash
# On Raspberry Pi
sudo apt update
sudo apt install python3-pip chromium-browser

pip install -r requirements.txt
python run.py monitor
```

### Option 3: VPS (€5-10/month)

- Hetzner Cloud: €3.79/month
- DigitalOcean: $6/month
- Contabo: €4.99/month

```bash
# Setup on VPS
ssh root@your-vps-ip
git clone https://github.com/yourusername/Sports-Betting-Edge-Toolkit.git
cd Sports-Betting-Edge-Toolkit
pip install -r requirements.txt

# Run with systemd
sudo nano /etc/systemd/system/betting-edge.service
```

Create systemd service:
```ini
[Unit]
Description=Sports Betting Edge Scanner
After=network.target

[Service]
User=root
WorkingDirectory=/root/Sports-Betting-Edge-Toolkit
ExecStart=/usr/bin/python3 run.py monitor
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable betting-edge
sudo systemctl start betting-edge
```

## Understanding the Metrics

### Expected Value (EV)

EV = (Win Probability × Win Amount) - (Loss Probability × Stake)

Positive EV means profitable long-term. We calculate true probability from Pinnacle odds.

### Closing Line Value (CLV)

CLV = (Closing Odds Probability - Bet Odds Probability) / Bet Odds Probability × 100

**The single most important metric.** Consistently beating the closing line = long-term profit.

### Kelly Criterion

Kelly % = (Win Probability × Odds - 1) / (Odds - 1)

Use fractional Kelly (25%) for lower variance.

## Project Structure

```
Sports-Betting-Edge-Toolkit/
├── config/
│   ├── config.yaml          # Main configuration
│   └── bookmakers.yaml      # Bookmaker settings
├── src/
│   ├── scrapers/            # Odds scrapers
│   ├── analyzers/           # EV, CLV, Arb calculators
│   ├── bankroll/            # Kelly & bankroll management
│   ├── bonus/               # Bonus tracking
│   ├── notifications/       # Telegram bot
│   ├── database/            # SQLite database
│   ├── importers/           # CSV importers
│   └── utils/               # Odds conversion, etc.
├── dashboard/
│   └── app.py               # Streamlit dashboard
├── scripts/
│   ├── run_scraper.py
│   ├── run_scanner.py
│   └── run_dashboard.py
├── data/                    # Database & imports
├── run.py                   # Main entry point
├── requirements.txt
└── README.md
```

## Slovak Bookmaker Notes

### Tipsport
- Largest Slovak book
- Good for live betting
- Typical bonus: 5x rollover, max 1.50 odds

### Fortuna
- Part of Fortuna Entertainment Group
- Good markets for Slovak/Czech leagues
- Bonus: 6x rollover, max 1.40 odds

### Niké
- Popular for Superodds
- 5x rollover, max 1.50 odds

### DOXXbet
- Lower limits but softer odds
- Best for bonus hunting
- 4x rollover, max 1.60 odds

## Tips for Success

1. **Always check CLV** - It's the best predictor of skill
2. **Use fractional Kelly** - Never full Kelly (too volatile)
3. **Line shop aggressively** - Get accounts at all books
4. **Track everything** - Import all your history
5. **Focus on what you know** - Slovak/Czech leagues where you have edge
6. **Act fast on +EV** - Odds move quickly
7. **Don't chase losses** - Stick to Kelly sizing

## Troubleshooting

### "No odds data retrieved"

- Check internet connection
- Some books may block requests; try with VPN
- Pinnacle/Bet365 require browser automation

### "Playwright error"

```bash
playwright install chromium
```

### "Database locked"

Close the dashboard before running other scripts.

### "Telegram not sending"

- Verify bot token and chat ID in `.env`
- Message your bot first to activate it

## Legal Notice

This toolkit is for informational and personal use only. Ensure sports betting is legal in your jurisdiction. The authors are not responsible for any losses incurred.

## Contributing

Pull requests welcome! Please read the contribution guidelines first.

## License

MIT License - see LICENSE file.

---

**Good luck! May you always beat the closing line.** 🎲📈

"""
Telegram Bot
============

Sends notifications for +EV opportunities, arbitrage, and more.
"""

import asyncio
import logging
from datetime import datetime, time
from typing import List, Optional
import os

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ..analyzers.ev_calculator import EVOpportunity
from ..analyzers.arbitrage_finder import ArbitrageOpportunity


class TelegramNotifier:
    """
    Sends Telegram notifications for betting opportunities.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("TelegramNotifier")

        # Get credentials from config or environment
        self.bot_token = self.config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = self.config.get('chat_id') or os.getenv('TELEGRAM_CHAT_ID')

        if not self.bot_token or not self.chat_id:
            self.logger.warning("Telegram credentials not configured")
            self.enabled = False
        else:
            self.enabled = True
            self.bot = Bot(token=self.bot_token)

        # Quiet hours
        self.quiet_hours = self.config.get('quiet_hours', {})

    def _is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours."""
        if not self.quiet_hours.get('enabled', False):
            return False

        now = datetime.now().time()
        start = datetime.strptime(self.quiet_hours.get('start', '23:00'), '%H:%M').time()
        end = datetime.strptime(self.quiet_hours.get('end', '07:00'), '%H:%M').time()

        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    async def send_message(self, message: str, parse_mode: str = 'HTML'):
        """Send a message to Telegram."""
        if not self.enabled:
            self.logger.debug("Telegram not enabled, skipping message")
            return

        if self._is_quiet_hours():
            self.logger.debug("In quiet hours, skipping notification")
            return

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            self.logger.info("Telegram message sent")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")

    def send_message_sync(self, message: str, parse_mode: str = 'HTML'):
        """Synchronous wrapper for sending messages."""
        asyncio.run(self.send_message(message, parse_mode))

    async def notify_ev_opportunity(self, opportunity: EVOpportunity):
        """Send notification for +EV opportunity."""
        message = self._format_ev_message(opportunity)
        await self.send_message(message)

    async def notify_arbitrage(self, opportunity: ArbitrageOpportunity):
        """Send notification for arbitrage opportunity."""
        message = self._format_arb_message(opportunity)
        await self.send_message(message)

    async def notify_multiple_ev(self, opportunities: List[EVOpportunity]):
        """Send summary notification for multiple opportunities."""
        if not opportunities:
            return

        message = f"<b>🎯 {len(opportunities)} +EV Opportunities Found!</b>\n\n"

        for i, opp in enumerate(opportunities[:5], 1):
            message += (
                f"{i}. <b>+{opp.ev_percentage:.1f}% EV</b>\n"
                f"   {opp.event.home_team} vs {opp.event.away_team}\n"
                f"   {opp.selection} @ {opp.offered_odds} ({opp.bookmaker})\n"
                f"   Stake: €{opp.recommended_stake}\n\n"
            )

        if len(opportunities) > 5:
            message += f"<i>...and {len(opportunities) - 5} more</i>\n"

        message += f"\n<code>Total potential stake: €{sum(o.recommended_stake for o in opportunities):.2f}</code>"

        await self.send_message(message)

    async def notify_clv_beat(self, bet_info: dict):
        """Notify when a bet beats the closing line."""
        clv = bet_info.get('clv', 0)
        if clv <= 0:
            return

        message = (
            f"<b>✅ CLV Beat!</b>\n\n"
            f"Event: {bet_info.get('event', 'Unknown')}\n"
            f"Selection: {bet_info.get('selection', 'Unknown')}\n"
            f"Bet odds: {bet_info.get('bet_odds', 0)}\n"
            f"Closing odds: {bet_info.get('closing_odds', 0)}\n"
            f"<b>CLV: +{clv:.1f}%</b>"
        )

        await self.send_message(message)

    async def notify_bankroll_milestone(self, current: float, milestone: str):
        """Notify on bankroll milestones."""
        message = (
            f"<b>🎉 Bankroll Milestone!</b>\n\n"
            f"{milestone}\n"
            f"Current bankroll: <b>€{current:.2f}</b>"
        )

        await self.send_message(message)

    async def notify_bonus_completed(self, bookmaker: str, profit: float):
        """Notify when bonus rollover is completed."""
        emoji = "🎊" if profit > 0 else "📊"
        message = (
            f"<b>{emoji} Bonus Completed!</b>\n\n"
            f"Bookmaker: {bookmaker}\n"
            f"Profit: <b>€{profit:.2f}</b>"
        )

        await self.send_message(message)

    def _format_ev_message(self, opp: EVOpportunity) -> str:
        """Format EV opportunity message."""
        confidence_emoji = {
            'high': '🔥',
            'medium': '📈',
            'low': '📊'
        }.get(opp.confidence, '📊')

        return (
            f"<b>{confidence_emoji} +EV Opportunity!</b>\n\n"
            f"<b>{opp.event.home_team}</b> vs <b>{opp.event.away_team}</b>\n"
            f"League: {opp.event.league}\n"
            f"Time: {opp.event.start_time.strftime('%H:%M %d/%m')}\n\n"
            f"Selection: <b>{opp.selection}</b>\n"
            f"Odds: <b>{opp.offered_odds}</b> ({opp.bookmaker})\n"
            f"Sharp odds: {opp.sharp_odds}\n\n"
            f"<b>EV: +{opp.ev_percentage:.1f}%</b>\n"
            f"Edge: {opp.edge:.1f}%\n"
            f"True prob: {opp.true_probability*100:.1f}%\n\n"
            f"Recommended stake: <b>€{opp.recommended_stake}</b>\n"
            f"Kelly: {opp.kelly_stake*100:.1f}%\n"
            f"Confidence: {opp.confidence.upper()}"
        )

    def _format_arb_message(self, opp: ArbitrageOpportunity) -> str:
        """Format arbitrage message."""
        message = (
            f"<b>💰 Arbitrage Found!</b>\n\n"
            f"<b>{opp.event.home_team}</b> vs <b>{opp.event.away_team}</b>\n"
            f"Time: {opp.event.start_time.strftime('%H:%M %d/%m')}\n\n"
            f"<b>Profit: {opp.profit_percentage:.2f}%</b>\n"
            f"Guaranteed: <b>€{opp.guaranteed_profit:.2f}</b>\n\n"
            f"<u>Stakes:</u>\n"
        )

        for leg in opp.legs:
            message += (
                f"• {leg.selection} @ {leg.odds} ({leg.bookmaker})\n"
                f"  Stake: €{leg.stake}\n"
            )

        message += f"\n<code>Total stake: €{opp.total_stake}</code>"

        return message


class BettingBot:
    """
    Interactive Telegram bot for betting management.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("BettingBot")

        self.bot_token = self.config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')

        if not self.bot_token:
            self.logger.warning("Bot token not configured")
            return

        # Build application
        self.app = Application.builder().token(self.bot_token).build()

        # Add handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register command handlers."""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("bankroll", self.cmd_bankroll))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("ev", self.cmd_ev))
        self.app.add_handler(CommandHandler("arb", self.cmd_arb))
        self.app.add_handler(CommandHandler("bonus", self.cmd_bonus))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "<b>🎲 Sports Betting Edge Bot</b>\n\n"
            "I'll notify you of +EV opportunities and arbitrage.\n\n"
            "Commands:\n"
            "/help - Show all commands\n"
            "/bankroll - Current bankroll\n"
            "/stats - Betting statistics\n"
            "/ev - Find +EV opportunities\n"
            "/arb - Find arbitrage\n"
            "/bonus - Bonus status",
            parse_mode='HTML'
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await update.message.reply_text(
            "<b>Available Commands:</b>\n\n"
            "/bankroll - Show current bankroll and stats\n"
            "/stats - Show betting statistics\n"
            "/ev - Scan for +EV opportunities\n"
            "/arb - Scan for arbitrage\n"
            "/bonus - Show bonus rollover status\n"
            "/clv - Show CLV analysis\n"
            "/quiet - Toggle quiet hours",
            parse_mode='HTML'
        )

    async def cmd_bankroll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bankroll command."""
        # Would get from database
        await update.message.reply_text(
            "<b>💰 Bankroll Status</b>\n\n"
            "Current: €1,000.00\n"
            "P/L: +€150.00\n"
            "ROI: +15.0%\n"
            "Max DD: 8.5%",
            parse_mode='HTML'
        )

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        await update.message.reply_text(
            "<b>📊 Betting Statistics</b>\n\n"
            "Total bets: 150\n"
            "Win rate: 52.3%\n"
            "Avg odds: 1.95\n"
            "Avg CLV: +1.8%\n"
            "ROI: +8.5%",
            parse_mode='HTML'
        )

    async def cmd_ev(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ev command."""
        await update.message.reply_text(
            "🔍 Scanning for +EV opportunities...\n"
            "This may take a minute.",
            parse_mode='HTML'
        )
        # Would trigger scan

    async def cmd_arb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /arb command."""
        await update.message.reply_text(
            "🔍 Scanning for arbitrage...\n"
            "This may take a minute.",
            parse_mode='HTML'
        )
        # Would trigger scan

    async def cmd_bonus(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bonus command."""
        await update.message.reply_text(
            "<b>🎁 Bonus Status</b>\n\n"
            "No active bonuses.\n\n"
            "Add bonus with:\n"
            "/addbonus [book] [amount] [rollover]",
            parse_mode='HTML'
        )

    def run(self):
        """Run the bot."""
        self.logger.info("Starting Telegram bot...")
        self.app.run_polling()


async def test_notifications():
    """Test notification sending."""
    config = {
        'bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
        'chat_id': os.getenv('TELEGRAM_CHAT_ID')
    }

    notifier = TelegramNotifier(config)

    await notifier.send_message(
        "<b>Test Notification</b>\n\n"
        "Sports Betting Edge Toolkit is running! ✅"
    )


if __name__ == "__main__":
    asyncio.run(test_notifications())

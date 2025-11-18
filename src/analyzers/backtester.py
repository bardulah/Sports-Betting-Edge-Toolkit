"""
Backtesting Module
==================

Backtest betting strategies on historical data.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np

from ..database.db_manager import DatabaseManager
from ..utils.probability_utils import ProbabilityUtils
from ..utils.odds_converter import OddsConverter
from ..bankroll.kelly_criterion import KellyCalculator

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results of a backtest."""
    total_bets: int
    wins: int
    losses: int
    win_rate: float
    total_staked: float
    total_returned: float
    profit_loss: float
    roi: float
    max_drawdown: float
    sharpe_ratio: float
    avg_odds: float
    avg_ev: float
    final_bankroll: float
    bankroll_history: List[float]


class Backtester:
    """
    Backtest betting strategies on historical odds data.
    """

    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager or DatabaseManager()
        self.logger = logging.getLogger("Backtester")

    def backtest_ev_strategy(
        self,
        start_date: datetime,
        end_date: datetime,
        min_ev: float = 2.0,
        kelly_fraction: float = 0.25,
        initial_bankroll: float = 1000,
        max_bet_pct: float = 0.05
    ) -> BacktestResult:
        """
        Backtest a +EV betting strategy on historical data.

        Args:
            start_date: Start of backtest period
            end_date: End of backtest period
            min_ev: Minimum EV percentage to bet
            kelly_fraction: Kelly fraction to use
            initial_bankroll: Starting bankroll
            max_bet_pct: Maximum bet as % of bankroll

        Returns:
            BacktestResult with performance metrics
        """
        self.logger.info(f"Backtesting EV strategy: {min_ev}%+ EV, {kelly_fraction} Kelly")

        # Get historical EV opportunities
        opportunities = self._get_historical_opportunities(start_date, end_date, min_ev)

        if not opportunities:
            self.logger.warning("No historical opportunities found")
            return self._empty_result(initial_bankroll)

        # Simulate betting
        bankroll = initial_bankroll
        bankroll_history = [bankroll]

        bets = []
        total_staked = 0
        total_returned = 0

        for opp in opportunities:
            # Calculate stake
            true_prob = opp.get('true_probability', 0.5)
            odds = opp.get('offered_odds', 2.0)

            kelly = KellyCalculator.fractional_kelly(true_prob, odds, kelly_fraction)
            stake = min(kelly * bankroll, bankroll * max_bet_pct)
            stake = max(stake, 1)  # Minimum bet

            if stake > bankroll:
                continue

            # Simulate result based on true probability
            # In real backtest, we'd use actual results from DB
            result = self._get_actual_result(opp)

            if result == 'won':
                profit = stake * (odds - 1)
                bankroll += profit
                total_returned += stake + profit
            else:
                bankroll -= stake
                total_returned += 0

            total_staked += stake
            bankroll_history.append(bankroll)

            bets.append({
                'stake': stake,
                'odds': odds,
                'result': result,
                'profit': profit if result == 'won' else -stake
            })

        # Calculate metrics
        wins = len([b for b in bets if b['result'] == 'won'])
        losses = len(bets) - wins

        profit_loss = total_returned - total_staked
        roi = (profit_loss / total_staked * 100) if total_staked > 0 else 0

        max_dd, _, _ = ProbabilityUtils.max_drawdown(bankroll_history)

        # Sharpe ratio
        returns = [b['profit'] / b['stake'] for b in bets]
        sharpe = ProbabilityUtils.sharpe_ratio(returns) if returns else 0

        avg_odds = sum(b['odds'] for b in bets) / len(bets) if bets else 0
        avg_ev = sum(opp.get('ev_percentage', 0) for opp in opportunities) / len(opportunities)

        return BacktestResult(
            total_bets=len(bets),
            wins=wins,
            losses=losses,
            win_rate=round((wins / len(bets) * 100) if bets else 0, 2),
            total_staked=round(total_staked, 2),
            total_returned=round(total_returned, 2),
            profit_loss=round(profit_loss, 2),
            roi=round(roi, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            avg_odds=round(avg_odds, 3),
            avg_ev=round(avg_ev, 2),
            final_bankroll=round(bankroll, 2),
            bankroll_history=bankroll_history
        )

    def _get_historical_opportunities(
        self,
        start_date: datetime,
        end_date: datetime,
        min_ev: float
    ) -> List[dict]:
        """Get historical EV opportunities from database."""
        with self.db.get_session() as session:
            from ..database.models import EVOpportunity

            opps = session.query(EVOpportunity).filter(
                EVOpportunity.detected_at >= start_date,
                EVOpportunity.detected_at <= end_date,
                EVOpportunity.ev_percentage >= min_ev
            ).order_by(EVOpportunity.detected_at).all()

            return [{
                'id': o.id,
                'event_id': o.event_id,
                'bookmaker': o.bookmaker,
                'selection': o.selection,
                'offered_odds': o.offered_odds,
                'true_probability': o.true_probability,
                'ev_percentage': o.ev_percentage,
                'start_time': o.start_time
            } for o in opps]

    def _get_actual_result(self, opportunity: dict) -> str:
        """
        Get actual result of an opportunity.

        In a full implementation, this would:
        1. Look up the event result in DB
        2. Return 'won' or 'lost'

        For now, simulate based on true probability.
        """
        true_prob = opportunity.get('true_probability', 0.5)
        return 'won' if np.random.random() < true_prob else 'lost'

    def _empty_result(self, initial_bankroll: float) -> BacktestResult:
        """Return empty result."""
        return BacktestResult(
            total_bets=0, wins=0, losses=0, win_rate=0,
            total_staked=0, total_returned=0, profit_loss=0,
            roi=0, max_drawdown=0, sharpe_ratio=0,
            avg_odds=0, avg_ev=0, final_bankroll=initial_bankroll,
            bankroll_history=[initial_bankroll]
        )

    def monte_carlo_simulation(
        self,
        win_prob: float,
        avg_odds: float,
        kelly_fraction: float,
        initial_bankroll: float,
        num_bets: int,
        simulations: int = 1000
    ) -> dict:
        """
        Monte Carlo simulation of strategy performance.
        """
        return ProbabilityUtils.simulate_bankroll(
            win_prob, avg_odds, kelly_fraction,
            initial_bankroll, num_bets, simulations
        )

    def compare_strategies(
        self,
        start_date: datetime,
        end_date: datetime,
        strategies: List[dict]
    ) -> pd.DataFrame:
        """
        Compare multiple betting strategies.

        Args:
            start_date: Start date
            end_date: End date
            strategies: List of strategy configs
                [{'name': 'Conservative', 'min_ev': 3.0, 'kelly': 0.25}, ...]

        Returns:
            DataFrame comparing results
        """
        results = []

        for strategy in strategies:
            result = self.backtest_ev_strategy(
                start_date, end_date,
                min_ev=strategy.get('min_ev', 2.0),
                kelly_fraction=strategy.get('kelly', 0.25),
                initial_bankroll=strategy.get('bankroll', 1000),
                max_bet_pct=strategy.get('max_bet', 0.05)
            )

            results.append({
                'Strategy': strategy.get('name', 'Unknown'),
                'Min EV': strategy.get('min_ev'),
                'Kelly': strategy.get('kelly'),
                'Total Bets': result.total_bets,
                'Win Rate': f"{result.win_rate}%",
                'ROI': f"{result.roi}%",
                'P/L': f"€{result.profit_loss}",
                'Max DD': f"{result.max_drawdown}%",
                'Sharpe': result.sharpe_ratio,
                'Final': f"€{result.final_bankroll}"
            })

        return pd.DataFrame(results)

    def analyze_odds_movements(
        self,
        event_id: int
    ) -> pd.DataFrame:
        """
        Analyze odds movements for an event.

        Returns DataFrame with odds history for all bookmakers.
        """
        with self.db.get_session() as session:
            from ..database.models import OddsHistory

            records = session.query(OddsHistory).filter(
                OddsHistory.event_id == event_id
            ).order_by(OddsHistory.timestamp).all()

            data = []
            for r in records:
                data.append({
                    'timestamp': r.timestamp,
                    'bookmaker': r.bookmaker,
                    'selection': r.selection,
                    'odds': r.odds_value
                })

            return pd.DataFrame(data)

    def detect_steam_moves(
        self,
        start_date: datetime,
        end_date: datetime,
        min_movement_pct: float = 5.0
    ) -> List[dict]:
        """
        Detect significant odds movements (steam moves).

        Steam moves indicate sharp money and are often +EV.
        """
        steam_moves = []

        with self.db.get_session() as session:
            from ..database.models import OddsHistory, Event

            events = session.query(Event).filter(
                Event.start_time >= start_date,
                Event.start_time <= end_date
            ).all()

            for event in events:
                # Get odds history
                history = session.query(OddsHistory).filter(
                    OddsHistory.event_id == event.id
                ).order_by(OddsHistory.timestamp).all()

                # Group by bookmaker + selection
                grouped = {}
                for h in history:
                    key = (h.bookmaker, h.selection)
                    if key not in grouped:
                        grouped[key] = []
                    grouped[key].append(h.odds_value)

                # Check for movements
                for (bookmaker, selection), odds_list in grouped.items():
                    if len(odds_list) < 2:
                        continue

                    initial = odds_list[0]
                    final = odds_list[-1]

                    movement_pct = abs((final - initial) / initial * 100)

                    if movement_pct >= min_movement_pct:
                        steam_moves.append({
                            'event': f"{event.home_team} vs {event.away_team}",
                            'bookmaker': bookmaker,
                            'selection': selection,
                            'initial_odds': initial,
                            'final_odds': final,
                            'movement_pct': round(movement_pct, 2),
                            'direction': 'shortened' if final < initial else 'lengthened'
                        })

        return sorted(steam_moves, key=lambda x: x['movement_pct'], reverse=True)

"""
Kelly Criterion & Bankroll Manager
==================================

Optimal stake sizing using Kelly criterion with bankroll tracking.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
import pandas as pd
import numpy as np

from ..utils.probability_utils import ProbabilityUtils
from ..database.db_manager import DatabaseManager


@dataclass
class StakeRecommendation:
    """Recommended stake for a bet."""
    full_kelly: float
    half_kelly: float
    quarter_kelly: float
    recommended: float
    fraction_used: float
    max_allowed: float
    bankroll: float
    ev_percentage: float
    risk_of_ruin: float


class KellyCalculator:
    """
    Calculates optimal stake sizes using Kelly criterion.
    """

    @staticmethod
    def full_kelly(probability: float, odds: float) -> float:
        """Calculate full Kelly stake fraction."""
        return ProbabilityUtils.kelly_criterion(probability, odds)

    @staticmethod
    def fractional_kelly(
        probability: float,
        odds: float,
        fraction: float = 0.25
    ) -> float:
        """Calculate fractional Kelly stake."""
        return ProbabilityUtils.fractional_kelly(probability, odds, fraction)

    @staticmethod
    def optimal_fraction(
        win_rate: float,
        avg_odds: float,
        risk_tolerance: str = 'medium'
    ) -> float:
        """
        Suggest optimal Kelly fraction based on historical performance.

        Args:
            win_rate: Historical win rate
            avg_odds: Average odds bet
            risk_tolerance: 'low', 'medium', 'high'

        Returns:
            Recommended Kelly fraction
        """
        # Base fraction on risk tolerance
        base_fractions = {
            'low': 0.125,    # Eighth Kelly
            'medium': 0.25,  # Quarter Kelly
            'high': 0.5      # Half Kelly
        }

        fraction = base_fractions.get(risk_tolerance, 0.25)

        # Adjust based on edge confidence
        expected_edge = (win_rate * (avg_odds - 1)) - (1 - win_rate)

        if expected_edge < 0.02:
            fraction *= 0.5  # Very small edge, be conservative
        elif expected_edge > 0.1:
            fraction *= 1.2  # Strong edge, can be more aggressive

        return min(fraction, 0.5)  # Cap at half Kelly

    @staticmethod
    def simultaneous_kelly(bets: List[Dict]) -> List[float]:
        """
        Calculate Kelly stakes for simultaneous bets.

        Accounts for correlation and bankroll constraints.

        Args:
            bets: List of {'probability': p, 'odds': o} dicts

        Returns:
            List of stake fractions
        """
        if not bets:
            return []

        # Calculate individual Kellys
        individual = [
            ProbabilityUtils.kelly_criterion(b['probability'], b['odds'])
            for b in bets
        ]

        # Sum of Kellys shouldn't exceed 1
        total = sum(individual)

        if total <= 1:
            return individual

        # Scale down proportionally
        scale = 0.8 / total  # Keep some buffer
        return [k * scale for k in individual]


class BankrollManager:
    """
    Manages bankroll tracking, stake sizing, and risk management.
    """

    def __init__(self, db_manager: DatabaseManager = None, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("BankrollManager")

        self.db = db_manager or DatabaseManager()

        # Configuration
        self.initial_bankroll = self.config.get('initial_bankroll', 1000)
        self.kelly_fraction = self.config.get('kelly_fraction', 0.25)
        self.max_bet_pct = self.config.get('max_bet_percentage', 0.05)
        self.min_bet = self.config.get('min_bet_amount', 1)

    def get_current_bankroll(self) -> float:
        """Get current bankroll from database."""
        return self.db.get_current_bankroll()

    def calculate_stake(
        self,
        probability: float,
        odds: float,
        kelly_fraction: float = None
    ) -> StakeRecommendation:
        """
        Calculate recommended stake for a bet.

        Args:
            probability: True probability of winning
            odds: Decimal odds
            kelly_fraction: Override default Kelly fraction

        Returns:
            StakeRecommendation with all calculations
        """
        bankroll = self.get_current_bankroll()
        fraction = kelly_fraction or self.kelly_fraction

        # Calculate different Kelly stakes
        full = KellyCalculator.full_kelly(probability, odds)
        half = full * 0.5
        quarter = full * 0.25

        # Use specified fraction
        kelly_stake = full * fraction

        # Apply max constraint
        max_stake = bankroll * self.max_bet_pct
        recommended = min(kelly_stake * bankroll, max_stake)
        recommended = max(recommended, 0)  # No negative stakes

        # Round to reasonable amount
        recommended = round(recommended, 2)

        # Calculate EV
        ev_pct = ProbabilityUtils.calculate_ev_percentage(probability, odds)

        # Estimate risk of ruin
        ror = self._estimate_risk_of_ruin(probability, odds, kelly_stake)

        return StakeRecommendation(
            full_kelly=round(full * bankroll, 2),
            half_kelly=round(half * bankroll, 2),
            quarter_kelly=round(quarter * bankroll, 2),
            recommended=recommended,
            fraction_used=fraction,
            max_allowed=round(max_stake, 2),
            bankroll=bankroll,
            ev_percentage=ev_pct,
            risk_of_ruin=ror
        )

    def _estimate_risk_of_ruin(
        self,
        probability: float,
        odds: float,
        bet_fraction: float
    ) -> float:
        """Estimate probability of ruin."""
        return ProbabilityUtils.ruin_probability(
            probability, odds, bet_fraction, target_multiple=2.0
        )

    def record_bet(
        self,
        stake: float,
        odds: float,
        result: str = 'pending',
        actual_return: float = 0
    ):
        """
        Record a bet and update bankroll.

        Args:
            stake: Amount staked
            odds: Decimal odds
            result: 'pending', 'won', 'lost'
            actual_return: Amount returned (for won bets)
        """
        bankroll = self.get_current_bankroll()

        if result == 'pending':
            # Just record the stake
            new_bankroll = bankroll - stake
        elif result == 'won':
            new_bankroll = bankroll - stake + actual_return
        elif result == 'lost':
            new_bankroll = bankroll - stake
        else:
            new_bankroll = bankroll

        # This would update via database
        profit_loss = actual_return - stake if result in ['won', 'lost'] else 0

        self.logger.info(
            f"Bet recorded: Stake €{stake}, Result: {result}, P/L: €{profit_loss}"
        )

    def get_bankroll_stats(self) -> dict:
        """Get comprehensive bankroll statistics."""
        history = self.db.get_bankroll_history()
        current = self.get_current_bankroll()
        initial = self.initial_bankroll

        if history.empty:
            return {
                'current': current,
                'initial': initial,
                'profit_loss': current - initial,
                'roi_pct': 0,
                'max_drawdown': 0
            }

        bankroll_values = history['bankroll'].tolist()

        # Calculate stats
        profit_loss = current - initial
        roi = (profit_loss / initial) * 100 if initial > 0 else 0

        # Max drawdown
        max_dd, peak_idx, trough_idx = ProbabilityUtils.max_drawdown(bankroll_values)

        # Peak and current drawdown
        peak = max(bankroll_values)
        current_dd = ((peak - current) / peak) * 100 if peak > 0 else 0

        return {
            'current': round(current, 2),
            'initial': initial,
            'profit_loss': round(profit_loss, 2),
            'roi_pct': round(roi, 2),
            'peak': round(peak, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'current_drawdown_pct': round(current_dd, 2),
            'num_records': len(bankroll_values)
        }

    def get_bankroll_chart_data(self) -> pd.DataFrame:
        """Get data for bankroll chart."""
        return self.db.get_bankroll_history()

    def simulate_future(
        self,
        win_prob: float,
        avg_odds: float,
        num_bets: int,
        simulations: int = 1000
    ) -> dict:
        """
        Monte Carlo simulation of future bankroll.

        Args:
            win_prob: Expected win probability
            avg_odds: Average odds
            num_bets: Number of future bets
            simulations: Number of simulations

        Returns:
            Simulation statistics
        """
        bankroll = self.get_current_bankroll()
        bet_fraction = self.kelly_fraction * KellyCalculator.full_kelly(win_prob, avg_odds)
        bet_fraction = min(bet_fraction, self.max_bet_pct)

        return ProbabilityUtils.simulate_bankroll(
            win_prob, avg_odds, bet_fraction, bankroll, num_bets, simulations
        )

    def get_recommended_unit_size(self) -> float:
        """Get recommended unit size based on current bankroll."""
        bankroll = self.get_current_bankroll()
        # 1% of bankroll is typical unit size
        return round(bankroll * 0.01, 2)

    def set_bankroll(self, amount: float):
        """Set/update current bankroll."""
        self.db.set_initial_bankroll(amount)
        self.logger.info(f"Bankroll set to €{amount}")

    def deposit(self, amount: float, notes: str = None):
        """Record a deposit."""
        self.db.record_deposit(amount, notes)
        self.logger.info(f"Deposited €{amount}")

    def withdraw(self, amount: float, notes: str = None):
        """Record a withdrawal."""
        self.db.record_withdrawal(amount, notes)
        self.logger.info(f"Withdrew €{amount}")

    def get_bet_sizing_table(self, probabilities: List[float], odds: float) -> pd.DataFrame:
        """
        Generate table of stake sizes for different probabilities.
        """
        data = []
        bankroll = self.get_current_bankroll()

        for prob in probabilities:
            full = KellyCalculator.full_kelly(prob, odds)
            ev = ProbabilityUtils.calculate_ev_percentage(prob, odds)

            data.append({
                'probability': f"{prob*100:.0f}%",
                'ev_pct': round(ev, 2),
                'full_kelly': round(full * bankroll, 2),
                'half_kelly': round(full * 0.5 * bankroll, 2),
                'quarter_kelly': round(full * 0.25 * bankroll, 2),
            })

        return pd.DataFrame(data)

    def analyze_historical_staking(self) -> dict:
        """Analyze historical staking patterns."""
        bets = self.db.get_bets(limit=500)

        if not bets:
            return {'message': 'No bet history'}

        stakes = [b.stake for b in bets]
        kellys = [b.kelly_fraction for b in bets if b.kelly_fraction]

        bankroll_at_time = self.initial_bankroll  # Simplified

        return {
            'avg_stake': round(sum(stakes) / len(stakes), 2),
            'max_stake': max(stakes),
            'min_stake': min(stakes),
            'avg_kelly_used': round(sum(kellys) / len(kellys), 4) if kellys else None,
            'stakes_as_pct_bankroll': round((sum(stakes) / len(stakes)) / bankroll_at_time * 100, 2)
        }

"""
Bonus Hunter & Rollover Optimizer
=================================

Optimizes bonus clearing with minimal risk.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import math

from ..database.db_manager import DatabaseManager
from ..utils.odds_converter import OddsConverter


@dataclass
class BonusOpportunity:
    """A bonus opportunity to evaluate."""
    bookmaker: str
    bonus_amount: float
    wagering_requirement: float
    max_odds: float
    min_odds: float
    expires_in_days: int
    ev_estimate: float
    recommended_strategy: str


@dataclass
class RolloverBet:
    """Recommended bet for bonus rollover."""
    selection: str
    odds: float
    stake: float
    expected_loss: float
    rollover_contribution: float
    notes: str


class RolloverOptimizer:
    """
    Optimizes the clearing of bonus wagering requirements.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("RolloverOptimizer")

        # Slovak bookmaker typical bonus terms
        self.bookmaker_terms = {
            'tipsport': {
                'typical_rollover': 5,
                'max_odds': 1.50,
                'min_odds': 1.10,
                'time_limit_days': 30
            },
            'fortuna': {
                'typical_rollover': 6,
                'max_odds': 1.40,
                'min_odds': 1.10,
                'time_limit_days': 30
            },
            'nike': {
                'typical_rollover': 5,
                'max_odds': 1.50,
                'min_odds': 1.10,
                'time_limit_days': 30
            },
            'doxxbet': {
                'typical_rollover': 4,
                'max_odds': 1.60,
                'min_odds': 1.10,
                'time_limit_days': 30
            }
        }

    def calculate_bonus_ev(
        self,
        bonus_amount: float,
        wagering_requirement: float,
        max_odds: float,
        strategy: str = 'low_risk'
    ) -> dict:
        """
        Calculate expected value of a bonus.

        Args:
            bonus_amount: Bonus amount received
            wagering_requirement: Times bonus must be wagered
            max_odds: Maximum odds allowed for rollover
            strategy: 'low_risk' or 'value_hunting'

        Returns:
            Dict with EV calculations
        """
        total_wagering = bonus_amount * wagering_requirement

        if strategy == 'low_risk':
            # Bet on heavy favorites around max odds
            avg_odds = max_odds
            implied_prob = 1 / avg_odds
            # Assume small margin loss
            expected_return_rate = implied_prob * avg_odds

            # Account for variance and margin
            house_edge = 0.03  # ~3% margin on low odds
            expected_loss_per_bet = 1 - (expected_return_rate - house_edge)
            total_expected_loss = total_wagering * expected_loss_per_bet

            ev = bonus_amount - total_expected_loss

        else:  # value_hunting
            # Actively seek +EV bets during rollover
            # Assume small positive EV on average
            avg_ev_per_bet = 0.02  # 2% EV
            ev = bonus_amount + (total_wagering * avg_ev_per_bet)

        return {
            'bonus_amount': bonus_amount,
            'total_wagering_required': total_wagering,
            'expected_value': round(ev, 2),
            'ev_percentage': round((ev / bonus_amount) * 100, 2),
            'is_profitable': ev > 0,
            'strategy': strategy,
            'recommendation': 'Accept' if ev > 0 else 'Decline'
        }

    def optimize_rollover(
        self,
        bonus_amount: float,
        wagering_requirement: float,
        max_odds: float,
        available_events: List[dict] = None
    ) -> List[RolloverBet]:
        """
        Generate optimal betting strategy for rollover.

        Args:
            bonus_amount: Bonus amount
            wagering_requirement: Rollover requirement
            max_odds: Maximum allowed odds
            available_events: Current events to bet on

        Returns:
            List of recommended bets
        """
        total_required = bonus_amount * wagering_requirement
        recommendations = []

        # Default strategy: equal stakes on favorites
        num_bets = math.ceil(wagering_requirement)
        stake_per_bet = bonus_amount / min(num_bets, 10)  # Cap at 10 bets initially

        # Target odds just under max
        target_odds = max_odds - 0.05

        for i in range(num_bets):
            # Calculate expected loss
            implied_prob = 1 / target_odds
            margin = 0.03
            expected_return = stake_per_bet * (implied_prob - margin) * target_odds
            expected_loss = stake_per_bet - expected_return

            recommendations.append(RolloverBet(
                selection=f"Heavy favorite (1X or similar)",
                odds=target_odds,
                stake=round(stake_per_bet, 2),
                expected_loss=round(expected_loss, 2),
                rollover_contribution=stake_per_bet,
                notes=f"Bet {i+1} of rollover"
            ))

            if sum(r.rollover_contribution for r in recommendations) >= total_required:
                break

        return recommendations

    def evaluate_bonus_offer(
        self,
        bookmaker: str,
        bonus_amount: float,
        wagering_requirement: float = None,
        max_odds: float = None,
        expires_days: int = None
    ) -> BonusOpportunity:
        """
        Evaluate a specific bonus offer.
        """
        # Get default terms if not specified
        terms = self.bookmaker_terms.get(bookmaker.lower(), {})

        if wagering_requirement is None:
            wagering_requirement = terms.get('typical_rollover', 5)
        if max_odds is None:
            max_odds = terms.get('max_odds', 1.50)
        if expires_days is None:
            expires_days = terms.get('time_limit_days', 30)

        # Calculate EV for both strategies
        low_risk = self.calculate_bonus_ev(
            bonus_amount, wagering_requirement, max_odds, 'low_risk'
        )
        value_hunt = self.calculate_bonus_ev(
            bonus_amount, wagering_requirement, max_odds, 'value_hunting'
        )

        # Choose best strategy
        if value_hunt['expected_value'] > low_risk['expected_value']:
            ev = value_hunt['expected_value']
            strategy = 'Value hunting during rollover'
        else:
            ev = low_risk['expected_value']
            strategy = 'Low-risk heavy favorites'

        return BonusOpportunity(
            bookmaker=bookmaker,
            bonus_amount=bonus_amount,
            wagering_requirement=wagering_requirement,
            max_odds=max_odds,
            min_odds=terms.get('min_odds', 1.10),
            expires_in_days=expires_days,
            ev_estimate=ev,
            recommended_strategy=strategy
        )


class BonusHunter:
    """
    Tracks and optimizes bonus opportunities across bookmakers.
    """

    def __init__(self, db_manager: DatabaseManager = None, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("BonusHunter")

        self.db = db_manager or DatabaseManager()
        self.optimizer = RolloverOptimizer(config)

    def add_bonus(
        self,
        bookmaker: str,
        bonus_amount: float,
        wagering_requirement: float,
        max_odds: float = 1.50,
        expires_at: datetime = None
    ) -> int:
        """Add a bonus to track."""
        if not expires_at:
            expires_at = datetime.now() + timedelta(days=30)

        bonus_data = {
            'bookmaker': bookmaker,
            'bonus_type': 'deposit',
            'bonus_amount': bonus_amount,
            'wagering_requirement': wagering_requirement,
            'max_odds': max_odds,
            'received_at': datetime.now(),
            'expires_at': expires_at
        }

        bonus_id = self.db.add_bonus(bonus_data)

        # Calculate EV
        ev_info = self.optimizer.calculate_bonus_ev(
            bonus_amount, wagering_requirement, max_odds
        )

        self.logger.info(
            f"Added bonus: {bookmaker} €{bonus_amount} "
            f"(EV: €{ev_info['expected_value']})"
        )

        return bonus_id

    def record_rollover_bet(
        self,
        bonus_id: int,
        stake: float,
        odds: float,
        result: str = 'pending'
    ):
        """Record a bet that contributes to rollover."""
        # Check if bet qualifies (odds within limits)
        bonus = self.get_bonus(bonus_id)

        if bonus and odds <= bonus.get('max_odds', 1.50):
            self.db.update_bonus_progress(bonus_id, stake)
            self.logger.info(f"Rollover progress: +€{stake}")
        else:
            self.logger.warning(f"Bet odds {odds} too high for rollover")

    def get_bonus(self, bonus_id: int) -> Optional[dict]:
        """Get bonus details."""
        # Would query database
        return None

    def get_active_bonuses(self) -> List:
        """Get all active bonuses."""
        return self.db.get_active_bonuses()

    def get_rollover_summary(self) -> dict:
        """Get summary of current rollover progress."""
        bonuses = self.get_active_bonuses()

        if not bonuses:
            return {'message': 'No active bonuses'}

        total_bonus = sum(b.bonus_amount for b in bonuses)
        total_required = sum(b.amount_required for b in bonuses)
        total_wagered = sum(b.amount_wagered for b in bonuses)
        total_remaining = total_required - total_wagered

        return {
            'active_bonuses': len(bonuses),
            'total_bonus_value': round(total_bonus, 2),
            'total_wagering_required': round(total_required, 2),
            'total_wagered': round(total_wagered, 2),
            'total_remaining': round(total_remaining, 2),
            'overall_progress': round((total_wagered / total_required) * 100, 1) if total_required > 0 else 0
        }

    def get_best_rollover_events(
        self,
        max_odds: float,
        events: List
    ) -> List[dict]:
        """
        Find best events for rolling over bonus.

        Prioritizes:
        1. Heavy favorites at max allowed odds
        2. Low variance outcomes
        3. Quick settlement
        """
        suitable = []

        for event in events:
            best_odds = event.get_best_odds('moneyline')

            for selection, (odds, bookmaker) in best_odds.items():
                if 1.01 < odds <= max_odds:
                    # Calculate implied probability
                    prob = 1 / odds
                    variance = prob * (1 - prob)

                    suitable.append({
                        'event': f"{event.home_team} vs {event.away_team}",
                        'selection': selection,
                        'odds': odds,
                        'bookmaker': bookmaker,
                        'implied_prob': round(prob * 100, 1),
                        'variance': round(variance, 4),
                        'start_time': event.start_time
                    })

        # Sort by odds descending (higher odds = faster rollover)
        # then by variance ascending (lower variance = safer)
        suitable.sort(key=lambda x: (-x['odds'], x['variance']))

        return suitable[:20]

    def complete_bonus(self, bonus_id: int, final_profit: float):
        """Mark bonus as completed."""
        self.db.update_bonus_progress(bonus_id, 0)  # Triggers completion check
        self.logger.info(f"Bonus {bonus_id} completed. Profit: €{final_profit}")

    def get_bonus_history_stats(self) -> dict:
        """Get historical bonus statistics."""
        # Would query completed bonuses
        return {
            'total_bonuses_cleared': 0,
            'total_bonus_profit': 0,
            'avg_profit_per_bonus': 0,
            'best_bonus': None,
            'by_bookmaker': {}
        }

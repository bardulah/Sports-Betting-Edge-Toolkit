"""
Arbitrage Finder
================

Finds arbitrage (surebet) opportunities across bookmakers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from itertools import combinations

from ..scrapers.odds_aggregator import AggregatedEvent
from ..utils.odds_converter import OddsConverter


@dataclass
class ArbitrageLeg:
    """Single leg of an arbitrage opportunity."""
    bookmaker: str
    selection: str
    odds: float
    stake: float
    potential_return: float


@dataclass
class ArbitrageOpportunity:
    """Complete arbitrage opportunity."""
    event: AggregatedEvent
    market_type: str
    profit_percentage: float
    total_stake: float
    guaranteed_profit: float
    legs: List[ArbitrageLeg]
    detected_at: datetime = field(default_factory=datetime.now)

    def __str__(self):
        return (
            f"{self.profit_percentage:.2f}% Arb | {self.event.home_team} vs {self.event.away_team} | "
            f"Profit: €{self.guaranteed_profit:.2f} on €{self.total_stake:.2f}"
        )


class ArbitrageFinder:
    """
    Finds arbitrage opportunities across multiple bookmakers.

    An arbitrage exists when the combined implied probability of all
    outcomes is less than 100%, allowing guaranteed profit.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("ArbitrageFinder")

        # Configuration
        self.min_profit = self.config.get('min_profit_percentage', 1.0)
        self.max_stake = self.config.get('max_stake', 500)
        self.include_commission = self.config.get('include_commission', True)

        # Bookmaker commissions (if any)
        self.commissions = self.config.get('commissions', {
            'Betfair': 0.05,  # 5% commission on winnings
        })

    def find_arbitrage(
        self,
        events: List[AggregatedEvent],
        min_profit: float = None
    ) -> List[ArbitrageOpportunity]:
        """
        Find all arbitrage opportunities.

        Args:
            events: List of aggregated events
            min_profit: Minimum profit percentage to report

        Returns:
            List of ArbitrageOpportunity sorted by profit
        """
        min_profit = min_profit if min_profit is not None else self.min_profit
        opportunities = []

        for event in events:
            event_arbs = self._analyze_event(event, min_profit)
            opportunities.extend(event_arbs)

        # Sort by profit
        opportunities.sort(key=lambda x: x.profit_percentage, reverse=True)

        return opportunities

    def _analyze_event(
        self,
        event: AggregatedEvent,
        min_profit: float
    ) -> List[ArbitrageOpportunity]:
        """Analyze a single event for arbitrage."""
        opportunities = []

        # Get best odds for each outcome
        best_odds = event.get_best_odds('moneyline')

        if len(best_odds) < 2:
            return opportunities

        # Check if arbitrage exists
        if len(best_odds) == 2:
            # Two-way market (tennis, hockey)
            arb = self._check_two_way_arb(event, best_odds, min_profit)
            if arb:
                opportunities.append(arb)

        elif len(best_odds) == 3:
            # Three-way market (football)
            arb = self._check_three_way_arb(event, best_odds, min_profit)
            if arb:
                opportunities.append(arb)

        return opportunities

    def _check_two_way_arb(
        self,
        event: AggregatedEvent,
        best_odds: Dict[str, Tuple[float, str]],
        min_profit: float
    ) -> Optional[ArbitrageOpportunity]:
        """Check for two-way arbitrage."""
        selections = list(best_odds.keys())
        if len(selections) != 2:
            return None

        odds1, book1 = best_odds[selections[0]]
        odds2, book2 = best_odds[selections[1]]

        # Calculate implied probabilities
        imp1 = 1 / odds1
        imp2 = 1 / odds2
        total_implied = imp1 + imp2

        if total_implied >= 1:
            return None  # No arbitrage

        # Calculate profit
        profit_pct = ((1 / total_implied) - 1) * 100

        if profit_pct < min_profit:
            return None

        # Calculate stakes for equal return
        total_stake = self.max_stake
        stake1 = total_stake * imp1 / total_implied
        stake2 = total_stake * imp2 / total_implied

        return1 = stake1 * odds1
        return2 = stake2 * odds2
        guaranteed = return1 - total_stake  # Should be same as return2 - total_stake

        legs = [
            ArbitrageLeg(book1, selections[0], odds1, round(stake1, 2), round(return1, 2)),
            ArbitrageLeg(book2, selections[1], odds2, round(stake2, 2), round(return2, 2))
        ]

        return ArbitrageOpportunity(
            event=event,
            market_type='moneyline',
            profit_percentage=round(profit_pct, 2),
            total_stake=round(total_stake, 2),
            guaranteed_profit=round(guaranteed, 2),
            legs=legs
        )

    def _check_three_way_arb(
        self,
        event: AggregatedEvent,
        best_odds: Dict[str, Tuple[float, str]],
        min_profit: float
    ) -> Optional[ArbitrageOpportunity]:
        """Check for three-way arbitrage."""
        selections = list(best_odds.keys())
        if len(selections) != 3:
            return None

        # Get odds and books
        odds_data = [(sel, best_odds[sel][0], best_odds[sel][1]) for sel in selections]

        # Calculate total implied probability
        total_implied = sum(1 / data[1] for data in odds_data)

        if total_implied >= 1:
            return None  # No arbitrage

        # Calculate profit
        profit_pct = ((1 / total_implied) - 1) * 100

        if profit_pct < min_profit:
            return None

        # Calculate stakes
        total_stake = self.max_stake
        legs = []

        for sel, odds, book in odds_data:
            stake = total_stake * (1 / odds) / total_implied
            potential_return = stake * odds

            legs.append(ArbitrageLeg(
                bookmaker=book,
                selection=sel,
                odds=odds,
                stake=round(stake, 2),
                potential_return=round(potential_return, 2)
            ))

        guaranteed = legs[0].potential_return - total_stake

        return ArbitrageOpportunity(
            event=event,
            market_type='moneyline',
            profit_percentage=round(profit_pct, 2),
            total_stake=round(total_stake, 2),
            guaranteed_profit=round(guaranteed, 2),
            legs=legs
        )

    def calculate_stakes(
        self,
        odds_list: List[float],
        total_stake: float = None
    ) -> Dict[str, float]:
        """
        Calculate optimal stakes for arbitrage.

        Args:
            odds_list: List of odds for each outcome
            total_stake: Total amount to stake

        Returns:
            Dictionary with stakes and profit info
        """
        total_stake = total_stake or self.max_stake

        if not odds_list or any(o <= 1 for o in odds_list):
            return {'error': 'Invalid odds'}

        # Calculate implied probabilities
        implied = [1 / o for o in odds_list]
        total_implied = sum(implied)

        if total_implied >= 1:
            return {
                'is_arbitrage': False,
                'total_implied': round(total_implied * 100, 2),
                'message': 'No arbitrage exists'
            }

        # Calculate stakes
        stakes = [total_stake * imp / total_implied for imp in implied]
        returns = [stake * odds for stake, odds in zip(stakes, odds_list)]
        profit = returns[0] - total_stake

        return {
            'is_arbitrage': True,
            'profit_percentage': round(((1 / total_implied) - 1) * 100, 2),
            'total_stake': round(total_stake, 2),
            'stakes': [round(s, 2) for s in stakes],
            'returns': [round(r, 2) for r in returns],
            'guaranteed_profit': round(profit, 2),
            'roi': round((profit / total_stake) * 100, 2)
        }

    def find_near_arbitrage(
        self,
        events: List[AggregatedEvent],
        max_margin: float = 1.0
    ) -> List[dict]:
        """
        Find events close to arbitrage (low total margin).

        These are good candidates for +EV betting even without full arb.
        """
        near_arbs = []

        for event in events:
            best_odds = event.get_best_odds('moneyline')

            if len(best_odds) < 2:
                continue

            odds_list = [v[0] for v in best_odds.values()]
            total_implied = sum(1 / o for o in odds_list)
            margin = (total_implied - 1) * 100

            if 0 < margin <= max_margin:
                near_arbs.append({
                    'event': event,
                    'margin': round(margin, 2),
                    'best_odds': best_odds,
                    'note': 'Very close to arbitrage - strong +EV opportunity'
                })

        return sorted(near_arbs, key=lambda x: x['margin'])

    def get_summary(self, opportunities: List[ArbitrageOpportunity]) -> dict:
        """Get summary of arbitrage opportunities."""
        if not opportunities:
            return {
                'total_opportunities': 0,
                'total_potential_profit': 0,
                'avg_profit_pct': 0,
                'max_profit_pct': 0,
                'by_sport': {}
            }

        by_sport = {}
        for opp in opportunities:
            sport = opp.event.sport
            by_sport[sport] = by_sport.get(sport, 0) + 1

        return {
            'total_opportunities': len(opportunities),
            'total_potential_profit': round(sum(o.guaranteed_profit for o in opportunities), 2),
            'avg_profit_pct': round(sum(o.profit_percentage for o in opportunities) / len(opportunities), 2),
            'max_profit_pct': round(max(o.profit_percentage for o in opportunities), 2),
            'total_stake_required': round(sum(o.total_stake for o in opportunities), 2),
            'by_sport': by_sport
        }

    def check_arbitrage_quick(self, odds_list: List[float]) -> bool:
        """Quick check if odds create an arbitrage."""
        if not odds_list or any(o <= 1 for o in odds_list):
            return False
        return sum(1 / o for o in odds_list) < 1

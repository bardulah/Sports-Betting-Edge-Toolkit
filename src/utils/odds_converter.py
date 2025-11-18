"""
Odds Converter Module
=====================

Converts between different odds formats and calculates implied probabilities.
Supports: Decimal, American, Fractional, Implied Probability
"""

from typing import Union, Tuple
from fractions import Fraction
import math


class OddsConverter:
    """
    Universal odds converter supporting all major formats.
    """

    @staticmethod
    def decimal_to_american(decimal_odds: float) -> int:
        """Convert decimal odds to American odds."""
        if decimal_odds >= 2.0:
            return int(round((decimal_odds - 1) * 100))
        else:
            return int(round(-100 / (decimal_odds - 1)))

    @staticmethod
    def american_to_decimal(american_odds: int) -> float:
        """Convert American odds to decimal odds."""
        if american_odds > 0:
            return round((american_odds / 100) + 1, 3)
        else:
            return round((100 / abs(american_odds)) + 1, 3)

    @staticmethod
    def decimal_to_fractional(decimal_odds: float) -> str:
        """Convert decimal odds to fractional odds."""
        frac = Fraction(decimal_odds - 1).limit_denominator(100)
        return f"{frac.numerator}/{frac.denominator}"

    @staticmethod
    def fractional_to_decimal(fractional: str) -> float:
        """Convert fractional odds to decimal odds."""
        parts = fractional.split('/')
        if len(parts) == 2:
            return round((int(parts[0]) / int(parts[1])) + 1, 3)
        return float(parts[0]) + 1

    @staticmethod
    def decimal_to_probability(decimal_odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if decimal_odds <= 0:
            return 0.0
        return round(1 / decimal_odds, 4)

    @staticmethod
    def probability_to_decimal(probability: float) -> float:
        """Convert probability to decimal odds."""
        if probability <= 0 or probability >= 1:
            return 0.0
        return round(1 / probability, 3)

    @staticmethod
    def american_to_probability(american_odds: int) -> float:
        """Convert American odds to implied probability."""
        if american_odds > 0:
            return round(100 / (american_odds + 100), 4)
        else:
            return round(abs(american_odds) / (abs(american_odds) + 100), 4)

    @staticmethod
    def probability_to_american(probability: float) -> int:
        """Convert probability to American odds."""
        if probability <= 0 or probability >= 1:
            return 0
        if probability >= 0.5:
            return int(round(-100 * probability / (1 - probability)))
        else:
            return int(round(100 * (1 - probability) / probability))

    @staticmethod
    def calculate_margin(odds_list: list[float]) -> float:
        """
        Calculate bookmaker margin from a list of decimal odds.

        Args:
            odds_list: List of decimal odds for all outcomes

        Returns:
            Margin as a percentage (e.g., 0.05 for 5%)
        """
        if not odds_list or any(o <= 0 for o in odds_list):
            return 0.0

        total_implied = sum(1 / odds for odds in odds_list)
        return round(total_implied - 1, 4)

    @staticmethod
    def calculate_overround(odds_list: list[float]) -> float:
        """
        Calculate overround (total implied probability).

        Args:
            odds_list: List of decimal odds for all outcomes

        Returns:
            Overround as percentage (e.g., 105% means 5% margin)
        """
        if not odds_list or any(o <= 0 for o in odds_list):
            return 0.0

        return round(sum(1 / odds for odds in odds_list) * 100, 2)

    @staticmethod
    def remove_margin_multiplicative(odds_list: list[float]) -> list[float]:
        """
        Remove margin using multiplicative method.
        Distributes margin equally across all outcomes.

        Args:
            odds_list: List of decimal odds with margin

        Returns:
            List of fair decimal odds
        """
        if not odds_list or any(o <= 0 for o in odds_list):
            return odds_list

        total_implied = sum(1 / odds for odds in odds_list)
        return [round(odds * total_implied, 3) for odds in odds_list]

    @staticmethod
    def remove_margin_additive(odds_list: list[float]) -> list[float]:
        """
        Remove margin using additive method.
        Subtracts equal probability from each outcome.

        Args:
            odds_list: List of decimal odds with margin

        Returns:
            List of fair decimal odds
        """
        if not odds_list or any(o <= 0 for o in odds_list):
            return odds_list

        n = len(odds_list)
        margin = OddsConverter.calculate_margin(odds_list)
        margin_per_outcome = margin / n

        fair_odds = []
        for odds in odds_list:
            prob = (1 / odds) - margin_per_outcome
            if prob <= 0:
                prob = 0.001
            fair_odds.append(round(1 / prob, 3))

        return fair_odds

    @staticmethod
    def remove_margin_power(odds_list: list[float], iterations: int = 100) -> list[float]:
        """
        Remove margin using power/Shin method.
        Better handles favorite-longshot bias.

        Args:
            odds_list: List of decimal odds with margin
            iterations: Number of iterations for convergence

        Returns:
            List of fair decimal odds
        """
        if not odds_list or any(o <= 0 for o in odds_list):
            return odds_list

        implied_probs = [1 / odds for odds in odds_list]
        total = sum(implied_probs)

        # Binary search for power coefficient
        low, high = 0.0, 1.0

        for _ in range(iterations):
            mid = (low + high) / 2
            adjusted = [p ** mid for p in implied_probs]
            adj_total = sum(adjusted)

            if adj_total > 1:
                low = mid
            else:
                high = mid

        power = (low + high) / 2
        fair_probs = [p ** power for p in implied_probs]
        total_fair = sum(fair_probs)
        normalized = [p / total_fair for p in fair_probs]

        return [round(1 / p, 3) if p > 0 else 1000 for p in normalized]

    @staticmethod
    def remove_margin_odds_ratio(odds_list: list[float]) -> list[float]:
        """
        Remove margin while keeping odds ratio constant.

        Args:
            odds_list: List of decimal odds with margin

        Returns:
            List of fair decimal odds
        """
        if len(odds_list) != 2:
            # Only works for 2-way markets
            return OddsConverter.remove_margin_multiplicative(odds_list)

        if any(o <= 0 for o in odds_list):
            return odds_list

        p1 = 1 / odds_list[0]
        p2 = 1 / odds_list[1]

        # Solve quadratic to find true probability
        a = 1
        b = -1
        c = (p1 * p2 - p1 - p2) / (p1 - p2) if p1 != p2 else 0

        discriminant = b**2 - 4*a*c
        if discriminant < 0:
            return OddsConverter.remove_margin_multiplicative(odds_list)

        fair_p1 = (-b - math.sqrt(discriminant)) / (2*a)
        fair_p2 = 1 - fair_p1

        if fair_p1 <= 0 or fair_p2 <= 0:
            return OddsConverter.remove_margin_multiplicative(odds_list)

        return [round(1 / fair_p1, 3), round(1 / fair_p2, 3)]

    @staticmethod
    def get_true_odds(odds_list: list[float], method: str = "power") -> list[float]:
        """
        Get true (fair) odds using specified margin removal method.

        Args:
            odds_list: List of decimal odds with margin
            method: One of 'multiplicative', 'additive', 'power', 'odds_ratio'

        Returns:
            List of fair decimal odds
        """
        methods = {
            'multiplicative': OddsConverter.remove_margin_multiplicative,
            'additive': OddsConverter.remove_margin_additive,
            'power': OddsConverter.remove_margin_power,
            'odds_ratio': OddsConverter.remove_margin_odds_ratio,
        }

        converter = methods.get(method, OddsConverter.remove_margin_power)
        return converter(odds_list)

    @staticmethod
    def convert_all_formats(decimal_odds: float) -> dict:
        """
        Convert decimal odds to all formats at once.

        Args:
            decimal_odds: Odds in decimal format

        Returns:
            Dictionary with all formats
        """
        return {
            'decimal': decimal_odds,
            'american': OddsConverter.decimal_to_american(decimal_odds),
            'fractional': OddsConverter.decimal_to_fractional(decimal_odds),
            'implied_probability': OddsConverter.decimal_to_probability(decimal_odds),
            'implied_percentage': round(OddsConverter.decimal_to_probability(decimal_odds) * 100, 2),
        }

    @staticmethod
    def normalize_odds(odds: Union[float, int, str], from_format: str = 'auto') -> float:
        """
        Normalize any odds format to decimal.

        Args:
            odds: Odds in any format
            from_format: 'decimal', 'american', 'fractional', or 'auto'

        Returns:
            Decimal odds
        """
        if from_format == 'auto':
            if isinstance(odds, str) and '/' in odds:
                from_format = 'fractional'
            elif isinstance(odds, int) or (isinstance(odds, float) and (odds > 50 or odds < -50)):
                from_format = 'american'
            else:
                from_format = 'decimal'

        if from_format == 'decimal':
            return float(odds)
        elif from_format == 'american':
            return OddsConverter.american_to_decimal(int(odds))
        elif from_format == 'fractional':
            return OddsConverter.fractional_to_decimal(str(odds))
        else:
            return float(odds)


# Convenience functions
def to_decimal(odds: Union[float, int, str], from_format: str = 'auto') -> float:
    """Quick conversion to decimal odds."""
    return OddsConverter.normalize_odds(odds, from_format)


def to_probability(odds: Union[float, int, str], from_format: str = 'auto') -> float:
    """Quick conversion to implied probability."""
    decimal = OddsConverter.normalize_odds(odds, from_format)
    return OddsConverter.decimal_to_probability(decimal)


def get_margin(odds_list: list[float]) -> float:
    """Quick margin calculation."""
    return OddsConverter.calculate_margin(odds_list)


def fair_odds(odds_list: list[float], method: str = 'power') -> list[float]:
    """Quick fair odds calculation."""
    return OddsConverter.get_true_odds(odds_list, method)

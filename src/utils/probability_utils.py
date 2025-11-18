"""
Probability Utilities Module
============================

Statistical and probability functions for sports betting analysis.
"""

import math
from typing import List, Tuple, Optional
from scipy import stats
import numpy as np


class ProbabilityUtils:
    """
    Utility class for probability and statistical calculations.
    """

    @staticmethod
    def calculate_ev(probability: float, odds: float, stake: float = 1.0) -> float:
        """
        Calculate Expected Value of a bet.

        Args:
            probability: True probability of winning (0-1)
            odds: Decimal odds offered
            stake: Bet amount

        Returns:
            Expected value in currency units
        """
        win_amount = stake * (odds - 1)
        ev = (probability * win_amount) - ((1 - probability) * stake)
        return round(ev, 4)

    @staticmethod
    def calculate_ev_percentage(probability: float, odds: float) -> float:
        """
        Calculate EV as a percentage of stake.

        Args:
            probability: True probability of winning (0-1)
            odds: Decimal odds offered

        Returns:
            EV percentage (e.g., 5.0 for +5% EV)
        """
        implied_prob = 1 / odds
        edge = probability - implied_prob
        ev_pct = edge * odds * 100
        return round(ev_pct, 2)

    @staticmethod
    def calculate_edge(true_probability: float, offered_odds: float) -> float:
        """
        Calculate betting edge percentage.

        Args:
            true_probability: Estimated true probability
            offered_odds: Decimal odds being offered

        Returns:
            Edge as percentage
        """
        implied = 1 / offered_odds
        edge = ((true_probability - implied) / implied) * 100
        return round(edge, 2)

    @staticmethod
    def kelly_criterion(probability: float, odds: float) -> float:
        """
        Calculate optimal Kelly bet size as fraction of bankroll.

        Args:
            probability: True probability of winning
            odds: Decimal odds

        Returns:
            Optimal fraction of bankroll to bet
        """
        if probability <= 0 or probability >= 1 or odds <= 1:
            return 0.0

        q = 1 - probability
        b = odds - 1

        kelly = (probability * b - q) / b
        return max(0, round(kelly, 4))

    @staticmethod
    def fractional_kelly(probability: float, odds: float, fraction: float = 0.25) -> float:
        """
        Calculate fractional Kelly bet size.

        Args:
            probability: True probability of winning
            odds: Decimal odds
            fraction: Kelly fraction (0.25 = quarter Kelly)

        Returns:
            Fractional Kelly bet size
        """
        full_kelly = ProbabilityUtils.kelly_criterion(probability, odds)
        return round(full_kelly * fraction, 4)

    @staticmethod
    def optimal_bet_size(
        probability: float,
        odds: float,
        bankroll: float,
        kelly_fraction: float = 0.25,
        max_bet_pct: float = 0.05
    ) -> float:
        """
        Calculate optimal bet size with constraints.

        Args:
            probability: True probability
            odds: Decimal odds
            bankroll: Current bankroll
            kelly_fraction: Kelly multiplier
            max_bet_pct: Maximum bet as fraction of bankroll

        Returns:
            Optimal bet size in currency
        """
        kelly = ProbabilityUtils.fractional_kelly(probability, odds, kelly_fraction)
        bet_fraction = min(kelly, max_bet_pct)
        bet_size = bankroll * bet_fraction
        return round(bet_size, 2)

    @staticmethod
    def poisson_probability(expected: float, actual: int) -> float:
        """
        Calculate Poisson probability.

        Args:
            expected: Expected value (lambda)
            actual: Actual outcome

        Returns:
            Probability of exact outcome
        """
        return stats.poisson.pmf(actual, expected)

    @staticmethod
    def poisson_over_under(expected: float, line: float) -> Tuple[float, float]:
        """
        Calculate over/under probabilities using Poisson distribution.

        Args:
            expected: Expected value
            line: The line to compare against

        Returns:
            Tuple of (over_prob, under_prob)
        """
        under = stats.poisson.cdf(int(line), expected)
        over = 1 - stats.poisson.cdf(int(line), expected)

        # Handle push probability for whole numbers
        if line == int(line):
            push = stats.poisson.pmf(int(line), expected)
            over = 1 - under

        return (round(over, 4), round(under, 4))

    @staticmethod
    def calculate_clv(bet_odds: float, closing_odds: float) -> float:
        """
        Calculate Closing Line Value.

        Args:
            bet_odds: Odds when bet was placed
            closing_odds: Final odds before event start

        Returns:
            CLV as percentage
        """
        if closing_odds <= 0 or bet_odds <= 0:
            return 0.0

        bet_prob = 1 / bet_odds
        close_prob = 1 / closing_odds

        clv = ((close_prob - bet_prob) / bet_prob) * 100
        return round(clv, 2)

    @staticmethod
    def calculate_roi(profit: float, total_staked: float) -> float:
        """
        Calculate Return on Investment.

        Args:
            profit: Total profit/loss
            total_staked: Total amount wagered

        Returns:
            ROI as percentage
        """
        if total_staked <= 0:
            return 0.0
        return round((profit / total_staked) * 100, 2)

    @staticmethod
    def calculate_yield(profit: float, num_bets: int, avg_stake: float = 1.0) -> float:
        """
        Calculate yield (profit per unit staked).

        Args:
            profit: Total profit
            num_bets: Number of bets
            avg_stake: Average stake size

        Returns:
            Yield percentage
        """
        if num_bets <= 0:
            return 0.0
        total_staked = num_bets * avg_stake
        return ProbabilityUtils.calculate_roi(profit, total_staked)

    @staticmethod
    def calculate_win_rate(wins: int, total: int) -> float:
        """Calculate win rate percentage."""
        if total <= 0:
            return 0.0
        return round((wins / total) * 100, 2)

    @staticmethod
    def calculate_z_score(wins: int, total: int, expected_win_rate: float) -> float:
        """
        Calculate Z-score for win rate.

        Args:
            wins: Number of wins
            total: Total bets
            expected_win_rate: Expected win probability

        Returns:
            Z-score
        """
        if total <= 0:
            return 0.0

        observed_rate = wins / total
        std_error = math.sqrt(expected_win_rate * (1 - expected_win_rate) / total)

        if std_error == 0:
            return 0.0

        z = (observed_rate - expected_win_rate) / std_error
        return round(z, 2)

    @staticmethod
    def calculate_p_value(z_score: float) -> float:
        """
        Calculate p-value from Z-score (two-tailed).

        Args:
            z_score: The Z-score

        Returns:
            P-value
        """
        return round(2 * (1 - stats.norm.cdf(abs(z_score))), 4)

    @staticmethod
    def confidence_interval(
        wins: int,
        total: int,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate confidence interval for win rate.

        Args:
            wins: Number of wins
            total: Total bets
            confidence: Confidence level (e.g., 0.95)

        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if total <= 0:
            return (0.0, 0.0)

        p = wins / total
        z = stats.norm.ppf((1 + confidence) / 2)

        margin = z * math.sqrt(p * (1 - p) / total)

        return (
            round(max(0, p - margin) * 100, 2),
            round(min(1, p + margin) * 100, 2)
        )

    @staticmethod
    def bankroll_growth_rate(wins: int, losses: int, avg_odds: float) -> float:
        """
        Calculate expected bankroll growth rate.

        Args:
            wins: Number of wins
            losses: Number of losses
            avg_odds: Average decimal odds

        Returns:
            Expected growth rate
        """
        if wins + losses == 0:
            return 0.0

        p = wins / (wins + losses)
        b = avg_odds - 1

        # Log growth rate
        growth = p * math.log(1 + b) + (1 - p) * math.log(1 - 1)
        return round(growth, 4)

    @staticmethod
    def ruin_probability(
        win_prob: float,
        odds: float,
        bet_fraction: float,
        target_multiple: float = 2.0
    ) -> float:
        """
        Estimate probability of ruin before reaching target.

        Args:
            win_prob: Probability of winning each bet
            odds: Decimal odds
            bet_fraction: Fraction of bankroll bet each time
            target_multiple: Target bankroll multiple

        Returns:
            Estimated ruin probability
        """
        if win_prob <= 0 or win_prob >= 1:
            return 1.0 if win_prob <= 0 else 0.0

        # Simplified ruin formula
        q = 1 - win_prob
        b = odds - 1

        if bet_fraction >= 1:
            return q

        # Approximate using gambler's ruin formula
        if win_prob * b > q:
            ruin = (q / (win_prob * b)) ** (1 / bet_fraction)
        else:
            ruin = 1.0

        return min(1.0, max(0.0, round(ruin, 4)))

    @staticmethod
    def sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
        """
        Calculate Sharpe ratio for betting returns.

        Args:
            returns: List of returns (as decimals)
            risk_free_rate: Risk-free rate

        Returns:
            Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate

        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)

        if std_excess == 0:
            return 0.0

        return round(mean_excess / std_excess, 2)

    @staticmethod
    def max_drawdown(bankroll_history: List[float]) -> Tuple[float, int, int]:
        """
        Calculate maximum drawdown from bankroll history.

        Args:
            bankroll_history: List of bankroll values over time

        Returns:
            Tuple of (max_drawdown_pct, peak_idx, trough_idx)
        """
        if len(bankroll_history) < 2:
            return (0.0, 0, 0)

        peak = bankroll_history[0]
        peak_idx = 0
        max_dd = 0.0
        max_dd_peak_idx = 0
        max_dd_trough_idx = 0

        for i, value in enumerate(bankroll_history):
            if value > peak:
                peak = value
                peak_idx = i

            drawdown = (peak - value) / peak if peak > 0 else 0

            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_peak_idx = peak_idx
                max_dd_trough_idx = i

        return (round(max_dd * 100, 2), max_dd_peak_idx, max_dd_trough_idx)

    @staticmethod
    def simulate_bankroll(
        win_prob: float,
        odds: float,
        bet_fraction: float,
        initial_bankroll: float,
        num_bets: int,
        simulations: int = 1000
    ) -> dict:
        """
        Monte Carlo simulation of bankroll evolution.

        Args:
            win_prob: Win probability
            odds: Decimal odds
            bet_fraction: Fraction of bankroll to bet
            initial_bankroll: Starting bankroll
            num_bets: Number of bets to simulate
            simulations: Number of simulation runs

        Returns:
            Dictionary with simulation statistics
        """
        final_bankrolls = []
        ruin_count = 0

        for _ in range(simulations):
            bankroll = initial_bankroll

            for _ in range(num_bets):
                if bankroll <= 0:
                    ruin_count += 1
                    break

                bet_size = bankroll * bet_fraction

                if np.random.random() < win_prob:
                    bankroll += bet_size * (odds - 1)
                else:
                    bankroll -= bet_size

            final_bankrolls.append(bankroll)

        final_array = np.array(final_bankrolls)

        return {
            'mean_final': round(np.mean(final_array), 2),
            'median_final': round(np.median(final_array), 2),
            'std_final': round(np.std(final_array), 2),
            'min_final': round(np.min(final_array), 2),
            'max_final': round(np.max(final_array), 2),
            'ruin_probability': round(ruin_count / simulations, 4),
            'percentile_5': round(np.percentile(final_array, 5), 2),
            'percentile_25': round(np.percentile(final_array, 25), 2),
            'percentile_75': round(np.percentile(final_array, 75), 2),
            'percentile_95': round(np.percentile(final_array, 95), 2),
        }


# Convenience functions
def ev(prob: float, odds: float, stake: float = 1.0) -> float:
    """Quick EV calculation."""
    return ProbabilityUtils.calculate_ev(prob, odds, stake)


def kelly(prob: float, odds: float, fraction: float = 1.0) -> float:
    """Quick Kelly calculation."""
    if fraction == 1.0:
        return ProbabilityUtils.kelly_criterion(prob, odds)
    return ProbabilityUtils.fractional_kelly(prob, odds, fraction)


def clv(bet_odds: float, closing_odds: float) -> float:
    """Quick CLV calculation."""
    return ProbabilityUtils.calculate_clv(bet_odds, closing_odds)


def roi(profit: float, staked: float) -> float:
    """Quick ROI calculation."""
    return ProbabilityUtils.calculate_roi(profit, staked)

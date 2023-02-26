"""Module for dice probability functions. All calculations assume face values are 
integers ranging from 1 to X >= 1.

NOTE: References to 'pdf' mean 'probability distribution function', a mapping from
possible outcome values to probability of seeing that value.
"""

from __future__ import annotations
from collections import Counter
from itertools import product
from typing import Dict, Iterable
import math


def prob_max_roll(dice: int, sides: int, val: int) -> float:
    """Probability that max roll on [dice] with [sides] will exactly equal [val].
    This is the highest face of ANY die, not the sum of multiple dice!

    Credit: https://rpubs.com/gstats/max-roll
    """

    return ((val / sides) ** dice) - ((val - 1) / sides) ** dice


def all_probs_high_die(dice: int, sides: int) -> Dict[int, float]:
    """Return a dictionary of the probabilities that the highest single face of
    any die in a roll will be X, where X ranges from 1 to [sides].

    Format: {high roll : probability of high roll}"""

    return {(k + 1): prob_max_roll(dice, sides, k + 1) for k in range(sides)}


def all_probs_threshold(dice: int, sides: int, val: int) -> Dict[int, float]:
    """Return a dictionary of the probabilities that any number of dice will meet or
    exceed some threshold value.

    Format: {num dice : probability of num dice}"""
    if sides < val or dice < 1:
        return {0: 1.0}

    dieChance = max(0, (sides - val) + 1) / sides
    return {
        k: math.comb(dice, k) * (dieChance ** k) * (1 - dieChance) ** (dice - k)
        for k in range(dice + 1)
    }


def all_probs_brute_force_max_roll(dice: int) -> Dict[int, float]:
    """Calculate max roll probabilities by generating all possible rolls and counting
    the results.

    Explanation:
    1. Use itertools.product() to generate all combinations of die rolls
    2. Use map() to transform each set of rolls into a single max value
    3. Use collections.Counter type to generate a dictionary with the count of each
        value.
    """

    count = Counter(map(max, product((1, 2, 3, 4, 5, 6), repeat=dice)))
    rolls = sum(count.values())
    return {k: v / rolls for k, v in count.items()}


def all_probs_drop_high(dice: int) -> Dict[int, float]:
    """Calculate max roll probabilities by generating all possible rolls, dropping
    the highest, and counting the results. Useful for verifying HGB skill bonus.

    Explanation:
    Same as all_probs_brute_force_max_roll() except drop the high die first."""
    count = Counter(map(max, map(drop_high, product((1, 2, 3, 4, 5, 6), repeat=dice))))
    rolls = sum(count.values())
    return {k: v / rolls for k, v in count.items()}


def drop_high(roll: Iterable) -> tuple:
    """Remove highest value from iterable"""
    roll = list(roll)
    roll.remove(max(roll))
    return tuple(roll)


def check_accuracy(maxDice=9):
    # Unimplemented. Already verified accuracy of mathematical method vs. brute force
    pass


def expected(pdf: Dict[int, float]) -> float:
    """Returns the 'average' result of a probability distribution function."""
    return sum(k * v for k, v in pdf.items())


def standard_dev(pdf: Dict[int, float]) -> float:
    """Standard deviation for a discrete random variable isn't quite the same as
    for a bell curve, but it's still a useful measure.

    Credit: https://nzmaths.co.nz/category/glossary/standard-deviation-discrete-random-variable
    """
    exp = expected(pdf)
    return math.sqrt(sum(((k - exp) ** 2) * v for k, v in pdf.items()))


if __name__ == "__main__":
    """Just for debug purposes."""
    print(all_probs_high_die(3, 6))
    print(all_probs_threshold(2, 6, 4))

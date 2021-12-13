from __future__ import annotations
from collections import Counter
from itertools import product
from typing import Dict, Iterable
import math


def prob_max_roll(dice: int, sides: int, val: int) -> float:
    """Probability that max roll on XdY will equal val"""
    # Ref: https://rpubs.com/gstats/max-roll

    return ((val / sides) ** dice) - ((val - 1) / sides) ** dice


def all_probs_high_die(dice: int, sides: int) -> Dict[int, float]:
    """Probabilities for all max rolls on XdY"""
    return {(k + 1): prob_max_roll(dice, sides, k + 1) for k in range(sides)}


def all_probs_threshold(dice: int, sides: int, val: int) -> Dict[int, float]:
    if sides < val or dice < 1:
        return {0: 1.0}

    dieChance = max(0, (sides - val) + 1) / sides
    return {
        k: math.comb(dice, k) * (dieChance ** k) * (1 - dieChance) ** (dice - k)
        for k in range(dice + 1)
    }


def all_probs_brute_force_max_roll(dice: int) -> Dict[int, float]:
    # Just for verification purposes
    count = Counter(map(max, product((1, 2, 3, 4, 5, 6), repeat=dice)))
    rolls = sum(count.values())
    return {k: v / rolls for k, v in count.items()}


def all_probs_drop_high(dice: int) -> Dict[int, float]:
    # Just for verification purposes
    count = Counter(map(max, map(drop_high, product((1, 2, 3, 4, 5, 6), repeat=dice))))
    rolls = sum(count.values())
    return {k: v / rolls for k, v in count.items()}


def drop_high(roll: Iterable) -> tuple:
    roll = list(roll)
    roll.remove(max(roll))
    return tuple(roll)


def check_accuracy(maxDice=9):
    # TODO: Check brute force vs. math
    pass


def expected(pdf: Dict[int, float]) -> float:
    return sum(k * v for k, v in pdf.items())


def standard_dev(pdf: Dict[int, float]) -> float:
    exp = expected(pdf)
    return math.sqrt(sum(((k - exp) ** 2) * v for k, v in pdf.items()))


if __name__ == "__main__":
    print(all_probs_high_die(3, 6))
    print(all_probs_threshold(2, 5, 3))

"""
Exact probability distributions for the reroll / bonus / keep-top-K dice rule.

Rule for each of the ``n`` original dice (each a die with ``faces`` = F faces):

1. Roll the die once.
2. If the rolled face belongs to the reroll set, reroll it exactly once; the
   new face is the die's final face. Otherwise the first face is final.
3. If (and only if) the final face is the maximum face F, roll one extra
   bonus dF and add it to that face. The bonus die is never rerolled and
   never triggers another bonus die.

So one original die contributes a value between 1 and 2F.  Value F itself is
impossible: a final face of F always comes with a bonus of 1..F, giving
F+1..2F.

From the n per-die values the largest K are summed.

Every probability here is an exact :class:`fractions.Fraction`.  The returned
distribution always sums to exactly 1 — no Monte Carlo noise.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Dict, FrozenSet, Iterable, List, Tuple

MIN_DICE, MAX_DICE = 1, 6
MIN_FACES, MAX_FACES = 2, 8


def validate_params(
    n_dice: int, faces: int, keep: int, reroll: Iterable[int]
) -> Tuple[int, int, int, FrozenSet[int]]:
    """Validate and normalize the rule parameters.

    Raises ``ValueError`` with a Chinese message on the first problem.
    The reroll collection is deduplicated and returned as a frozenset.
    """
    if not isinstance(n_dice, int) or isinstance(n_dice, bool):
        raise ValueError("原骰数必须是整数")
    if not MIN_DICE <= n_dice <= MAX_DICE:
        raise ValueError(f"原骰数必须在 {MIN_DICE}～{MAX_DICE} 之间")

    if not isinstance(faces, int) or isinstance(faces, bool):
        raise ValueError("面数必须是整数")
    if not MIN_FACES <= faces <= MAX_FACES:
        raise ValueError(f"面数必须在 {MIN_FACES}～{MAX_FACES} 之间")

    if not isinstance(keep, int) or isinstance(keep, bool):
        raise ValueError("保留颗数必须是整数")
    if not 1 <= keep <= n_dice:
        raise ValueError("保留颗数必须在 1～原骰数 之间")

    reroll_set = frozenset(reroll)
    for face in reroll_set:
        if not isinstance(face, int) or isinstance(face, bool):
            raise ValueError("重掷面集合中的值必须是整数")
        if not 1 <= face <= faces:
            raise ValueError(f"重掷面 {face} 超出 1～{faces} 范围")

    return n_dice, faces, keep, reroll_set


def one_die_leaves(faces: int, reroll: FrozenSet[int]) -> List[Tuple[int, Fraction]]:
    """Enumerate every complete random path of a single original die.

    Each entry is ``(value, probability)`` for one leaf of the
    first-roll / reroll / bonus three-level tree.  The leaf probabilities
    sum to exactly 1.  Equal values appear as separate leaves — this is the
    path-level oracle used by the brute-force tests.
    """
    leaves: List[Tuple[int, Fraction]] = []
    for first in range(1, faces + 1):
        if first in reroll:
            # First face is rerolled: p(first)=1/F, p(second)=1/F.  Whether
            # the bonus die is rolled depends on the *final* (second) face,
            # not on the first face that triggered the reroll.
            for second in range(1, faces + 1):
                if second == faces:
                    # Final face is F: three random rolls (first, second,
                    # non-chaining bonus), each leaf has p = 1/F**3.
                    for bonus in range(1, faces + 1):
                        leaves.append((faces + bonus, Fraction(1, faces**3)))
                else:
                    leaves.append((second, Fraction(1, faces**2)))
        elif first == faces:
            # First face F kept: add the bonus dF.
            for bonus in range(1, faces + 1):
                leaves.append((faces + bonus, Fraction(1, faces**2)))
        else:
            leaves.append((first, Fraction(1, faces)))
    return leaves


def one_die_distribution(
    faces: int, reroll: FrozenSet[int]
) -> Dict[int, Fraction]:
    """Exact distribution of one original die's final total value."""
    dist: Dict[int, Fraction] = {}
    for value, probability in one_die_leaves(faces, reroll):
        dist[value] = dist.get(value, Fraction(0)) + probability
    return dist


def _merge_topk(state: Tuple[int, ...], value: int, keep: int) -> Tuple[int, ...]:
    """Insert ``value`` into an ascending tuple, keeping only the K largest."""
    if len(state) < keep:
        return tuple(sorted(state + (value,)))
    # State is ascending, so state[0] is the current smallest kept value.
    # Drop it when the incoming value is larger; ties are kept as-is.
    if value <= state[0]:
        return state
    return tuple(sorted(state[1:] + (value,)))


def top_k_distribution(
    n_dice: int,
    faces: int,
    keep: int,
    reroll: FrozenSet[int],
) -> Dict[int, Fraction]:
    """Exact distribution of the sum of the K largest per-die values.

    Dynamic program over (multiset of the current K largest values).  A
    state is an ascending tuple of length at most K.  After each die the
    new value is merged in and the smallest entries drop out.
    """
    single = one_die_distribution(faces, reroll)

    # state -> probability; start with no dice seen, then fold in each die.
    states: Dict[Tuple[int, ...], Fraction] = {(): Fraction(1)}
    for _ in range(n_dice):
        nxt: Dict[Tuple[int, ...], Fraction] = {}
        for state, state_p in states.items():
            for value, value_p in single.items():
                new_state = _merge_topk(state, value, keep)
                nxt[new_state] = nxt.get(new_state, Fraction(0)) + state_p * value_p
        states = nxt

    totals: Dict[int, Fraction] = {}
    for state, probability in states.items():
        score = sum(state)
        totals[score] = totals.get(score, Fraction(0)) + probability
    return dict(sorted(totals.items()))


def enumerate_distribution(
    n_dice: int,
    faces: int,
    keep: int,
    reroll: FrozenSet[int],
) -> Dict[int, Fraction]:
    """Brute-force oracle: walk every n-dice random path exactly once.

    The Cartesian product of :func:`one_die_leaves` visits each complete
    joint roll path with its exact joint probability; the top-K sum of the
    path aggregates into the result.  Feasible for small face counts, which
    is all the tests need.
    """
    leaves = one_die_leaves(faces, reroll)
    totals: Dict[int, Fraction] = {}
    chosen: List[int] = []

    def walk(index: int, probability: Fraction) -> None:
        if index == n_dice:
            score = sum(sorted(chosen, reverse=True)[:keep])
            totals[score] = totals.get(score, Fraction(0)) + probability
            return
        for value, leaf_p in leaves:
            chosen.append(value)
            walk(index + 1, probability * leaf_p)
            chosen.pop()

    walk(0, Fraction(1))
    return dict(sorted(totals.items()))


def expected_score(distribution: Dict[int, Fraction]) -> Fraction:
    """Exact expectation sum(score * p)."""
    return sum((score * p for score, p in distribution.items()), Fraction(0))


def probability_at_least(distribution: Dict[int, Fraction], threshold: int) -> Fraction:
    """Exact tail probability P(total >= threshold)."""
    return sum(
        (p for score, p in distribution.items() if score >= threshold),
        Fraction(0),
    )

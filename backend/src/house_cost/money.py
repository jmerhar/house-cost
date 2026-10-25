"""Money as whole cents, and splitting an amount into shares that add up to it exactly."""

from collections.abc import Sequence


def allocate(amount_cents: int, weights: Sequence[int]) -> list[int]:
    """Split ``amount_cents`` in proportion to ``weights``, so the parts add up to it exactly.

    Each part is first rounded down; the cents left over go one each to the parts that lost the
    most to rounding (the largest remainder), and a tie goes to the earlier part. Callers list
    households in their configured order, which therefore decides who gets a contested cent.

    A negative amount (a refund or credit) is split as its positive and negated, so a credit is
    shared exactly as the charge it reverses would be. A part with zero weight gets nothing.
    """
    if any(weight < 0 for weight in weights):
        raise ValueError("weights cannot be negative")
    total = sum(weights)
    if total == 0:
        raise ValueError("at least one weight must be positive")
    if amount_cents < 0:
        return [-part for part in allocate(-amount_cents, weights)]

    exact = [amount_cents * weight for weight in weights]
    parts = [share // total for share in exact]
    left = amount_cents - sum(parts)
    # Largest remainder first; `sorted` is stable, so equal remainders keep the parts' order.
    by_remainder = sorted(range(len(weights)), key=lambda i: exact[i] % total, reverse=True)
    for i in by_remainder[:left]:
        parts[i] += 1
    return parts

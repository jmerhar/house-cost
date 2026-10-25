"""Splitting amounts into shares that add up exactly, and settling balances."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from house_cost.balances import HouseholdBalance, settle
from house_cost.models import Household
from house_cost.money import allocate
from house_cost.splitting import split


class TestAllocate:
    def test_an_even_split(self) -> None:
        assert allocate(10_000, [5000, 5000]) == [5000, 5000]

    def test_an_odd_cent_goes_to_the_first_part_on_a_tie(self) -> None:
        assert allocate(15_055, [5000, 5000]) == [7528, 7527]

    def test_the_cent_goes_to_the_largest_remainder(self) -> None:
        # 1 cent at 25/75: 0.25 and 0.75 exactly; the larger remainder wins.
        assert allocate(1, [2500, 7500]) == [0, 1]
        assert allocate(10, [3333, 3333, 3334]) == [3, 3, 4]

    def test_a_zero_weight_gets_nothing(self) -> None:
        assert allocate(999, [0, 10_000, 0]) == [0, 999, 0]

    def test_a_credit_is_split_as_the_charge_it_reverses(self) -> None:
        assert allocate(-15_055, [5000, 5000]) == [-7528, -7527]

    def test_nothing_splits_into_nothing(self) -> None:
        assert allocate(0, [2500, 7500]) == [0, 0]

    @pytest.mark.parametrize("weights", [[0, 0], [], [5000, -5000]])
    def test_weights_must_be_positive_somewhere_and_never_negative(self, weights) -> None:
        with pytest.raises(ValueError):
            allocate(100, weights)

    @given(
        st.integers(min_value=-10_000_000, max_value=10_000_000),
        st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=6).filter(
            lambda weights: sum(weights) > 0
        ),
    )
    def test_the_parts_always_add_up_and_each_is_within_a_cent_of_its_share(
        self, amount: int, weights: list[int]
    ) -> None:
        parts = allocate(amount, weights)

        assert sum(parts) == amount
        total = sum(weights)
        for part, weight in zip(parts, weights, strict=True):
            assert abs(part - amount * weight / total) < 1
            if weight == 0:
                assert part == 0


def _households(*ids: int) -> list[Household]:
    return [Household(id=i, name=f"h{i}", position=n) for n, i in enumerate(ids)]


class TestSplit:
    def test_every_household_gets_a_share_and_the_unnamed_ones_nothing(self) -> None:
        shares = split(1001, {1: 5000, 2: 5000}, _households(1, 2, 3))

        assert [(s.household_id, s.amount_cents) for s in shares] == [(1, 501), (2, 500), (3, 0)]

    def test_shares_for_a_household_that_does_not_exist_are_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown households"):
            split(100, {1: 5000, 9: 5000}, _households(1, 2))


def _position(household_id: int, balance: int) -> HouseholdBalance:
    # A balance made of a payment (positive) or a share owed (negative).
    return HouseholdBalance(
        household_id=household_id,
        name=str(household_id),
        paid_cents=max(balance, 0),
        share_cents=max(-balance, 0),
        adjustment_cents=0,
        sent_cents=0,
        received_cents=0,
    )


class TestSettle:
    def test_two_households_need_one_transfer(self) -> None:
        transfers = settle([_position(1, 9973), _position(2, -9973)])

        assert [(t.from_id, t.to_id, t.amount_cents) for t in transfers] == [(2, 1, 9973)]

    def test_everyone_square_needs_none(self) -> None:
        assert settle([_position(1, 0), _position(2, 0)]) == []

    def test_three_households_need_at_most_two(self) -> None:
        transfers = settle([_position(1, 5000), _position(2, -3000), _position(3, -2000)])

        assert [(t.from_id, t.to_id, t.amount_cents) for t in transfers] == [
            (2, 1, 3000),
            (3, 1, 2000),
        ]

    @given(st.lists(st.integers(min_value=-1_000_000, max_value=1_000_000), min_size=1, max_size=5))
    def test_the_transfers_bring_every_balance_to_zero(self, balances: list[int]) -> None:
        # The last household takes up the remainder, as real balances always add up to zero.
        balances = [*balances, -sum(balances)]
        positions = [_position(i, b) for i, b in enumerate(balances)]

        left = dict(enumerate(balances))
        transfers = settle(positions)
        for transfer in transfers:
            assert transfer.amount_cents > 0
            left[transfer.from_id] += transfer.amount_cents
            left[transfer.to_id] -= transfer.amount_cents

        assert set(left.values()) <= {0}
        assert len(transfers) <= max(len(balances) - 1, 0)

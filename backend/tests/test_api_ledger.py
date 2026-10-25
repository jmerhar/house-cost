"""Rules, bills and balances: the agreement's cases, worked through the API."""

import httpx
import pytest
from helpers import Agreement, bill, ok, shares_of


async def _rule(client, category: int, on: str, *shares: tuple[int, int], note: str = "") -> dict:
    return await ok(
        client.post(
            "/api/rules",
            json={
                "category_id": category,
                "effective_from": on,
                "note": note,
                "shares": [{"household_id": h, "basis_points": bp} for h, bp in shares],
            },
        ),
        201,
    )


class TestRules:
    async def test_the_shares_must_add_up_to_100_percent(
        self, client, agreement: Agreement
    ) -> None:
        response = await client.post(
            "/api/rules",
            json={
                "category_id": agreement.road,
                "effective_from": "2027-01-01",
                "shares": [{"household_id": agreement.lucia, "basis_points": 3000}],
            },
        )
        assert response.status_code == 422
        assert "100%" in response.text

    async def test_a_household_can_have_only_one_share(self, client, agreement: Agreement) -> None:
        response = await client.post(
            "/api/rules",
            json={
                "category_id": agreement.road,
                "effective_from": "2027-01-01",
                "shares": [
                    {"household_id": agreement.lucia, "basis_points": 5000},
                    {"household_id": agreement.lucia, "basis_points": 5000},
                ],
            },
        )
        assert response.status_code == 422

    async def test_two_rules_cannot_start_on_the_same_day(
        self, client, agreement: Agreement
    ) -> None:
        response = await client.post(
            "/api/rules",
            json={
                "category_id": agreement.road,
                "effective_from": "2026-09-05",
                "shares": [{"household_id": agreement.owners, "basis_points": 10000}],
            },
        )
        assert (response.status_code, response.json()["detail"]) == (409, "rule_exists_on_date")

    async def test_a_rule_naming_an_unknown_household_is_refused(
        self, client, agreement: Agreement
    ) -> None:
        response = await client.post(
            "/api/rules",
            json={
                "category_id": agreement.road,
                "effective_from": "2027-01-01",
                "shares": [{"household_id": 999, "basis_points": 10000}],
            },
        )
        assert (response.status_code, response.json()["detail"]) == (422, "unknown_household")

    async def test_a_rule_for_an_unknown_category_is_refused(
        self, client, agreement: Agreement
    ) -> None:
        response = await client.post(
            "/api/rules",
            json={
                "category_id": 999,
                "effective_from": "2027-01-01",
                "shares": [{"household_id": agreement.owners, "basis_points": 10000}],
            },
        )
        assert response.status_code == 404

    async def test_rules_are_listed_with_whether_a_bill_uses_them(
        self, client, agreement: Agreement
    ) -> None:
        later = await _rule(client, agreement.road, "2027-01-01", (agreement.owners, 10000))
        await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.lucia, (agreement.road, 100))
            ),
            201,
        )

        rules = await ok(client.get("/api/rules", params={"category_id": agreement.road}))

        assert [(r["effective_from"], r["in_use"]) for r in rules] == [
            ("2026-09-05", True),
            ("2027-01-01", False),
        ]
        assert later["shares"] == [{"household_id": agreement.owners, "basis_points": 10000}]
        assert len(await ok(client.get("/api/rules"))) == 5

    async def test_only_an_unused_rule_can_be_deleted(self, client, agreement: Agreement) -> None:
        later = await _rule(client, agreement.road, "2027-01-01", (agreement.owners, 10000))
        first = (await ok(client.get("/api/rules", params={"category_id": agreement.road})))[0]
        await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.lucia, (agreement.road, 100))
            ),
            201,
        )

        response = await client.delete(f"/api/rules/{first['id']}")
        assert (response.status_code, response.json()["detail"]) == (409, "rule_in_use")
        assert (await client.delete(f"/api/rules/{later['id']}")).status_code == 204
        assert (await client.delete(f"/api/rules/{later['id']}")).status_code == 404


class TestSplitPreview:
    async def test_shows_the_split_a_line_would_get(self, client, agreement: Agreement) -> None:
        preview = await ok(
            client.get(
                "/api/split-preview",
                params={"category_id": agreement.road, "on": "2026-10-01", "amount_cents": 10001},
            )
        )
        assert shares_of(preview) == {agreement.lucia: 4000, agreement.owners: 6001}

    async def test_before_any_rule_there_is_no_split(self, client, agreement: Agreement) -> None:
        response = await client.get(
            "/api/split-preview",
            params={"category_id": agreement.road, "on": "2026-09-04", "amount_cents": 100},
        )
        assert (response.status_code, response.json()["detail"]) == (422, "no_rule")


class TestBills:
    async def test_electricity_is_split_evenly_with_the_odd_cent_to_the_first_household(
        self, client, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 28759),
                    supplier="MEO Energia",
                    invoice_number="FA MEA26/100001",
                    period_start="2026-09-13",
                    period_end="2026-10-16",
                    due_date="2026-11-03",
                ),
            ),
            201,
        )

        assert created["total_cents"] == 28759
        assert shares_of(created["lines"][0]) == {agreement.lucia: 14380, agreement.owners: 14379}
        assert created["supplier"] == "MEO Energia"
        assert created["locked"] is False

    async def test_road_upkeep_is_split_a_quarter_to_three_quarters(
        self, client, agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-05", agreement.lucia, (agreement.road, 10000))
            ),
            201,
        )

        assert shares_of(created["lines"][0]) == {agreement.lucia: 4000, agreement.owners: 6000}

    async def test_a_new_rule_applies_from_its_first_day(
        self, client, agreement: Agreement
    ) -> None:
        third = await ok(client.post("/api/households", json={"name": "Third", "position": 2}), 201)
        await _rule(
            client,
            agreement.electricity,
            "2027-01-01",
            (agreement.lucia, 4000),
            (agreement.owners, 4000),
            (third["id"], 2000),
        )
        before = await ok(
            client.post(
                "/api/bills",
                json=bill("2026-12-31", agreement.lucia, (agreement.electricity, 10000)),
            ),
            201,
        )
        on_the_day = await ok(
            client.post(
                "/api/bills", json=bill("2027-01-01", third["id"], (agreement.electricity, 10000))
            ),
            201,
        )

        assert shares_of(before["lines"][0]) == {
            agreement.lucia: 5000,
            agreement.owners: 5000,
            third["id"]: 0,
        }
        assert shares_of(on_the_day["lines"][0]) == {
            agreement.lucia: 4000,
            agreement.owners: 4000,
            third["id"]: 2000,
        }

    async def test_a_bill_before_any_rule_cannot_be_split(
        self, client, agreement: Agreement
    ) -> None:
        response = await client.post(
            "/api/bills", json=bill("2026-09-01", agreement.lucia, (agreement.smas, 4000))
        )

        assert (response.status_code, response.json()["detail"]) == (422, "no_rule")

    async def test_a_mixed_bill_splits_each_line_by_its_own_rule(
        self, client, agreement: Agreement
    ) -> None:
        mobile = await ok(
            client.post("/api/categories", json={"name": "Mobile (Tiago + Marta)"}), 201
        )
        await _rule(client, mobile["id"], "2026-09-05", (agreement.owners, 10000))
        payload = bill(
            "2026-09-21", agreement.lucia, (agreement.electricity, 1837), (mobile["id"], 161)
        )
        payload["lines"][0]["description"] = "M4 package"
        created = await ok(client.post("/api/bills", json=payload), 201)

        assert created["total_cents"] == 1998
        internet, phone = created["lines"]
        assert internet["description"] == "M4 package"
        assert shares_of(internet) == {agreement.lucia: 919, agreement.owners: 918}
        assert shares_of(phone) == {agreement.lucia: 0, agreement.owners: 161}
        # Lúcia paid all of it; the owners owe her their half of the package and all the phone.
        balances = await ok(client.get("/api/balances"))
        assert {h["household_id"]: h["balance_cents"] for h in balances["households"]} == {
            agreement.lucia: 1998 - 919,
            agreement.owners: -(918 + 161),
        }

    async def test_a_refund_is_split_like_the_charge(self, client, agreement: Agreement) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill("2026-11-01", agreement.owners, (agreement.electricity, -1001)),
            ),
            201,
        )

        assert created["total_cents"] == -1001
        assert shares_of(created["lines"][0]) == {agreement.lucia: -501, agreement.owners: -500}

    async def test_a_bill_needs_a_known_payer_and_categories(
        self, client, agreement: Agreement
    ) -> None:
        unknown_payer = await client.post(
            "/api/bills", json=bill("2026-10-01", 999, (agreement.road, 100))
        )
        unknown_category = await client.post(
            "/api/bills", json=bill("2026-10-01", agreement.lucia, (999, 100))
        )
        no_lines = await client.post("/api/bills", json=bill("2026-10-01", agreement.lucia))
        backwards = await client.post(
            "/api/bills",
            json=bill(
                "2026-10-01",
                agreement.lucia,
                (agreement.road, 100),
                period_start="2026-10-02",
                period_end="2026-10-01",
            ),
        )

        assert (unknown_payer.status_code, unknown_payer.json()["detail"]) == (
            422,
            "unknown_household",
        )
        assert (unknown_category.status_code, unknown_category.json()["detail"]) == (
            422,
            "unknown_category",
        )
        assert no_lines.status_code == 422
        assert backwards.status_code == 422

    async def test_a_correction_keeps_the_split_of_unchanged_lines(
        self, client, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-01", agreement.lucia, (agreement.road, 10000), (agreement.smas, 4001)
                ),
            ),
            201,
        )
        # A rule back-dated before the bill: a later correction of the description must not
        # quietly re-split the lines it did not touch.
        await _rule(client, agreement.road, "2026-09-30", (agreement.owners, 10000))
        road, smas = created["lines"]
        corrected = await ok(
            client.put(
                f"/api/bills/{created['id']}",
                json={
                    **bill("2026-10-01", agreement.lucia),
                    "description": "corrected",
                    "lines": [
                        {
                            "id": road["id"],
                            "category_id": agreement.road,
                            "amount_cents": 10000,
                            "description": "renamed",
                        },
                        {"id": smas["id"], "category_id": agreement.smas, "amount_cents": 5000},
                    ],
                },
            )
        )

        new_road, new_smas = corrected["lines"]
        assert corrected["description"] == "corrected"
        assert (new_road["id"], new_road["description"]) == (road["id"], "renamed")
        assert shares_of(new_road) == {agreement.lucia: 4000, agreement.owners: 6000}
        assert new_road["rule_id"] == road["rule_id"]
        assert shares_of(new_smas) == {agreement.lucia: 2500, agreement.owners: 2500}
        assert corrected["total_cents"] == 15000

    async def test_changing_the_date_splits_every_line_again(
        self, client, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.lucia, (agreement.road, 10000))
            ),
            201,
        )
        await _rule(client, agreement.road, "2027-01-01", (agreement.owners, 10000))
        line = created["lines"][0]
        moved = await ok(
            client.put(
                f"/api/bills/{created['id']}",
                json={
                    **bill("2027-02-01", agreement.lucia),
                    "lines": [
                        {"id": line["id"], "category_id": agreement.road, "amount_cents": 10000}
                    ],
                },
            )
        )
        assert shares_of(moved["lines"][0]) == {agreement.lucia: 0, agreement.owners: 10000}

    async def test_lines_can_be_added_and_removed(self, client, agreement: Agreement) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-01", agreement.lucia, (agreement.road, 100), (agreement.smas, 200)
                ),
            ),
            201,
        )
        keep = created["lines"][1]
        changed = await ok(
            client.put(
                f"/api/bills/{created['id']}",
                json={
                    **bill("2026-10-01", agreement.lucia),
                    "lines": [
                        {"id": keep["id"], "category_id": agreement.smas, "amount_cents": 200},
                        {"category_id": agreement.electricity, "amount_cents": 300},
                    ],
                },
            )
        )
        assert [(line["category_id"], line["amount_cents"]) for line in changed["lines"]] == [
            (agreement.smas, 200),
            (agreement.electricity, 300),
        ]

    async def test_a_line_of_another_bill_cannot_be_borrowed(
        self, client, agreement: Agreement
    ) -> None:
        one = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.lucia, (agreement.road, 100))
            ),
            201,
        )
        two = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-02", agreement.lucia, (agreement.road, 100))
            ),
            201,
        )
        response = await client.put(
            f"/api/bills/{two['id']}",
            json={
                **bill("2026-10-02", agreement.lucia),
                "lines": [
                    {
                        "id": one["lines"][0]["id"],
                        "category_id": agreement.road,
                        "amount_cents": 100,
                    }
                ],
            },
        )
        assert (response.status_code, response.json()["detail"]) == (422, "unknown_line")

    async def test_a_deleted_bill_is_gone_from_lists_and_balances(
        self, client, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.lucia, (agreement.road, 10000))
            ),
            201,
        )

        assert (await client.delete(f"/api/bills/{created['id']}")).status_code == 204
        assert (await client.get(f"/api/bills/{created['id']}")).status_code == 404
        assert (
            await client.put(
                f"/api/bills/{created['id']}",
                json=bill("2026-10-01", agreement.lucia, (agreement.road, 1)),
            )
        ).status_code == 404
        assert (await ok(client.get("/api/bills")))["total"] == 0
        balances = await ok(client.get("/api/balances"))
        assert {h["balance_cents"] for h in balances["households"]} == {0}

    async def test_anyone_can_enter_and_correct_bills(
        self, member: httpx.AsyncClient, agreement: Agreement
    ) -> None:
        created = await ok(
            member.post(
                "/api/bills", json=bill("2026-10-01", agreement.owners, (agreement.road, 100))
            ),
            201,
        )
        await ok(
            member.put(
                f"/api/bills/{created['id']}",
                json=bill("2026-10-01", agreement.owners, (agreement.road, 200)),
            )
        )
        assert (await member.delete(f"/api/bills/{created['id']}")).status_code == 204


class TestListingBills:
    @pytest.fixture
    async def bills(self, client, agreement: Agreement) -> None:
        for payload in (
            bill(
                "2026-10-18",
                agreement.owners,
                (agreement.electricity, 28759),
                supplier="MEO Energia",
            ),
            bill("2026-11-02", agreement.lucia, (agreement.road, 5000), description="Gravel"),
            bill("2027-01-15", agreement.lucia, (agreement.smas, 4868), invoice_number="SMAS-1"),
        ):
            await ok(client.post("/api/bills", json=payload), 201)

    async def test_newest_first(self, client, bills) -> None:
        page = await ok(client.get("/api/bills"))
        assert [b["date"] for b in page["items"]] == ["2027-01-15", "2026-11-02", "2026-10-18"]
        assert page["total"] == 3

    @pytest.mark.parametrize(
        ("params", "dates"),
        [
            ({"year": 2026}, ["2026-11-02", "2026-10-18"]),
            ({"q": "meo"}, ["2026-10-18"]),
            ({"q": "gravel"}, ["2026-11-02"]),
            ({"q": "smas-1"}, ["2027-01-15"]),
            ({"limit": 1, "offset": 1}, ["2026-11-02"]),
        ],
    )
    async def test_narrowed(self, client, bills, params, dates) -> None:
        page = await ok(client.get("/api/bills", params=params))
        assert [b["date"] for b in page["items"]] == dates

    async def test_by_category_and_payer(self, client, agreement: Agreement, bills) -> None:
        by_category = await ok(client.get("/api/bills", params={"category_id": agreement.road}))
        by_payer = await ok(client.get("/api/bills", params={"paid_by_id": agreement.owners}))
        assert [b["date"] for b in by_category["items"]] == ["2026-11-02"]
        assert [b["date"] for b in by_payer["items"]] == ["2026-10-18"]


class TestBalances:
    async def test_the_spreadsheet_case(self, client, agreement: Agreement) -> None:
        # The case worked by hand when the split was a spreadsheet: the owners end up owing
        # Lúcia €84.73.
        for payload in (
            bill("2026-10-01", agreement.owners, (agreement.electricity, 15054)),
            bill("2026-10-05", agreement.lucia, (agreement.road, 10000)),
            bill("2026-12-31", agreement.lucia, (agreement.electricity, 10000)),
        ):
            await ok(client.post("/api/bills", json=payload), 201)
        await ok(
            client.post(
                "/api/settlements",
                json={
                    "date": "2026-10-10",
                    "from_id": agreement.lucia,
                    "to_id": agreement.owners,
                    "amount_cents": 5000,
                },
            ),
            201,
        )

        result = await ok(client.get("/api/balances"))
        by_id = {h["household_id"]: h for h in result["households"]}

        assert by_id[agreement.lucia] == {
            "household_id": agreement.lucia,
            "name": "Lúcia",
            "paid_cents": 20000,
            "share_cents": 7527 + 4000 + 5000,
            "adjustment_cents": 0,
            "sent_cents": 5000,
            "received_cents": 0,
            "balance_cents": 8473,
        }
        assert by_id[agreement.owners]["balance_cents"] == -8473
        assert result["transfers"] == [
            {"from_id": agreement.owners, "to_id": agreement.lucia, "amount_cents": 8473}
        ]

    async def test_everyone_square_at_the_start(self, client, agreement: Agreement) -> None:
        result = await ok(client.get("/api/balances"))
        assert [h["balance_cents"] for h in result["households"]] == [0, 0]
        assert result["transfers"] == []


class TestSettlements:
    async def test_recorded_corrected_and_deleted(
        self, client, member, agreement: Agreement
    ) -> None:
        created = await ok(
            member.post(
                "/api/settlements",
                json={
                    "date": "2026-11-01",
                    "from_id": agreement.owners,
                    "to_id": agreement.lucia,
                    "amount_cents": 9973,
                    "note": "MB Way",
                },
            ),
            201,
        )
        updated = await ok(
            member.put(
                f"/api/settlements/{created['id']}",
                json={
                    "date": "2026-11-02",
                    "from_id": agreement.owners,
                    "to_id": agreement.lucia,
                    "amount_cents": 9900,
                },
            )
        )
        assert (updated["date"], updated["amount_cents"], updated["note"]) == (
            "2026-11-02",
            9900,
            "",
        )
        assert [
            s["id"] for s in await ok(client.get("/api/settlements", params={"year": 2026}))
        ] == [created["id"]]
        assert await ok(client.get("/api/settlements", params={"year": 2025})) == []

        assert (await member.delete(f"/api/settlements/{created['id']}")).status_code == 204
        assert await ok(client.get("/api/settlements")) == []
        assert (await member.delete(f"/api/settlements/{created['id']}")).status_code == 404

    @pytest.mark.parametrize(
        "change",
        [{"to_id": "same"}, {"amount_cents": 0}, {"amount_cents": -5}],
    )
    async def test_must_be_a_positive_amount_between_two_households(
        self, client, agreement: Agreement, change
    ) -> None:
        payload = {
            "date": "2026-11-01",
            "from_id": agreement.owners,
            "to_id": agreement.lucia,
            "amount_cents": 100,
        }
        payload.update(change)
        if payload["to_id"] == "same":
            payload["to_id"] = agreement.owners
        assert (await client.post("/api/settlements", json=payload)).status_code == 422

    async def test_needs_known_households(self, client, agreement: Agreement) -> None:
        response = await client.post(
            "/api/settlements",
            json={
                "date": "2026-11-01",
                "from_id": 999,
                "to_id": agreement.lucia,
                "amount_cents": 100,
            },
        )
        assert (response.status_code, response.json()["detail"]) == (422, "unknown_household")

"""Households, people and categories, as an admin keeps them."""

import pytest
from helpers import PASSWORD, Agreement, ok


class TestHouseholds:
    async def test_listed_in_their_order(self, client, agreement: Agreement) -> None:
        await ok(client.post("/api/households", json={"name": "Third", "position": 2}), 201)
        await ok(
            client.put(f"/api/households/{agreement.lucia}", json={"name": "Lúcia", "position": 5})
        )

        names = [h["name"] for h in await ok(client.get("/api/households"))]
        assert names == ["Tiago + Marta", "Third", "Lúcia"]

    async def test_names_are_unique(self, client, agreement: Agreement) -> None:
        create = await client.post("/api/households", json={"name": "Lúcia"})
        rename = await client.put(f"/api/households/{agreement.owners}", json={"name": "Lúcia"})

        assert (create.status_code, create.json()["detail"]) == (409, "name_taken")
        assert (rename.status_code, rename.json()["detail"]) == (409, "name_taken")

    async def test_an_unknown_household_is_a_404(self, client, admin) -> None:
        assert (await client.put("/api/households/999", json={"name": "X"})).status_code == 404


class TestPeople:
    async def test_an_admin_gives_someone_a_login(
        self, client, agreement: Agreement, new_client
    ) -> None:
        marta = await ok(
            client.post(
                "/api/people",
                json={
                    "name": "Marta",
                    "login": "Marta",
                    "household_id": agreement.owners,
                    "password": PASSWORD,
                    "language": "pt-PT",
                },
            ),
            201,
        )
        assert (marta["login"], marta["role"], marta["language"]) == (
            "marta",
            "member",
            "pt-PT",
        )
        me = await ok(
            new_client().post("/api/auth/login", json={"login": "marta", "password": PASSWORD})
        )
        assert me["household_name"] == "Tiago + Marta"
        assert [p["name"] for p in await ok(client.get("/api/people"))] == ["Lúcia", "Marta"]

    async def test_logins_are_unique_and_households_must_exist(
        self, client, agreement: Agreement
    ) -> None:
        taken = await client.post(
            "/api/people",
            json={
                "name": "G",
                "login": "LUCIA",
                "household_id": agreement.owners,
                "password": PASSWORD,
            },
        )
        nowhere = await client.post(
            "/api/people",
            json={"name": "X", "login": "x", "household_id": 999, "password": PASSWORD},
        )
        assert (taken.status_code, taken.json()["detail"]) == (409, "login_taken")
        assert (nowhere.status_code, nowhere.json()["detail"]) == (422, "unknown_household")

    async def test_the_last_admin_cannot_step_down(self, client, admin: dict) -> None:
        demote = await client.put(
            f"/api/people/{admin['id']}",
            json={
                "name": "Lúcia",
                "login": "lucia",
                "role": "member",
                "household_id": admin["household_id"],
                "active": True,
            },
        )
        deactivate = await client.put(
            f"/api/people/{admin['id']}",
            json={
                "name": "Lúcia",
                "login": "lucia",
                "role": "admin",
                "household_id": admin["household_id"],
                "active": False,
            },
        )
        assert (demote.status_code, demote.json()["detail"]) == (409, "last_admin")
        assert deactivate.status_code == 409

    async def test_an_admin_can_step_down_once_there_is_another(
        self, client, admin: dict, member, agreement
    ) -> None:
        tiago = next(p for p in await ok(client.get("/api/people")) if p["login"] == "tiago")
        await ok(client.put(f"/api/people/{tiago['id']}", json={**tiago, "role": "admin"}))

        me = await ok(
            client.put(
                f"/api/people/{admin['id']}",
                json={
                    "name": "Lúcia",
                    "login": "lucia",
                    "role": "member",
                    "household_id": admin["household_id"],
                    "active": True,
                },
            )
        )
        assert me["role"] == "member"
        assert (await client.post("/api/categories", json={"name": "Pool"})).status_code == 403
        assert (await member.post("/api/categories", json={"name": "Pool"})).status_code == 201

    async def test_a_reset_password_logs_the_person_out(
        self, client, member, agreement, new_client
    ) -> None:
        tiago = next(p for p in await ok(client.get("/api/people")) if p["login"] == "tiago")
        await ok(
            client.put(f"/api/people/{tiago['id']}", json={**tiago, "password": "reset by lucia"})
        )

        assert (await member.get("/api/auth/me")).status_code == 401
        await ok(
            new_client().post(
                "/api/auth/login", json={"login": "tiago", "password": "reset by lucia"}
            )
        )

    async def test_an_edit_needs_a_known_person_and_a_free_login(
        self, client, member, agreement
    ) -> None:
        tiago = next(p for p in await ok(client.get("/api/people")) if p["login"] == "tiago")
        missing = await client.put("/api/people/999", json={**tiago})
        taken = await client.put(f"/api/people/{tiago['id']}", json={**tiago, "login": "lucia"})

        assert missing.status_code == 404
        assert (taken.status_code, taken.json()["detail"]) == (409, "login_taken")


class TestCategories:
    async def test_listed_by_name_and_editable(self, client, agreement: Agreement) -> None:
        await ok(
            client.put(
                f"/api/categories/{agreement.road}",
                json={"name": "Access road", "description": "Routine upkeep", "active": True},
            )
        )
        categories = await ok(client.get("/api/categories"))

        assert [c["name"] for c in categories] == [
            "Access road",
            "Electricity",
            "Other upkeep and major works",
            "SMAS",
        ]
        assert categories[0]["description"] == "Routine upkeep"

    async def test_names_are_unique(self, client, agreement: Agreement) -> None:
        create = await client.post("/api/categories", json={"name": "SMAS"})
        rename = await client.put(f"/api/categories/{agreement.road}", json={"name": "SMAS"})

        assert (create.status_code, create.json()["detail"]) == (409, "name_taken")
        assert (rename.status_code, rename.json()["detail"]) == (409, "name_taken")


class TestSettings:
    async def test_reconciliation_is_off_until_an_admin_turns_it_on(
        self, client, member, admin
    ) -> None:
        assert await ok(member.get("/api/settings")) == {
            "reconciliation_enabled": False,
            "site_title": "",
        }
        await ok(client.put("/api/settings", json={"reconciliation_enabled": True}))

        assert (await ok(member.get("/api/settings")))["reconciliation_enabled"] is True
        assert (await ok(member.get("/api/auth/me")))["reconciliation_enabled"] is True

    async def test_the_apps_name_is_set_by_an_admin_and_shown_before_login(
        self, client, admin, new_client
    ) -> None:
        saved = await ok(client.put("/api/settings", json={"site_title": "  Oliveiras  "}))
        stranger = new_client()

        assert saved == {"reconciliation_enabled": False, "site_title": "Oliveiras"}
        assert (await ok(stranger.get("/api/setup")))["title"] == "Oliveiras"
        manifest = (await stranger.get("/manifest.webmanifest")).json()
        assert (manifest["name"], manifest["short_name"]) == ("Oliveiras", "Oliveiras")

        await ok(client.put("/api/settings", json={"site_title": ""}))
        assert (await ok(stranger.get("/api/setup")))["title"] is None
        assert (await stranger.get("/manifest.webmanifest")).json()["name"] == "House costs"
        too_long = await client.put("/api/settings", json={"site_title": "x" * 61})
        assert too_long.status_code == 422


async def test_only_known_settings_can_be_stored(app) -> None:
    from house_cost.audit import set_setting
    from house_cost.db import session_scope

    async with session_scope(app.state.services.sessionmaker) as db:
        with pytest.raises(KeyError):
            await set_setting(db, "no_such_setting", True)

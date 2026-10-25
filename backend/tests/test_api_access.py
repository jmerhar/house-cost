"""Who can reach what: setup, logging in and out, sessions, and the guard on every write."""

import re

import httpx
import pytest
from fastapi import FastAPI
from helpers import PASSWORD, ok

from house_cost.api.deps import SESSION_COOKIE
from house_cost.auth import WRITE_HEADER, WRITE_HEADER_VALUE
from house_cost.config import Settings

#: The only routes open without a session.
PUBLIC = {("GET", "/api/health"), ("GET", "/api/setup"), ("POST", "/api/setup"),
          ("POST", "/api/auth/login"), ("POST", "/api/auth/logout")}  # fmt: skip


class TestSetup:
    async def test_needed_until_someone_exists(self, client: httpx.AsyncClient) -> None:
        assert (await ok(client.get("/api/setup"))) == {"required": True}

    async def test_creates_the_admin_and_their_household_and_logs_them_in(
        self, client: httpx.AsyncClient, admin: dict
    ) -> None:
        assert admin["role"] == "admin"
        assert admin["household_name"] == "Lúcia"
        assert admin["reconciliation_enabled"] is False
        assert (await ok(client.get("/api/auth/me")))["login"] == "lucia"
        assert (await ok(client.get("/api/setup"))) == {"required": False}

    async def test_is_closed_for_good_once_done(
        self, client: httpx.AsyncClient, admin: dict, new_client
    ) -> None:
        stranger = new_client()
        response = await stranger.post(
            "/api/setup",
            json={"household_name": "X", "name": "X", "login": "x", "password": PASSWORD},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "already_set_up"

    async def test_needs_a_long_enough_password(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/setup",
            json={"household_name": "H", "name": "N", "login": "n", "password": "short"},
        )
        assert response.status_code == 422


class TestLogin:
    async def test_logs_in_with_the_right_password_in_any_case(
        self, admin: dict, new_client
    ) -> None:
        browser = new_client()
        me = await ok(
            browser.post("/api/auth/login", json={"login": " LUCIA ", "password": PASSWORD})
        )

        assert me["login"] == "lucia"
        cookie = browser.cookies.get(SESSION_COOKIE)
        assert cookie and len(cookie) > 30

    async def test_the_cookie_is_httponly_and_lax(self, admin: dict, new_client) -> None:
        response = await new_client().post(
            "/api/auth/login", json={"login": "lucia", "password": PASSWORD}
        )
        header = response.headers["set-cookie"].lower()

        assert "httponly" in header and "samesite=lax" in header
        assert "secure" not in header  # plain http in the tests

    @pytest.mark.parametrize("login", ["lucia", "nobody"])
    async def test_a_wrong_password_and_an_unknown_login_are_refused_alike(
        self, admin: dict, new_client, login: str
    ) -> None:
        response = await new_client().post(
            "/api/auth/login", json={"login": login, "password": "wrong password"}
        )

        assert (response.status_code, response.json()["detail"]) == (401, "invalid_login")

    async def test_too_many_failures_are_refused_for_a_while(
        self, admin: dict, new_client, settings: Settings
    ) -> None:
        browser = new_client()
        for _ in range(settings.login_attempts_per_minute):
            await browser.post(
                "/api/auth/login", json={"login": "lucia", "password": "wrong password"}
            )
        response = await browser.post(
            "/api/auth/login", json={"login": "lucia", "password": PASSWORD}
        )

        assert (response.status_code, response.json()["detail"]) == (429, "too_many_attempts")

    async def test_a_deactivated_person_cannot_log_in(self, client, member, agreement) -> None:
        people = await ok(client.get("/api/people"))
        tiago = next(p for p in people if p["login"] == "tiago")
        await ok(client.put(f"/api/people/{tiago['id']}", json={**tiago, "active": False}))

        assert (await member.get("/api/auth/me")).status_code == 401
        response = await member.post(
            "/api/auth/login", json={"login": "tiago", "password": PASSWORD}
        )
        assert response.status_code == 401

    async def test_logging_out_ends_the_session(
        self, client: httpx.AsyncClient, admin: dict
    ) -> None:
        token = client.cookies.get(SESSION_COOKIE)
        assert (await client.post("/api/auth/logout")).status_code == 204

        assert (await client.get("/api/auth/me")).status_code == 401
        client.cookies.set(SESSION_COOKIE, token)
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_logging_out_without_a_session_is_harmless(
        self, client: httpx.AsyncClient
    ) -> None:
        assert (await client.post("/api/auth/logout")).status_code == 204


class TestOwnAccount:
    async def test_name_and_language_can_be_changed(
        self, client: httpx.AsyncClient, admin: dict
    ) -> None:
        me = await ok(client.patch("/api/auth/me", json={"name": "Lúcia M.", "language": "pt-PT"}))

        assert (me["name"], me["language"]) == ("Lúcia M.", "pt-PT")

    async def test_a_new_password_needs_the_current_one(
        self, client: httpx.AsyncClient, admin: dict
    ) -> None:
        response = await client.patch(
            "/api/auth/me", json={"name": "Lúcia", "new_password": "a brand new password"}
        )
        assert (response.status_code, response.json()["detail"]) == (400, "wrong_password")
        response = await client.patch(
            "/api/auth/me",
            json={
                "name": "Lúcia",
                "current_password": "nope",
                "new_password": "a brand new password",
            },
        )
        assert response.status_code == 400

    async def test_changing_the_password_logs_out_every_other_browser(
        self, client: httpx.AsyncClient, admin: dict, new_client
    ) -> None:
        other = new_client()
        await ok(other.post("/api/auth/login", json={"login": "lucia", "password": PASSWORD}))
        await ok(
            client.patch(
                "/api/auth/me",
                json={
                    "name": "Lúcia",
                    "current_password": PASSWORD,
                    "new_password": "a brand new password",
                },
            )
        )

        assert (await client.get("/api/auth/me")).status_code == 200
        assert (await other.get("/api/auth/me")).status_code == 401
        fresh = new_client()
        await ok(
            fresh.post(
                "/api/auth/login", json={"login": "lucia", "password": "a brand new password"}
            )
        )

    async def test_sessions_can_be_listed_and_ended(
        self, client: httpx.AsyncClient, admin: dict, new_client
    ) -> None:
        other = new_client()
        await ok(other.post("/api/auth/login", json={"login": "lucia", "password": PASSWORD}))
        sessions = await ok(client.get("/api/auth/sessions"))

        assert len(sessions) == 2
        assert [s["current"] for s in sessions].count(True) == 1
        theirs = next(s for s in sessions if not s["current"])
        assert (await client.delete(f"/api/auth/sessions/{theirs['id']}")).status_code == 204
        assert (await other.get("/api/auth/me")).status_code == 401

    async def test_someone_elses_session_cannot_be_ended(self, client, member) -> None:
        mine = await ok(member.get("/api/auth/sessions"))
        response = await client.delete(f"/api/auth/sessions/{mine[0]['id']}")

        assert response.status_code == 404
        assert (await member.get("/api/auth/me")).status_code == 200


def _routes(app: FastAPI) -> list[tuple[str, str]]:
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


async def test_every_route_but_the_public_ones_needs_a_session(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    refused = []
    for method, path in _routes(app):
        if (method, path) in PUBLIC:
            continue
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        response = await client.request(method, concrete, json={})
        if response.status_code != 401:
            refused.append((method, path, response.status_code))

    assert refused == [], "these answered without a session"


async def test_the_public_routes_are_the_ones_listed(app: FastAPI) -> None:
    # A new public route has to be added to PUBLIC on purpose, after thought.
    assert set(_routes(app)) >= PUBLIC


async def test_members_cannot_use_admin_routes(member: httpx.AsyncClient, agreement) -> None:
    attempts = [
        ("POST", "/api/households", {"name": "Third"}),
        ("PUT", f"/api/households/{agreement.lucia}", {"name": "Mine now"}),
        ("POST", "/api/people", {"name": "X", "login": "x", "household_id": agreement.owners, "password": PASSWORD}),  # noqa: E501
        ("PUT", "/api/people/1", {"name": "X", "login": "lucia", "role": "member", "household_id": agreement.lucia, "active": True}),  # noqa: E501
        ("POST", "/api/categories", {"name": "Pool"}),
        ("PUT", f"/api/categories/{agreement.road}", {"name": "Road"}),
        ("POST", "/api/rules", {"category_id": agreement.road, "effective_from": "2027-01-01", "shares": [{"household_id": agreement.owners, "basis_points": 10000}]}),  # noqa: E501
        ("DELETE", "/api/rules/1", None),
        ("PUT", "/api/settings", {"reconciliation_enabled": True}),
    ]  # fmt: skip
    for method, path, body in attempts:
        response = await member.request(method, path, json=body)
        assert (response.status_code, response.json()["detail"]) == (403, "admin_only"), path


class TestWriteGuard:
    async def test_a_write_without_the_header_is_refused(
        self, admin: dict, client, new_client
    ) -> None:
        bare = new_client(write_header=False)
        bare.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE))
        response = await bare.post("/api/categories", json={"name": "Forged"})

        assert (response.status_code, response.json()["detail"]) == (403, "missing_write_header")
        assert (await bare.get("/api/categories")).status_code == 200

    async def test_a_write_from_another_origin_is_refused(self, admin: dict, client) -> None:
        response = await client.post(
            "/api/categories", json={"name": "Forged"}, headers={"Origin": "https://evil.test"}
        )
        assert (response.status_code, response.json()["detail"]) == (403, "foreign_origin")

    async def test_a_write_from_the_public_url_is_allowed(self, data_dir) -> None:
        from house_cost.api.app import create_app
        from house_cost.models import Base

        app = create_app(Settings(data_dir=data_dir, public_url="https://costs.example.com"))
        async with app.router.lifespan_context(app):
            async with app.state.services.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:18091"
            ) as c:
                response = await c.post(
                    "/api/setup",
                    json={"household_name": "H", "name": "N", "login": "n", "password": PASSWORD},
                    headers={
                        WRITE_HEADER: WRITE_HEADER_VALUE,
                        "Origin": "https://costs.example.com",
                    },
                )
        assert response.status_code == 201


class TestSecureCookie:
    async def _cookie(self, settings: Settings, base_url: str) -> str:
        from house_cost.api.app import create_app
        from house_cost.models import Base

        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with app.state.services.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url=base_url, headers={WRITE_HEADER: WRITE_HEADER_VALUE}
            ) as c:
                response = await c.post(
                    "/api/setup",
                    json={"household_name": "H", "name": "N", "login": "n", "password": PASSWORD},
                )
        return response.headers["set-cookie"].lower()

    async def test_secure_over_https(self, data_dir) -> None:
        assert "secure" in await self._cookie(Settings(data_dir=data_dir), "https://costs.test")

    async def test_secure_when_configured_so_whatever_the_scheme(self, data_dir) -> None:
        assert "secure" in await self._cookie(
            Settings(data_dir=data_dir, cookie_secure=True), "http://t"
        )

    async def test_not_secure_when_configured_off(self, data_dir) -> None:
        assert "secure" not in await self._cookie(
            Settings(data_dir=data_dir, cookie_secure=False), "https://costs.test"
        )

"""Adding passkeys and logging in with them, against a software authenticator."""

import pytest
from helpers import ok
from softauthn import SoftAuthenticator, b64

from house_cost.passkeys import Ceremonies, party

ORIGIN = "http://house-cost.test"


async def add_passkey(client, authenticator: SoftAuthenticator, label: str = "iPhone") -> dict:
    options = await ok(client.post("/api/auth/passkeys/options"))
    return await ok(
        client.post(
            "/api/auth/passkeys",
            json={"label": label, "credential": authenticator.register(options)},
        ),
        201,
    )


async def passkey_login(browser, authenticator: SoftAuthenticator, **answer):
    options = await ok(browser.post("/api/auth/passkey-login/options"))
    return await browser.post(
        "/api/auth/passkey-login",
        json={"credential": authenticator.authenticate(options, **answer)},
    )


@pytest.fixture
def authenticator() -> SoftAuthenticator:
    return SoftAuthenticator(origin=ORIGIN)


class TestAdding:
    async def test_the_options_name_the_site_and_ask_for_a_discoverable_passkey(
        self, client, admin
    ) -> None:
        options = await ok(client.post("/api/auth/passkeys/options"))

        assert options["rp"] == {"id": "house-cost.test", "name": "House costs"}
        assert options["user"]["name"] == "lucia"
        assert options["authenticatorSelection"]["residentKey"] == "required"
        assert options["excludeCredentials"] == []

    async def test_a_passkey_is_added_listed_and_named(self, client, admin, authenticator) -> None:
        added = await add_passkey(client, authenticator)

        assert added["label"] == "iPhone" and added["last_used_at"] is None
        assert [p["label"] for p in await ok(client.get("/api/auth/passkeys"))] == ["iPhone"]
        again = await ok(client.post("/api/auth/passkeys/options"))
        assert again["excludeCredentials"][0]["id"] == b64(authenticator.credentials[0].id)

    async def test_the_handle_stays_the_same_across_passkeys(
        self, client, admin, authenticator
    ) -> None:
        first = await ok(client.post("/api/auth/passkeys/options"))
        second = await ok(client.post("/api/auth/passkeys/options"))
        assert first["user"]["id"] == second["user"]["id"]

    async def test_an_answer_from_another_origin_is_rejected(
        self, client, admin, authenticator
    ) -> None:
        options = await ok(client.post("/api/auth/passkeys/options"))
        credential = authenticator.register(options, origin="https://evil.test")
        response = await client.post(
            "/api/auth/passkeys", json={"label": "x", "credential": credential}
        )

        assert (response.status_code, response.json()["detail"]) == (400, "passkey_rejected")

    async def test_an_answer_without_a_ceremony_is_refused(
        self, client, admin, authenticator, new_client
    ) -> None:
        options = await ok(client.post("/api/auth/passkeys/options"))
        credential = authenticator.register(options)
        client.cookies.delete("hc_webauthn", path="/api/auth")
        response = await client.post(
            "/api/auth/passkeys", json={"label": "x", "credential": credential}
        )

        assert (response.status_code, response.json()["detail"]) == (400, "passkey_expired")

    async def test_a_ceremony_is_good_for_one_answer(self, client, admin, authenticator) -> None:
        options = await ok(client.post("/api/auth/passkeys/options"))
        credential = authenticator.register(options)
        cookie = client.cookies.get("hc_webauthn", path="/api/auth")
        await ok(
            client.post("/api/auth/passkeys", json={"label": "x", "credential": credential}), 201
        )
        client.cookies.set("hc_webauthn", cookie, path="/api/auth")
        response = await client.post(
            "/api/auth/passkeys", json={"label": "x", "credential": credential}
        )

        assert (response.status_code, response.json()["detail"]) == (400, "passkey_expired")

    async def test_the_same_passkey_cannot_be_added_twice(
        self, client, admin, authenticator
    ) -> None:
        await add_passkey(client, authenticator)
        # The same passkey offered again for a fresh challenge: genuine, but already on file.
        options = await ok(client.post("/api/auth/passkeys/options"))
        again = authenticator.register(options, credential=authenticator.credentials[0])
        response = await client.post("/api/auth/passkeys", json={"label": "b", "credential": again})

        assert (response.status_code, response.json()["detail"]) == (409, "passkey_exists")

    async def test_someone_elses_ceremony_cannot_be_finished(
        self, client, member, authenticator
    ) -> None:
        options = await ok(client.post("/api/auth/passkeys/options"))
        member.cookies.set(
            "hc_webauthn", client.cookies.get("hc_webauthn", path="/api/auth"), path="/api/auth"
        )
        response = await member.post(
            "/api/auth/passkeys", json={"label": "x", "credential": authenticator.register(options)}
        )
        assert (response.status_code, response.json()["detail"]) == (400, "passkey_expired")

    async def test_removed_only_by_its_owner(self, client, member, admin, authenticator) -> None:
        added = await add_passkey(client, authenticator)

        assert (await member.delete(f"/api/auth/passkeys/{added['id']}")).status_code == 404
        assert (await client.delete(f"/api/auth/passkeys/{added['id']}")).status_code == 204
        assert await ok(client.get("/api/auth/passkeys")) == []


class TestLoggingIn:
    async def test_a_passkey_logs_its_owner_in_and_records_its_use(
        self, client, admin, authenticator, new_client
    ) -> None:
        await add_passkey(client, authenticator)
        browser = new_client()
        response = await passkey_login(browser, authenticator)

        assert response.status_code == 200, response.text
        assert response.json()["login"] == "lucia"
        assert (await ok(browser.get("/api/auth/me")))["login"] == "lucia"
        used = (await ok(client.get("/api/auth/passkeys")))[0]
        assert used["last_used_at"] is not None

    async def test_the_login_options_name_nobody(self, client, admin, new_client) -> None:
        options = await ok(new_client().post("/api/auth/passkey-login/options"))
        assert options["rpId"] == "house-cost.test"
        assert options.get("allowCredentials", []) == []

    async def test_an_unknown_passkey_is_refused(
        self, client, admin, authenticator, new_client
    ) -> None:
        stranger = SoftAuthenticator(origin=ORIGIN)
        await add_passkey(client, authenticator)
        options = await ok(client.post("/api/auth/passkeys/options"))
        stranger.register(options)  # made, but never added to the account
        response = await passkey_login(new_client(), stranger)

        assert (response.status_code, response.json()["detail"]) == (401, "passkey_unknown")

    async def test_a_signature_from_another_origin_is_refused(
        self, client, admin, authenticator, new_client
    ) -> None:
        await add_passkey(client, authenticator)
        response = await passkey_login(new_client(), authenticator, origin="https://evil.test")

        assert (response.status_code, response.json()["detail"]) == (401, "passkey_rejected")

    async def test_a_cloned_key_betrayed_by_its_counter_is_refused(
        self, client, admin, authenticator, new_client
    ) -> None:
        await add_passkey(client, authenticator)
        assert (await passkey_login(new_client(), authenticator)).status_code == 200
        authenticator.credentials[0].sign_count = 0  # a copy that never saw the last login
        response = await passkey_login(new_client(), authenticator)

        assert (response.status_code, response.json()["detail"]) == (401, "passkey_rejected")

    async def test_a_deactivated_persons_passkey_is_refused(
        self, client, member, agreement, authenticator
    ) -> None:
        await add_passkey(member, authenticator)
        tiago = next(p for p in await ok(client.get("/api/people")) if p["login"] == "tiago")
        await ok(client.put(f"/api/people/{tiago['id']}", json={**tiago, "active": False}))
        response = await passkey_login(member, authenticator)

        assert (response.status_code, response.json()["detail"]) == (401, "passkey_unknown")

    async def test_an_answer_without_a_login_ceremony_is_refused(
        self, client, admin, authenticator, new_client
    ) -> None:
        await add_passkey(client, authenticator)
        options = await ok(client.post("/api/auth/passkeys/options"))  # a registration ceremony
        response = await client.post(
            "/api/auth/passkey-login",
            json={
                "credential": authenticator.authenticate(
                    {"rpId": "house-cost.test", "challenge": options["challenge"]}
                )
            },
        )
        assert (response.status_code, response.json()["detail"]) == (400, "passkey_expired")

    async def test_a_malformed_answer_is_refused(self, client, admin, new_client) -> None:
        browser = new_client()
        await ok(browser.post("/api/auth/passkey-login/options"))
        response = await browser.post("/api/auth/passkey-login", json={"credential": {"id": "x"}})

        assert (response.status_code, response.json()["detail"]) == (400, "passkey_rejected")

    async def test_failures_count_against_the_throttle(
        self, client, admin, settings, new_client
    ) -> None:
        browser = new_client()
        for _ in range(settings.login_attempts_per_minute):
            await ok(browser.post("/api/auth/passkey-login/options"))
            await browser.post("/api/auth/passkey-login", json={"credential": {"id": "x"}})
        response = await browser.post("/api/auth/passkey-login", json={"credential": {"id": "x"}})

        assert (response.status_code, response.json()["detail"]) == (429, "too_many_attempts")


class TestParty:
    def test_the_public_url_decides_where_passkeys_belong(self) -> None:
        assert party("https://costs.example.com/", "http", "127.0.0.1:18091") == party(
            "https://costs.example.com", "https", "anything"
        )
        assert (
            party("https://costs.example.com:8443", "http", "x").origin
            == "https://costs.example.com:8443"
        )
        assert party(None, "http", "localhost:5173").rp_id == "localhost"
        assert party(None, "http", "localhost:5173").origin == "http://localhost:5173"


class TestCeremonies:
    def test_a_ceremony_expires(self) -> None:
        now = [0.0]
        ceremonies = Ceremonies(clock=lambda: now[0])
        key = ceremonies.start(b"challenge", 1)
        now[0] += 301

        assert ceremonies.finish(key) is None
        assert ceremonies.finish(None) is None


async def test_a_passkey_presented_for_someone_else_is_refused(
    client, admin, authenticator, new_client
) -> None:
    await add_passkey(client, authenticator)
    authenticator.credentials[0].user_handle = b"another person's handle"
    response = await passkey_login(new_client(), authenticator)

    assert (response.status_code, response.json()["detail"]) == (401, "passkey_unknown")

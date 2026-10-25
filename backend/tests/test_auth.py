"""Passwords, the login throttle, sessions, and the origin check, without the HTTP layer."""

from datetime import timedelta

import pytest

from house_cost.auth import (
    SESSION_LIFETIME,
    SESSION_REFRESH,
    LoginThrottle,
    PasswordTooShort,
    find_session,
    hash_password,
    open_session,
    origin_allowed,
    verify_password,
)
from house_cost.db import session_scope
from house_cost.models import Household, Person, utcnow


class TestPasswords:
    def test_a_hash_verifies_its_password_and_no_other(self) -> None:
        hashed = hash_password("a long enough password")

        assert hashed.startswith("$argon2id$")
        assert verify_password(hashed, "a long enough password")
        assert not verify_password(hashed, "another long password")

    def test_a_short_password_is_refused(self) -> None:
        with pytest.raises(PasswordTooShort):
            hash_password("short")

    def test_a_malformed_hash_matches_nothing(self) -> None:
        assert not verify_password("not a hash", "whatever it is")


class TestThrottle:
    def test_blocks_after_the_limit_and_forgets_after_a_minute(self) -> None:
        now = [1000.0]
        throttle = LoginThrottle(3, clock=lambda: now[0])
        for _ in range(3):
            assert not throttle.blocked("1.2.3.4")
            throttle.failed("1.2.3.4")

        assert throttle.blocked("1.2.3.4")
        assert not throttle.blocked("5.6.7.8")
        now[0] += 60.5
        assert not throttle.blocked("1.2.3.4")

    def test_a_success_forgets_the_failures(self) -> None:
        throttle = LoginThrottle(2)
        throttle.failed("a")
        throttle.failed("a")
        throttle.succeeded("a")

        assert not throttle.blocked("a")


class TestOrigin:
    @pytest.mark.parametrize(
        ("origin", "host", "public_url", "allowed"),
        [
            (None, "x.test", None, True),
            ("https://x.test", "x.test", None, True),
            ("http://x.test", "x.test", None, True),
            ("https://evil.test", "x.test", None, False),
            ("null", "x.test", None, False),
            ("https://costs.example.com", "127.0.0.1:18091", "https://costs.example.com/", True),
            ("https://COSTS.example.com", "127.0.0.1:18091", "https://costs.example.com", True),
            ("https://evil.test", "127.0.0.1:18091", "https://costs.example.com", False),
            ("https://x.test", None, None, False),
        ],
    )
    def test_only_the_apps_own_origin_may_write(self, origin, host, public_url, allowed) -> None:
        assert origin_allowed(origin, host, public_url) is allowed


class TestSessions:
    @pytest.fixture
    async def person(self, app) -> tuple[object, Person]:
        factory = app.state.services.sessionmaker
        async with session_scope(factory) as db:
            household = Household(name="H")
            db.add(household)
            await db.flush()
            person = Person(
                name="P",
                login="p",
                password_hash=hash_password("long password!"),
                household_id=household.id,
            )
            db.add(person)
        return factory, person

    async def test_a_token_finds_its_session_until_it_expires(self, person) -> None:
        factory, someone = person
        async with session_scope(factory) as db:
            token = await open_session(db, someone, "Firefox")
        now = utcnow()
        async with session_scope(factory) as db:
            assert (await find_session(db, token, now)).person.login == "p"
            assert await find_session(db, "not-a-token", now) is None
            assert (
                await find_session(db, token, now + SESSION_LIFETIME + timedelta(seconds=1)) is None
            )

    async def test_using_a_session_extends_it_at_most_daily(self, person) -> None:
        factory, someone = person
        async with session_scope(factory) as db:
            token = await open_session(db, someone, "")
        start = utcnow()
        async with session_scope(factory) as db:
            session = await find_session(db, token, start + timedelta(hours=1))
            unchanged = session.expires_at
        async with session_scope(factory) as db:
            session = await find_session(db, token, start + SESSION_REFRESH + timedelta(minutes=1))
            extended = session.expires_at

        assert unchanged <= start + SESSION_LIFETIME + timedelta(seconds=5)
        assert extended > unchanged + timedelta(hours=23)

    async def test_a_deactivated_person_has_no_session(self, person) -> None:
        factory, someone = person
        async with session_scope(factory) as db:
            token = await open_session(db, someone, "")
            (await db.get(Person, someone.id)).active = False
        async with session_scope(factory) as db:
            assert await find_session(db, token) is None

"""Notifications: who gets which, in which language, sent once; and the scheduled work."""

import asyncio
import json
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import pytest
from helpers import PASSWORD, Agreement, bill, ok

from house_cost.config import Settings
from house_cost.db import session_scope
from house_cost.notify import AppriseSender, send_to
from house_cost.notify.events import bill_added, contract_reminders, missing_bills
from house_cost.notify.messages import (
    CATALOGUE,
    WORDS,
    day,
    days,
    every,
    language,
    money,
    price,
    render,
    within,
)
from house_cost.scheduler import Scheduler, back_up


class Recorder:
    """Records what would have been sent, instead of sending it."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[list[str], str, str]] = []
        self.fail = fail

    async def send(self, urls: list[str], title: str, body: str) -> bool:
        if self.fail:
            raise RuntimeError("delivery failed")
        self.sent.append((urls, title, body))
        return True


@pytest.fixture
def recorder(app) -> Recorder:
    recorder = Recorder()
    app.state.services.sender = recorder
    return recorder


async def _person(client, agreement: Agreement, login: str, household: int, **fields) -> dict:
    return await ok(
        client.post(
            "/api/people",
            json={
                "name": login.title(),
                "login": login,
                "household_id": household,
                "password": PASSWORD,
                **fields,
            },
        ),
        201,
    )


async def _notify_me(browser, urls: str, **notify_on) -> dict:
    me = await ok(browser.get("/api/auth/me"))
    body = {
        "name": me["name"],
        "language": me["language"],
        "apprise_urls": urls,
        "notify_on": notify_on,
    }
    return await ok(browser.patch("/api/auth/me", json=body))


class TestMessages:
    def test_every_message_has_both_languages_with_the_same_placeholders(self) -> None:
        import string

        def fields(text: str) -> set[str]:
            return {name for _, name, _, _ in string.Formatter().parse(text) if name}

        assert CATALOGUE["en"].keys() == CATALOGUE["pt-PT"].keys()
        assert WORDS["en"].keys() == WORDS["pt-PT"].keys()
        for key, (title, body) in CATALOGUE["en"].items():
            other_title, other_body = CATALOGUE["pt-PT"][key]
            assert fields(title) | fields(body) == fields(other_title) | fields(other_body), key

    def test_amounts_and_dates_as_each_language_writes_them(self) -> None:
        assert (money(123456, "en"), money(-501, "pt-PT")) == ("€1,234.56", "-5,01 €")
        assert (day(date(2026, 10, 23), "en"), day(date(2026, 7, 6), "pt-PT")) == (
            "23 Oct 2026",
            "06/07/2026",
        )
        assert (language("pt-PT"), language(None), language("de")) == ("pt-PT", "en", "en")
        assert render("test", "pt-PT")[0] == "Notificação de teste"
        assert (price(0.1499, "en"), price(0.2052, "pt-PT")) == ("€0.1499", "0,2052 €")
        assert [within(n, "en") for n in (0, 1, 7)] == ["today", "tomorrow", "in 7 days"]
        assert [within(n, "pt-PT") for n in (0, 1, 7)] == ["hoje", "amanhã", "dentro de 7 dias"]
        assert (days(1, "en"), days(30, "pt-PT"), days(1, "pt-PT")) == ("1 day", "30 dias", "1 dia")
        assert (every(1, "en"), every(1, "pt-PT"), every(30, "en")) == ("day", "dia", "30 days")


class TestAccount:
    async def test_a_person_sets_where_and_what_they_are_notified(self, client, admin) -> None:
        me = await _notify_me(client, " mailto://me@example.com \n", new_bill=False)

        assert me["apprise_urls"] == "mailto://me@example.com"
        assert me["notify_on"] == {
            "new_bill": False,
            "price_change": True,
            "contract": True,
            "missing_bill": True,
        }
        unchanged = await ok(client.patch("/api/auth/me", json={"name": "Graça"}))
        assert unchanged["apprise_urls"] == "mailto://me@example.com"

    async def test_others_do_not_see_a_persons_urls(self, client, member, admin) -> None:
        await _notify_me(client, "tgram://secret-token/123")
        assert "secret-token" not in (await member.get("/api/people")).text
        audit = await ok(member.get("/api/audit"))
        assert any(entry["entity"] == "person" for entry in audit["items"])
        assert "secret-token" not in str(audit)

    async def test_a_test_notification_goes_to_their_own_urls(
        self, client, admin, recorder
    ) -> None:
        refused = await client.post("/api/auth/me/test-notification")
        assert (refused.status_code, refused.json()["detail"]) == (422, "no_urls")

        await _notify_me(client, "json://example.test")
        assert await ok(client.post("/api/auth/me/test-notification")) == {"sent": True}
        assert recorder.sent == [
            (
                ["json://example.test"],
                "Test notification",
                "Notifications from House costs reach you here.",
            )
        ]


class TestNewBill:
    async def test_the_other_households_hear_of_it_in_their_language(
        self, client, agreement: Agreement, member, recorder, new_client
    ) -> None:
        await _notify_me(member, "json://jure.test")
        andreia = new_client()
        await _person(client, agreement, "andreia", agreement.owners, language="pt-PT")
        await ok(andreia.post("/api/auth/login", json={"login": "andreia", "password": PASSWORD}))
        await _notify_me(andreia, "json://andreia.test")
        quiet = new_client()
        await _person(client, agreement, "quiet", agreement.owners)
        await ok(quiet.post("/api/auth/login", json={"login": "quiet", "password": PASSWORD}))
        await _notify_me(quiet, "json://quiet.test", new_bill=False)
        await _notify_me(client, "json://graca.test")

        await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-05", agreement.graca, (agreement.road, 10000), supplier="Gravel Lda"
                ),
            ),
            201,
        )

        assert sorted(urls[0] for urls, _, _ in recorder.sent) == [
            "json://andreia.test",
            "json://jure.test",
        ]
        english = next(s for s in recorder.sent if s[0] == ["json://jure.test"])
        assert english[1:] == (
            "New bill: Gravel Lda, €100.00",
            "Graça added a bill from Gravel Lda dated 5 Oct 2026: €100.00, "
            "of which your household's share is €75.00.",
        )
        portuguese = next(s for s in recorder.sent if s[0] == ["json://andreia.test"])
        assert portuguese[1] == "Nova fatura: Gravel Lda, 100,00 €"
        assert "05/10/2026" in portuguese[2] and "75,00 €" in portuguese[2]

    async def test_a_failed_delivery_does_not_stop_the_others_or_the_bill(
        self, client, agreement, member, app
    ) -> None:
        app.state.services.sender = Recorder(fail=True)
        await _notify_me(member, "json://jure.test")
        created = await client.post(
            "/api/bills", json=bill("2026-10-05", agreement.graca, (agreement.road, 100))
        )

        assert created.status_code == 201

    async def test_a_bill_gone_by_the_time_of_sending_sends_nothing(self, app, recorder) -> None:
        await bill_added(app.state.services.sessionmaker, recorder, 999, 999)
        assert recorder.sent == []

    async def test_a_broken_database_is_logged_not_raised(self, recorder, caplog) -> None:
        class Broken:
            def __call__(self):
                raise RuntimeError("no database")

        await bill_added(Broken(), recorder, 1, 1)
        assert "notifying of bill 1 failed" in caplog.text


@pytest.fixture
async def electricity(client, agreement: Agreement) -> dict:
    supplier = await ok(client.post("/api/suppliers", json={"name": "MEO Energia"}), 201)
    return await ok(
        client.post(
            "/api/services",
            json={
                "supplier_id": supplier["id"],
                "name": "Electricity",
                "ends_on": "2026-12-18",
                "notice_days": 30,
                "lock_in_until": "2027-08-12",
                "billed_every_days": 30,
            },
        ),
        201,
    )


def _reading(unit_price: float | None) -> list[dict]:
    return [{"quantity": "electricity_kwh", "value": 100, "unit_price": unit_price}]


class TestPriceChange:
    async def test_a_new_unit_price_is_told_once(
        self, client, agreement, electricity, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test", new_bill=False)
        for on, unit_price in (
            ("2026-09-23", 0.2052),
            ("2026-10-23", 0.2052),
            ("2026-11-23", 0.1499),
            ("2026-11-24", None),
        ):
            await ok(
                client.post(
                    "/api/bills",
                    json=bill(
                        on,
                        agreement.owners,
                        (agreement.electricity, 100),
                        service_id=electricity["id"],
                        readings=_reading(unit_price),
                    ),
                ),
                201,
            )

        assert [(title, body) for _, title, body in recorder.sent] == [
            (
                "MEO Energia changed its price",
                "The electricity price on the bill of 23 Nov 2026 is €0.1499 per kWh, "
                "against €0.2052 on the bill before.",
            )
        ]

    async def test_the_same_bill_seen_twice_is_told_once(
        self, client, agreement, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test", new_bill=False)
        for on, unit_price in (("2026-09-23", 0.2052), ("2026-10-23", 0.1499)):
            created = await ok(
                client.post(
                    "/api/bills",
                    json=bill(
                        on,
                        agreement.owners,
                        (agreement.electricity, 100),
                        service_id=electricity["id"],
                        readings=_reading(unit_price),
                    ),
                ),
                201,
            )
        await bill_added(app.state.services.sessionmaker, recorder, created["id"], 1)

        assert len(recorder.sent) == 1

    async def test_bills_without_a_service_are_not_compared(
        self, client, agreement, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test", new_bill=False)
        for unit_price in (0.1, 0.2):
            await ok(
                client.post(
                    "/api/bills",
                    json=bill(
                        "2026-10-23",
                        agreement.owners,
                        (agreement.electricity, 1),
                        readings=_reading(unit_price),
                    ),
                ),
                201,
            )
        assert recorder.sent == []


class TestReminders:
    async def _run(self, app, recorder, today: date, kind) -> None:
        async with session_scope(app.state.services.sessionmaker) as db:
            await kind(db, recorder, today)

    async def test_a_contract_ending_is_reminded_30_and_7_days_ahead_once_each(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test")
        for today in (
            date(2026, 11, 17),
            date(2026, 11, 20),
            date(2026, 11, 30),
            date(2026, 12, 11),
            date(2026, 12, 12),
        ):
            await self._run(app, recorder, today, contract_reminders)

        titles = [title for _, title, _ in recorder.sent]
        assert titles == ["Electricity ends in 28 days", "Electricity ends in 7 days"]
        assert (
            recorder.sent[0][2] == "Electricity with MEO Energia renews on 18 Dec 2026. "
            "Leaving needs notice of 30 days."
        )

    async def test_a_service_first_seen_inside_a_week_gets_one_reminder(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test")
        await self._run(app, recorder, date(2027, 8, 9), contract_reminders)
        await self._run(app, recorder, date(2027, 8, 10), contract_reminders)

        assert [title for _, title, _ in recorder.sent] == ["Electricity: lock-in ends in 3 days"]

    async def test_the_last_days_reminder_in_portuguese(
        self, client, admin, electricity, app, recorder
    ) -> None:
        me = await ok(client.get("/api/auth/me"))
        body = {"name": me["name"], "language": "pt-PT", "apprise_urls": "json://graca.test"}
        await ok(client.patch("/api/auth/me", json=body))
        await ok(
            client.put(f"/api/services/{electricity['id']}", json={**electricity, "notice_days": 1})
        )
        await self._run(app, recorder, date(2026, 12, 18), contract_reminders)

        assert [sent[1:] for sent in recorder.sent] == [
            (
                "O contrato de Electricity termina hoje",
                "O contrato de Electricity com MEO Energia renova-se a 18/12/2026. Para rescindir, "
                "é preciso avisar com 1 dia de antecedência.",
            )
        ]

    async def test_a_contract_that_ends_without_notice_on_file(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test")
        await ok(
            client.put(
                f"/api/services/{electricity['id']}",
                json={
                    **electricity,
                    "notice_days": None,
                    "renews_automatically": False,
                    "lock_in_until": None,
                },
            )
        )
        await self._run(app, recorder, date(2026, 12, 1), contract_reminders)

        assert (
            recorder.sent[0][2] == "Electricity with MEO Energia ends on 18 Dec 2026. "
            "Leaving needs notice of an unknown number of days."
        )

    async def test_a_missing_bill_is_pointed_out_once_per_gap(
        self, client, agreement, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test", new_bill=False)
        await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-23",
                    agreement.owners,
                    (agreement.electricity, 1),
                    service_id=electricity["id"],
                ),
            ),
            201,
        )
        # Due on 22 Nov, every 30 days; pointed out once the 7 days' grace after it has passed.
        await self._run(app, recorder, date(2026, 11, 29), missing_bills)
        assert recorder.sent == []
        for today in (date(2026, 11, 30), date(2026, 12, 1)):
            await self._run(app, recorder, today, missing_bills)

        assert [(title, body) for _, title, body in recorder.sent] == [
            (
                "No bill from MEO Energia yet",
                "The last bill for Electricity was dated 23 Oct 2026, "
                "and one usually comes every 30 days.",
            )
        ]


async def _backups(settings: Settings) -> list[str]:
    return sorted(path.name for path in settings.backups_dir.glob("*.db"))


class TestScheduler:
    def _scheduler(self, app, recorder, **overrides) -> Scheduler:
        services = app.state.services
        settings = services.settings.model_copy(update=overrides)
        return Scheduler(settings, services.engine, services.sessionmaker, recorder)

    async def test_the_days_backup_waits_for_its_time_and_is_taken_once(
        self, client, admin, app, recorder
    ) -> None:
        scheduler = self._scheduler(app, recorder, backup_time="03:30")
        lisbon = ZoneInfo("Europe/Lisbon")
        await scheduler.tick(datetime(2026, 10, 26, 3, 0, tzinfo=lisbon))
        assert await _backups(scheduler.settings) == []

        await scheduler.tick(datetime(2026, 10, 26, 3, 31, tzinfo=lisbon))
        await scheduler.tick(datetime(2026, 10, 26, 9, 0, tzinfo=lisbon))
        assert await _backups(scheduler.settings) == ["house-cost-2026-10-26.db"]

        import sqlite3

        copy = sqlite3.connect(scheduler.settings.backups_dir / "house-cost-2026-10-26.db")
        try:
            assert copy.execute("SELECT login FROM person").fetchall() == [("graca",)]
        finally:
            copy.close()

    async def test_only_the_newest_backups_are_kept(self, app, recorder) -> None:
        settings = app.state.services.settings
        for day_number in range(1, 5):
            await back_up(
                app.state.services.engine, settings.backups_dir, f"2026-10-0{day_number}", 2
            )

        assert await _backups(settings) == ["house-cost-2026-10-03.db", "house-cost-2026-10-04.db"]

    async def test_reminders_run_once_a_day(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "json://graca.test")
        scheduler = self._scheduler(app, recorder, backup_time="23:59")
        utc = ZoneInfo("UTC")
        await scheduler.tick(datetime(2026, 11, 20, 8, 0, tzinfo=utc))
        await scheduler.tick(datetime(2026, 11, 20, 9, 0, tzinfo=utc))

        assert len(recorder.sent) == 1

    async def test_the_loop_runs_until_stopped_and_survives_a_failing_tick(
        self, app, recorder, caplog
    ) -> None:
        scheduler = self._scheduler(
            app, recorder, scheduler_enabled=True, scheduler_tick_seconds=0.01
        )
        ticks = []

        async def tick(now=None):
            ticks.append(now)
            raise RuntimeError("boom")

        scheduler.tick = tick
        scheduler.start()
        scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()
        await scheduler.stop()

        assert len(ticks) >= 2
        assert "scheduled work failed" in caplog.text

    async def test_a_disabled_scheduler_does_not_start(self, app, recorder) -> None:
        scheduler = self._scheduler(app, recorder)
        scheduler.start()
        assert scheduler._task is None

    async def test_the_real_clock_is_where_the_house_is(self, app, recorder) -> None:
        scheduler = self._scheduler(app, recorder, timezone="Europe/Lisbon", backup_time="23:59")
        await scheduler.tick()
        assert scheduler._last_reminded is not None


class TestAppriseSender:
    def test_delivers_to_a_url_and_skips_one_it_cannot_read(self, caplog) -> None:
        received: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - the name http.server dispatches to
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            sent = asyncio.run(
                AppriseSender().send(
                    [f"json://127.0.0.1:{server.server_port}", "not a url"], "Title", "Body"
                )
            )
        finally:
            server.shutdown()
            server.server_close()

        assert sent is True
        assert (received[0]["title"], received[0]["message"]) == ("Title", "Body")
        assert "not recognised" in caplog.text and "not a url" not in caplog.text

    def test_nothing_it_can_read_sends_nothing(self) -> None:
        assert asyncio.run(AppriseSender().send(["not a url"], "T", "B")) is False


async def test_send_to_skips_those_who_do_not_want_it(app) -> None:
    from house_cost.models import Person

    people = [
        Person(name="A", apprise_urls="json://a", notify_on={}, active=True, language=None),
        Person(name="B", apprise_urls="", notify_on={}, active=True, language=None),
        Person(
            name="C",
            apprise_urls="json://c",
            notify_on={"contract": False},
            active=True,
            language=None,
        ),
        Person(name="D", apprise_urls="json://d", notify_on={}, active=False, language=None),
    ]
    recorder = Recorder()

    assert await send_to(recorder, people, "contract", "test", lambda _p, _l: {}) == 1
    assert [urls for urls, _, _ in recorder.sent] == [["json://a"]]

    class Undelivered(Recorder):
        async def send(self, urls: list[str], title: str, body: str) -> bool:
            await super().send(urls, title, body)
            return False

    assert await send_to(Undelivered(), people, "contract", "test", lambda _p, _l: {}) == 0

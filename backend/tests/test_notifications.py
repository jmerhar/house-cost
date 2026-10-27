"""Notifications: who gets which, in which language, sent once; and the scheduled work."""

import asyncio
import json
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import pytest
from conftest import MAIL_URL, SIGNAL_URL
from helpers import PASSWORD, Agreement, bill, ok
from sqlalchemy import select

from house_cost.config import Settings
from house_cost.db import session_scope
from house_cost.models import SentNotification
from house_cost.notify import AppriseSender, Notifier, with_recipient, with_target
from house_cost.notify.events import bill_added, contract_reminders, missing_bills
from house_cost.notify.messages import (
    CATALOGUE,
    WORDS,
    day,
    days,
    every,
    language,
    money,
    notice,
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
    app.state.services.notifier.sender = recorder
    return recorder


def mail(name: str) -> str:
    """The Apprise URL a person whose address is ``name``@example.com is mailed at."""
    return f"{MAIL_URL}&to={name}@example.com"


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


async def _notify_me(browser, email: str = "", phone: str = "", **notify_on) -> dict:
    me = await ok(browser.get("/api/auth/me"))
    body = {
        "name": me["name"],
        "language": me["language"],
        "email": email,
        "phone": phone,
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
        assert (day(date(2026, 10, 18), "en"), day(date(2026, 7, 6), "pt-PT")) == (
            "18 Oct 2026",
            "06/07/2026",
        )
        assert (language("pt-PT"), language(None), language("de")) == ("pt-PT", "en", "en")
        assert render("test", "pt-PT")[0] == "Notificação de teste"
        assert (price(0.1525, "en"), price(0.2052, "pt-PT")) == ("€0.1525", "0,2052 €")
        assert [within(n, "en") for n in (0, 1, 7)] == ["today", "tomorrow", "in 7 days"]
        assert [within(n, "pt-PT") for n in (0, 1, 7)] == ["hoje", "amanhã", "daqui a 7 dias"]
        assert (days(1, "en"), days(30, "pt-PT"), days(1, "pt-PT")) == ("1 day", "30 dias", "1 dia")
        assert (every(1, "en"), every(1, "pt-PT"), every(30, "en")) == (
            "every day",
            "por dia",
            "every 30 days",
        )
        assert (notice(30, "en"), notice(None, "pt-PT")) == (
            "You must give notice of 30 days to leave.",
            "Confirme no contrato o pré-aviso necessário para o cancelar.",
        )


class TestAccount:
    async def test_a_person_gives_an_address_a_number_and_what_to_hear_of(
        self, client, admin
    ) -> None:
        me = await _notify_me(client, " lucia@example.com ", "912 345 678", new_bill=False)

        assert (me["email"], me["phone"]) == ("lucia@example.com", "+351912345678")
        assert (me["notify_channels"], me["phone_country_code"]) == (["email", "signal"], "351")
        assert me["notify_on"] == {
            "new_bill": False,
            "price_change": True,
            "contract": True,
            "missing_bill": True,
        }
        unchanged = await ok(client.patch("/api/auth/me", json={"name": "Lúcia"}))
        assert (unchanged["email"], unchanged["phone"]) == ("lucia@example.com", "+351912345678")

    @pytest.mark.parametrize(
        ("field", "value", "code"),
        [("email", "not an address", "invalid_email"), ("phone", "12", "invalid_phone")],
    )
    async def test_what_cannot_be_an_address_or_a_number_is_refused(
        self, client, admin, field, value, code
    ) -> None:
        refused = await client.patch("/api/auth/me", json={"name": "Lúcia", field: value})
        assert (refused.status_code, refused.json()["detail"]) == (422, code)

    async def test_only_admins_and_the_person_see_their_contacts(
        self, client, member, admin
    ) -> None:
        await _notify_me(client, "lucia@example.com", "+351 912 345 678")
        await _notify_me(member, "tiago@example.com")

        as_member = {p["login"]: p for p in await ok(member.get("/api/people"))}
        assert (as_member["lucia"]["email"], as_member["lucia"]["phone"]) == (None, None)
        assert as_member["tiago"]["email"] == "tiago@example.com"
        as_admin = {p["login"]: p for p in await ok(client.get("/api/people"))}
        assert as_admin["tiago"]["email"] == "tiago@example.com"
        audit = await ok(member.get("/api/audit"))
        people = [entry for entry in audit["items"] if entry["entity"] == "person"]
        assert people
        for entry in people:
            for record in (entry["before"], entry["after"]):
                assert not {"email", "phone"} & set(record or {})
        # The stored forms, which no timestamp or id in the log can contain by chance.
        assert "@example.com" not in str(audit) and "+351912345678" not in str(audit)

    async def test_an_admin_sets_someones_contacts(self, client, agreement, member) -> None:
        marta = await _person(
            client,
            agreement,
            "marta",
            agreement.owners,
            email="a@example.com",
            phone="0044 20 7946 0000",
        )
        assert (marta["email"], marta["phone"]) == ("a@example.com", "+442079460000")

        people = {p["login"]: p for p in await ok(client.get("/api/people"))}
        tiago = people["tiago"]
        update = {
            k: tiago[k] for k in ("name", "login", "role", "language", "household_id", "active")
        }
        changed = await ok(
            client.put(f"/api/people/{tiago['id']}", json={**update, "phone": "910000000"})
        )
        kept = await ok(client.put(f"/api/people/{tiago['id']}", json=update))
        refused = await client.put(f"/api/people/{tiago['id']}", json={**update, "email": "x@"})

        assert changed["phone"] == kept["phone"] == "+351910000000"
        assert (refused.status_code, refused.json()["detail"]) == (422, "invalid_email")

    async def test_a_test_notification_goes_to_every_contact(self, client, admin, recorder) -> None:
        refused = await client.post("/api/auth/me/test-notification")
        assert (refused.status_code, refused.json()["detail"]) == (422, "no_contact")

        await _notify_me(client, "lucia@example.com", "912345678")
        assert await ok(client.post("/api/auth/me/test-notification")) == {"sent": True}
        assert recorder.sent == [
            (
                [mail("lucia"), f"{SIGNAL_URL}/+351912345678"],
                "Test notification",
                "Notifications from House costs reach you here.",
            )
        ]


class TestNewBill:
    async def test_the_other_households_hear_of_it_in_their_language(
        self, client, agreement: Agreement, member, recorder, new_client
    ) -> None:
        await _notify_me(member, "tiago@example.com")
        marta = new_client()
        await _person(client, agreement, "marta", agreement.owners, language="pt-PT")
        await ok(marta.post("/api/auth/login", json={"login": "marta", "password": PASSWORD}))
        await _notify_me(marta, "marta@example.com")
        quiet = new_client()
        await _person(client, agreement, "quiet", agreement.owners)
        await ok(quiet.post("/api/auth/login", json={"login": "quiet", "password": PASSWORD}))
        await _notify_me(quiet, "quiet@example.com", new_bill=False)
        await _notify_me(client, "lucia@example.com")

        await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-05", agreement.lucia, (agreement.road, 10000), supplier="Gravel Lda"
                ),
            ),
            201,
        )

        assert sorted(urls[0] for urls, _, _ in recorder.sent) == [
            mail("marta"),
            mail("tiago"),
        ]
        english = next(s for s in recorder.sent if s[0] == [mail("tiago")])
        assert english[1:] == (
            "New bill: Gravel Lda, €100.00",
            "Lúcia added a bill from Gravel Lda dated 5 Oct 2026: €100.00, "
            "of which your household's share is €60.00.",
        )
        portuguese = next(s for s in recorder.sent if s[0] == [mail("marta")])
        assert portuguese[1] == "Nova fatura: Gravel Lda, 100,00 €"
        assert "05/10/2026" in portuguese[2] and "60,00 €" in portuguese[2]

    async def test_a_failed_delivery_does_not_stop_the_others_or_the_bill(
        self, client, agreement, member, app
    ) -> None:
        app.state.services.notifier.sender = Recorder(fail=True)
        await _notify_me(member, "tiago@example.com")
        created = await client.post(
            "/api/bills", json=bill("2026-10-05", agreement.lucia, (agreement.road, 100))
        )

        assert created.status_code == 201

    async def test_a_bill_gone_by_the_time_of_sending_sends_nothing(self, app, recorder) -> None:
        await bill_added(app.state.services.sessionmaker, app.state.services.notifier, 999, 999)
        assert recorder.sent == []

    async def test_a_broken_database_is_logged_not_raised(self, recorder, caplog) -> None:
        class Broken:
            def __call__(self):
                raise RuntimeError("no database")

        await bill_added(Broken(), Notifier(recorder), 1, 1)
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
                "ends_on": "2026-12-11",
                "notice_days": 30,
                "lock_in_until": "2027-07-28",
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
        await _notify_me(client, "lucia@example.com", new_bill=False)
        for on, unit_price in (
            ("2026-09-21", 0.2052),
            ("2026-10-18", 0.2052),
            ("2026-11-23", 0.1525),
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
                "The electricity price on the bill of 23 Nov 2026 is €0.1525 per kWh, "
                "compared with €0.2052 on the bill before.",
            )
        ]

    async def test_the_same_bill_seen_twice_is_told_once(
        self, client, agreement, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com", new_bill=False)
        for on, unit_price in (("2026-09-21", 0.2052), ("2026-10-18", 0.1525)):
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
        await bill_added(
            app.state.services.sessionmaker, app.state.services.notifier, created["id"], 1
        )

        assert len(recorder.sent) == 1

    async def test_bills_without_a_service_are_not_compared(
        self, client, agreement, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com", new_bill=False)
        for unit_price in (0.1, 0.2):
            await ok(
                client.post(
                    "/api/bills",
                    json=bill(
                        "2026-10-18",
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
            await kind(db, app.state.services.notifier, today)

    async def test_a_contract_ending_is_reminded_30_and_7_days_ahead_once_each(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com")
        for today in (
            date(2026, 11, 10),
            date(2026, 11, 13),
            date(2026, 11, 23),
            date(2026, 12, 4),
            date(2026, 12, 5),
        ):
            await self._run(app, recorder, today, contract_reminders)

        titles = [title for _, title, _ in recorder.sent]
        assert titles == ["Electricity renews in 28 days", "Electricity renews in 7 days"]
        assert (
            recorder.sent[0][2] == "Electricity with MEO Energia renews on 11 Dec 2026. "
            "You must give notice of 30 days to leave."
        )

    async def test_a_deleted_services_reminders_go_with_it(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com")
        await self._run(app, recorder, date(2026, 12, 4), contract_reminders)
        await ok(client.delete(f"/api/services/{electricity['id']}"), 204)
        # The same contract added again; SQLite gives it the id that was freed.
        again = await ok(client.post("/api/services", json=electricity), 201)
        assert again["id"] == electricity["id"]
        await self._run(app, recorder, date(2026, 12, 4), contract_reminders)

        assert [title for _, title, _ in recorder.sent] == [
            "Electricity renews in 7 days",
            "Electricity renews in 7 days",
        ]
        async with session_scope(app.state.services.sessionmaker) as db:
            keys = (await db.execute(select(SentNotification.key))).scalars().all()
        assert sorted(keys) == [
            f"contract_ends:{again['id']}:2026-12-11:30",
            f"contract_ends:{again['id']}:2026-12-11:7",
        ]

    async def test_a_service_first_seen_inside_a_week_gets_one_reminder(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com")
        await self._run(app, recorder, date(2027, 7, 25), contract_reminders)
        await self._run(app, recorder, date(2027, 7, 26), contract_reminders)

        assert [title for _, title, _ in recorder.sent] == [
            "Electricity: minimum term ends in 3 days"
        ]

    async def test_the_last_days_reminder_in_portuguese(
        self, client, admin, electricity, app, recorder
    ) -> None:
        me = await ok(client.get("/api/auth/me"))
        body = {"name": me["name"], "language": "pt-PT", "email": "lucia@example.com"}
        await ok(client.patch("/api/auth/me", json=body))
        await ok(
            client.put(f"/api/services/{electricity['id']}", json={**electricity, "notice_days": 1})
        )
        await self._run(app, recorder, date(2026, 12, 11), contract_reminders)

        assert [sent[1:] for sent in recorder.sent] == [
            (
                "O contrato de Electricity renova-se hoje",
                "O contrato de Electricity com MEO Energia renova-se a 11/12/2026. Para rescindir, "
                "é preciso avisar com 1 dia de antecedência.",
            )
        ]

    async def test_a_contract_that_ends_without_notice_on_file(
        self, client, admin, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com")
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
            recorder.sent[0][2] == "Electricity with MEO Energia ends on 11 Dec 2026. "
            "Check the contract for the notice needed to leave."
        )

    async def test_a_missing_bill_is_pointed_out_once_per_gap(
        self, client, agreement, electricity, app, recorder
    ) -> None:
        await _notify_me(client, "lucia@example.com", new_bill=False)
        await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 1),
                    service_id=electricity["id"],
                ),
            ),
            201,
        )
        # Due on 17 Nov, every 30 days; pointed out once the 7 days' grace after it has passed.
        await self._run(app, recorder, date(2026, 11, 24), missing_bills)
        assert recorder.sent == []
        for today in (date(2026, 11, 25), date(2026, 11, 26)):
            await self._run(app, recorder, today, missing_bills)

        assert [(title, body) for _, title, body in recorder.sent] == [
            (
                "No bill from MEO Energia yet",
                "The last bill for Electricity was dated 18 Oct 2026, "
                "and one usually comes every 30 days.",
            )
        ]


async def _backups(settings: Settings) -> list[str]:
    return sorted(path.name for path in settings.backups_dir.glob("*.db"))


class TestScheduler:
    def _scheduler(self, app, recorder, **overrides) -> Scheduler:
        services = app.state.services
        settings = services.settings.model_copy(update=overrides)
        return Scheduler(settings, services.engine, services.sessionmaker, services.notifier)

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
            assert copy.execute("SELECT login FROM person").fetchall() == [("lucia",)]
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
        await _notify_me(client, "lucia@example.com")
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


class TestNotifier:
    async def test_sends_only_to_those_who_want_it_and_can_get_it(self) -> None:
        from house_cost.models import Person

        def person(name: str, **fields) -> Person:
            values = {"email": "", "phone": "", "notify_on": {}, "active": True, "language": None}
            return Person(name=name, **(values | fields))

        people = [
            person("A", email="a@example.com"),
            person("B"),
            person("C", email="c@example.com", notify_on={"contract": False}),
            person("D", email="d@example.com", active=False),
            person("E", phone="+351910000000"),
        ]
        recorder = Recorder()
        email_only = Notifier(recorder, email_url=MAIL_URL)

        assert await email_only.send_to(people, "contract", "test", lambda _p, _l: {}) == 1
        assert [urls for urls, _, _ in recorder.sent] == [[mail("a")]]
        assert email_only.channels == ["email"]

        class Undelivered(Recorder):
            async def send(self, urls: list[str], title: str, body: str) -> bool:
                await super().send(urls, title, body)
                return False

        assert (
            await Notifier(Undelivered(), MAIL_URL).send_to(
                people, "contract", "test", lambda _p, _l: {}
            )
            == 0
        )
        assert Notifier(recorder).channels == []

    def test_urls_are_addressed_to_the_person(self) -> None:
        assert with_recipient("mailto://host:25", "a+b@example.com") == (
            "mailto://host:25?to=a+b@example.com"
        )
        assert with_target("signal://signal:8080/+351210000000/?batch=no", "+351910000000") == (
            "signal://signal:8080/+351210000000/+351910000000?batch=no"
        )

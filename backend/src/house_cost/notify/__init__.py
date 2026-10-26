"""Notifications: sent through Apprise to each person who wants them, in their own language.

People give an email address and a phone number; the deployment configures how each kind is
sent (``NOTIFY_EMAIL_URL``, ``NOTIFY_SIGNAL_URL``), and the two make a person's Apprise URLs.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Person, SentNotification
from .messages import language, render

logger = logging.getLogger(__name__)

#: The kinds of notification a person can turn off, by the name their preferences use.
EVENTS = ("new_bill", "price_change", "contract", "missing_bill")


class Sender(Protocol):
    """Delivers one message to a set of Apprise URLs; returns whether any delivery succeeded."""

    async def send(self, urls: list[str], title: str, body: str) -> bool: ...


class AppriseSender:
    """Delivers through the Apprise library, off the event loop since Apprise blocks."""

    async def send(self, urls: list[str], title: str, body: str) -> bool:
        return await asyncio.to_thread(self._send, urls, title, body)

    @staticmethod
    def _send(urls: list[str], title: str, body: str) -> bool:
        import apprise

        notifier = apprise.Apprise()
        for url in urls:
            if not notifier.add(url):
                # Logged without the URL, which can carry a password or a token.
                logger.warning("an Apprise URL was not recognised and is skipped")
        if not len(notifier):
            return False
        return bool(notifier.notify(body=body, title=title))


def with_recipient(url: str, email: str) -> str:
    """The deployment's mail URL addressed to ``email``, as Apprise's ``to`` argument."""
    parts = urlsplit(url)
    to = "to=" + quote(email, safe="@+.")
    query = f"{parts.query}&{to}" if parts.query else to
    return urlunsplit(parts._replace(query=query))


def with_target(url: str, phone: str) -> str:
    """The deployment's Signal URL sending to ``phone``, the last part of its path."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=parts.path.rstrip("/") + "/" + phone))


@dataclass
class Notifier:
    """Delivery (``sender``) and the channels the deployment offers, by their base URLs."""

    sender: Sender
    email_url: str | None = None
    signal_url: str | None = None

    @property
    def channels(self) -> list[str]:
        """The kinds of contact people can give: "email", "signal", or neither."""
        offered = (("email", self.email_url), ("signal", self.signal_url))
        return [name for name, url in offered if url]

    def destinations(self, person: Person) -> list[str]:
        """Where ``person``'s notifications go: an Apprise URL per contact a channel can use."""
        urls = []
        if self.email_url and person.email:
            urls.append(with_recipient(self.email_url, person.email))
        if self.signal_url and person.phone:
            urls.append(with_target(self.signal_url, person.phone))
        return urls

    async def send_to(
        self,
        people: Iterable[Person],
        event: str,
        message: str,
        values: Callable[[Person, str], dict[str, object]],
    ) -> int:
        """Send ``message`` to each person who wants ``event`` and has somewhere to get it,
        filled in for them and in their language by ``values(person, lang)``. Returns how many
        were sent."""
        sent = 0
        for person in people:
            urls = self.destinations(person)
            if not urls or not person.wants(event):
                continue
            lang = language(person.language)
            title, body = render(message, lang, **values(person, lang))
            try:
                if await self.sender.send(urls, title, body):
                    sent += 1
            except Exception:  # noqa: BLE001 - one failed delivery must not stop the others
                logger.exception("a notification could not be sent")
        return sent


async def once(db: AsyncSession, key: str) -> bool:
    """Whether the notification ``key`` names is still to be sent; marks it sent if so."""
    if await db.get(SentNotification, key) is not None:
        return False
    db.add(SentNotification(key=key))
    await db.flush()
    return True

"""Notifications: sent through Apprise to each person who wants them, in their own language."""

import asyncio
import logging
from collections.abc import Callable, Iterable
from typing import Protocol

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


async def send_to(
    sender: Sender,
    people: Iterable[Person],
    event: str,
    message: str,
    values: Callable[[Person, str], dict[str, object]],
) -> int:
    """Send ``message`` to each person who wants ``event``, filled in for them and in their
    language by ``values(person, lang)``. Returns how many were sent."""
    sent = 0
    for person in people:
        if not person.wants(event):
            continue
        lang = language(person.language)
        title, body = render(message, lang, **values(person, lang))
        try:
            if await sender.send(person.urls, title, body):
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

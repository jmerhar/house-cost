"""Run the application with uvicorn, through jigkit: ``python -m house_cost [--reload]``.

jigkit's ``serve`` keeps the logging configured here instead of uvicorn's own handlers, and
believes X-Forwarded-For and X-Forwarded-Proto only from ``FORWARDED_ALLOW_IPS``: they decide
the client address the login throttle counts and the session cookie's Secure flag.
"""

import sys

from jigkit.logging import configure_logging
from jigkit.web import serve

from .config import get_settings


def main(argv: list[str] | None = None) -> None:
    """Serve the application, reloading on source changes when asked to."""
    settings = get_settings()
    configure_logging(settings.log_level)
    reload = "--reload" in (argv if argv is not None else sys.argv[1:])
    serve("house_cost.api.app:create_app", settings, reload=reload)


if __name__ == "__main__":
    main()

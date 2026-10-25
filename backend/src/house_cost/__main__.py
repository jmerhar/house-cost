"""Run the application with uvicorn: ``python -m house_cost [--reload]``."""

import logging
import sys

import uvicorn

from .config import get_settings

# Inside the container; the compose file decides what the host publishes.
HOST = "0.0.0.0"  # noqa: S104
PORT = 8000


def main(argv: list[str] | None = None) -> None:
    """Serve the application, reloading on source changes when asked to."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    reload = "--reload" in (argv if argv is not None else sys.argv[1:])
    if reload:
        # A reloading worker is a fresh process, so it is given an import string to build from.
        uvicorn.run(
            "house_cost.api.app:create_app", factory=True, reload=True, host=HOST, port=PORT
        )
        return
    from .api.app import create_app

    # log_config=None keeps the logging configured above instead of uvicorn's own handlers.
    uvicorn.run(create_app(settings), host=HOST, port=PORT, log_config=None)


if __name__ == "__main__":
    main()

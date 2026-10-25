"""The application: its health endpoint and how it serves the built single-page app."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from house_cost import __version__
from house_cost.api.app import IMMUTABLE, create_app
from house_cost.config import Settings


async def test_health_reports_the_database_and_version(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected", "version": __version__}


async def test_without_a_built_frontend_only_the_api_answers(client: httpx.AsyncClient) -> None:
    assert (await client.get("/")).status_code == 404


@pytest.fixture
def web(data_dir: Path) -> Path:
    """A built frontend: the shell, a hashed asset, a public file, and a secret next door."""
    root = data_dir / "web"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>shell</title>")
    (root / "assets" / "index-abc123.js").write_text("console.log('app')")
    (root / "favicon.svg").write_text("<svg/>")
    (data_dir / "secret.txt").write_text("not for the web")
    return root


@pytest.fixture
async def web_client(data_dir: Path, web: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(data_dir=data_dir, static_dir=web))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://house-cost.test") as c:
            yield c


class TestServingTheFrontend:
    async def test_the_root_is_the_shell_and_is_revalidated(
        self, web_client: httpx.AsyncClient
    ) -> None:
        response = await web_client.get("/")

        assert response.status_code == 200
        assert "<title>shell</title>" in response.text
        assert response.headers["cache-control"] == "no-cache"

    async def test_a_client_side_route_gets_the_shell(self, web_client: httpx.AsyncClient) -> None:
        response = await web_client.get("/bills/42")

        assert response.status_code == 200
        assert "<title>shell</title>" in response.text

    async def test_a_file_of_the_build_is_served_as_itself(
        self, web_client: httpx.AsyncClient
    ) -> None:
        response = await web_client.get("/favicon.svg")

        assert response.text == "<svg/>"

    async def test_hashed_assets_are_cached_for_good(self, web_client: httpx.AsyncClient) -> None:
        response = await web_client.get("/assets/index-abc123.js")

        assert response.status_code == 200
        assert response.headers["cache-control"] == IMMUTABLE

    async def test_a_missing_asset_is_not_marked_cacheable(
        self, web_client: httpx.AsyncClient
    ) -> None:
        response = await web_client.get("/assets/gone.js")

        assert response.status_code == 404
        assert response.headers.get("cache-control") != IMMUTABLE

    @pytest.mark.parametrize("path", ["/api", "/api/nothing-here", "/api/health/extra"])
    async def test_an_unknown_api_path_is_a_404_not_the_shell(
        self, web_client: httpx.AsyncClient, path: str
    ) -> None:
        response = await web_client.get(path)

        assert response.status_code == 404
        assert "shell" not in response.text

    async def test_the_api_still_answers_beside_the_frontend(
        self, web_client: httpx.AsyncClient
    ) -> None:
        assert (await web_client.get("/api/health")).json()["status"] == "ok"

    # Percent-encoded, because a client normalises a literal ../ away before it is ever sent.
    @pytest.mark.parametrize("path", ["/%2e%2e/secret.txt", "/..%2fsecret.txt"])
    async def test_nothing_outside_the_build_is_served(
        self, web_client: httpx.AsyncClient, path: str
    ) -> None:
        response = await web_client.get(path)

        assert "not for the web" not in response.text


async def test_a_build_without_assets_still_serves_its_shell(data_dir: Path) -> None:
    web = data_dir / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>shell</title>")
    app = create_app(Settings(data_dir=data_dir, static_dir=web))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert "shell" in (await client.get("/")).text

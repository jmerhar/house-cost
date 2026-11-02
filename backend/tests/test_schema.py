"""The app the OpenAPI export builds."""

from house_cost.api.schema import build_app


def test_builds_the_app_in_the_directory_given(tmp_path):
    schema = build_app(tmp_path).openapi()
    assert "/api/health" in schema["paths"]

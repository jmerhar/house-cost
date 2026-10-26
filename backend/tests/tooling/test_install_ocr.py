"""bin/install-ocr.sh: Tesseract installed through a package cache CI keeps between runs."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[3] / "bin" / "install-ocr.sh"


def _stub(directory: Path) -> Path:
    """An apt-get that records its arguments, one call per line, instead of running."""
    log = directory / "calls.log"
    stub = directory / "apt-get"
    stub.write_text(f'#!/bin/sh\necho "$*" >> {log}\n')
    stub.chmod(0o755)
    return log


def test_installs_through_the_cache(tmp_path: Path) -> None:
    log = _stub(tmp_path)
    cache = tmp_path / "cache"
    env = {**os.environ, "SUDO": "", "APT_GET": str(tmp_path / "apt-get")}
    subprocess.run([str(SCRIPT), str(cache)], env=env, check=True, capture_output=True)

    update, install = log.read_text().splitlines()
    assert update == "update -qq"
    assert install == (
        f"install -y --no-install-recommends -o Dir::Cache::Archives={cache} "
        "tesseract-ocr tesseract-ocr-por tesseract-ocr-eng"
    )
    # apt refuses a cache without its partial/ directory.
    assert (cache / "partial").is_dir()


def test_a_cache_directory_is_required(tmp_path: Path) -> None:
    result = subprocess.run([str(SCRIPT)], capture_output=True, text=True)

    assert result.returncode != 0
    assert "usage: bin/install-ocr.sh CACHE_DIR" in result.stderr

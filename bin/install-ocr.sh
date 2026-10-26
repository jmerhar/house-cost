#!/usr/bin/env bash
# Install Tesseract with Portuguese and English, for the tests that read scanned bills, keeping the
# downloaded packages in CACHE_DIR: with them there, nothing is downloaded.
#
# Usage: bin/install-ocr.sh CACHE_DIR
# CI keeps CACHE_DIR between runs (actions/cache), because Ubuntu's mirror can take minutes for
# these 9 MB. Environment: SUDO and APT_GET name the commands run; SUDO may be empty.
set -euo pipefail

cache="${1:?usage: bin/install-ocr.sh CACHE_DIR}"
sudo="${SUDO-sudo}"
apt_get="${APT_GET:-apt-get}"

as_root() {
  if [ -n "$sudo" ]; then "$sudo" "$@"; else "$@"; fi
}

mkdir -p "$cache/partial"
as_root "$apt_get" update -qq
as_root "$apt_get" install -y --no-install-recommends -o "Dir::Cache::Archives=$cache" \
  tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
# apt leaves its downloads owned by root, and the cache is saved as the runner's user.
as_root chown -R "$(id -u):$(id -g)" "$cache"

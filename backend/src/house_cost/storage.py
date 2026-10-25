"""Uploaded files, kept in the data directory under their SHA-256, and what kind they are."""

import hashlib
import os
import tempfile
from pathlib import Path

#: The kinds of file accepted, by the bytes they start with. Recognised from the content rather
#: than trusted from the upload's declared type, which the uploader chooses.
SIGNATURES: list[tuple[bytes, int, str]] = [
    (b"%PDF-", 0, "application/pdf"),
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"WEBP", 8, "image/webp"),
]
#: An ISO media file's brands that are HEIC/HEIF photos, as an iPhone takes them.
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}


class TooLarge(ValueError):
    """The upload is larger than the configured limit."""


def sniff(head: bytes) -> str | None:
    """The content type of a file starting with ``head``, or None if it is not one accepted."""
    for signature, offset, content_type in SIGNATURES:
        if head[offset : offset + len(signature)] == signature:
            if content_type == "image/webp" and head[:4] != b"RIFF":
                continue
            return content_type
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "image/heic"
    return None


def path_for(root: Path, sha256: str) -> Path:
    """Where the file with this digest is kept: two levels, so no directory grows huge."""
    return root / sha256[:2] / sha256


async def save(root: Path, stream, limit: int) -> tuple[str, int, bytes]:
    """Store an upload read in chunks from ``stream`` (anything with ``async read(n)``).

    Returns its SHA-256, its size and its first bytes. Written to a temporary file first and
    renamed into place, so a failed upload never leaves half a file under a real digest.
    """
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    head = b""
    descriptor, temporary = tempfile.mkstemp(dir=root, prefix=".upload-")
    try:
        with os.fdopen(descriptor, "wb") as out:
            while chunk := await stream.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise TooLarge(f"larger than {limit} bytes")
                if len(head) < 64:
                    head += chunk[: 64 - len(head)]
                digest.update(chunk)
                out.write(chunk)
        sha256 = digest.hexdigest()
        target = path_for(root, sha256)
        target.parent.mkdir(exist_ok=True)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return sha256, size, head

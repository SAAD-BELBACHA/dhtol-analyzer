from __future__ import annotations

import hashlib
from io import BytesIO
import shutil
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile


class UploadedArchiveError(RuntimeError):
    """Raised when an uploaded test archive cannot be used safely."""


def _safe_member_path(member_name: str) -> Path:
    member = Path(member_name)
    if member.is_absolute() or ".." in member.parts:
        raise UploadedArchiveError(
            f"Unsicherer ZIP-Pfad erkannt: {member_name}"
        )
    return member


def extract_uploaded_zip(
    payload: bytes,
    upload_name: str,
    base_dir: Path | None = None,
) -> Path:
    if not payload:
        raise UploadedArchiveError("ZIP-Datei ist leer.")

    digest = hashlib.sha256(payload).hexdigest()
    archive_label = Path(upload_name).stem or "upload"
    safe_label = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in archive_label
    ).strip("._")
    root = (
        base_dir
        if base_dir is not None
        else Path(tempfile.gettempdir()) / "dhtol-analyzer-uploads"
    )
    target = root / f"{safe_label or 'upload'}-{digest[:16]}"
    marker = target / ".extract_complete"
    if marker.exists():
        return target

    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise UploadedArchiveError("ZIP-Datei konnte nicht gelesen werden.") from exc

    with archive:
        members = archive.infolist()
        if not members:
            raise UploadedArchiveError("ZIP-Datei enthaelt keine Dateien.")
        for member in members:
            _safe_member_path(member.filename)

        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        archive.extractall(target)

    marker.write_text("ok\n", encoding="utf-8")
    return target

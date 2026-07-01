from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from parsers.uploaded_archive import UploadedArchiveError, extract_uploaded_zip


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_uploaded_zip_is_extracted_to_stable_folder(tmp_path: Path) -> None:
    payload = _zip_bytes({"run/sample.txt": "ok"})

    first = extract_uploaded_zip(payload, "test run.zip", tmp_path)
    second = extract_uploaded_zip(payload, "test run.zip", tmp_path)

    assert first == second
    assert (first / "run" / "sample.txt").read_text(encoding="utf-8") == "ok"


def test_uploaded_zip_rejects_path_traversal(tmp_path: Path) -> None:
    payload = _zip_bytes({"../evil.txt": "bad"})

    with pytest.raises(UploadedArchiveError, match="Unsicherer ZIP-Pfad"):
        extract_uploaded_zip(payload, "evil.zip", tmp_path)


def test_uploaded_zip_rejects_invalid_payload(tmp_path: Path) -> None:
    with pytest.raises(UploadedArchiveError, match="konnte nicht gelesen"):
        extract_uploaded_zip(b"not a zip", "broken.zip", tmp_path)


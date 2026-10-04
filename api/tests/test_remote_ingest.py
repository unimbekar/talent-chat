"""A folder check lists Drive and S3 résumés without downloading them."""

from datetime import datetime, timezone
import shutil

from app.admin.folder_ingest import scan_resumes
from app.admin.remote_ingest import materialize_drive, materialize_s3
from app.config import get_settings


class _DriveResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_drive_check_lists_a_resume_without_downloading(monkeypatch):
    seen = []

    def fake_get(url, headers=None, params=None, timeout=None):
        del url, headers, timeout
        seen.append(dict(params or {}))
        return _DriveResponse(
            {
                "files": [
                    {
                        "id": "file-1",
                        "name": "Ada Lovelace.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-02T00:00:00Z",
                        "size": "4000",
                    }
                ]
            }
        )

    monkeypatch.setattr("app.admin.remote_ingest.httpx.get", fake_get)
    root = materialize_drive("1AbC-def_GHIJK12345", "token", download=False)
    try:
        found = scan_resumes(root)
        assert len(found.chosen) == 1
        assert found.chosen[0].path.name == "Ada Lovelace.pdf"
        assert found.chosen[0].path.stat().st_size == 4000
        assert seen[0]["corpora"] == "allDrives"
        assert "pageToken" not in seen[0]
        assert "size" in seen[0]["fields"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_s3_check_lists_an_inbox_resume_without_downloading(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "talent-test-bucket")
    get_settings.cache_clear()

    class _Pager:
        def paginate(self, **kwargs):
            assert kwargs["Bucket"] == "talent-test-bucket"
            assert kwargs["Prefix"] == "inbox/Candidates/"
            yield {
                "Contents": [
                    {
                        "Key": "inbox/Candidates/Ada Lovelace.pdf",
                        "Size": 4000,
                        "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    },
                    {"Key": "inbox/Candidates/notes.txt", "Size": 40, "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc)},
                ]
            }

    class _Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return _Pager()

        def download_file(self, *args):
            raise AssertionError("a folder check must not download the résumé")

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: _Client())
    try:
        root = materialize_s3("inbox/Candidates", download=False)
        try:
            found = scan_resumes(root)
            assert [item.path.name for item in found.chosen] == ["Ada Lovelace.pdf"]
        finally:
            shutil.rmtree(root, ignore_errors=True)
    finally:
        get_settings.cache_clear()

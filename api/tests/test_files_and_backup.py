"""Local files, S3 originals, and dump upload. No live AWS calls."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.backup import fetch_dump, list_dumps, upload_dump
from app.core.files import LocalFileStore, S3FileStore, delete_stored


class _S3:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.deleted: list[str] = []

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs
        return {}

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs["Key"])
        return {}

    def get_object(self, **kwargs):
        return {"Body": _Body(self.objects[kwargs["Key"]]["Body"])}

    def list_objects_v2(self, **kwargs):
        keys = [key for key in self.objects if key.startswith(kwargs.get("Prefix", ""))]
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data


def test_local_store_round_trip(tmp_path: Path):
    store = LocalFileStore(str(tmp_path))
    locator = store.put("abc", b"resume")
    assert Path(locator).read_bytes() == b"resume"
    delete_stored(locator)
    assert not Path(locator).exists()


def test_s3_store_uses_sse_and_private_key():
    s3 = _S3()
    store = S3FileStore("talent-private", "us-east-1", client=s3)
    locator = store.put("abc123", b"resume")
    assert locator == "s3://talent-private/originals/abc123"
    saved = s3.objects["originals/abc123"]
    assert saved["ServerSideEncryption"] == "AES256"
    assert "ACL" not in saved
    delete_stored(locator, s3_client=s3)
    assert s3.deleted == ["originals/abc123"]


def test_backup_rejects_non_dumps_and_plain_text():
    s3 = _S3()
    with pytest.raises(RuntimeError):
        upload_dump(b"not a dump", "bucket", "us-east-1", client=s3)
    archive = b"PGDMP" + b"\x00rest"
    key = upload_dump(
        archive,
        "bucket",
        "us-east-1",
        client=s3,
        now=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc),
    )
    assert key == "dumps/talent-20260927T120000Z.dump"
    assert s3.objects[key]["ServerSideEncryption"] == "AES256"
    assert list_dumps("bucket", "us-east-1", client=s3) == [key]
    assert fetch_dump("bucket", key, "us-east-1", client=s3) == archive
    with pytest.raises(RuntimeError):
        fetch_dump("bucket", "originals/abc", "us-east-1", client=s3)

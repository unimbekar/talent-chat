"""Upload a pg_dump custom-format archive to S3, or fetch one back.

The archive is read from stdin:

    pg_dump -U postgres -Fc talent | python -m app.backup

Objects land at dumps/talent-YYYYMMDDTHHMMSSZ.dump with SSE-S3.
Retention is a bucket lifecycle rule on the dumps/ prefix, not this process.
"""

from datetime import datetime, timezone
import sys

from app.config import get_settings

_DUMP_MAGIC = b"PGDMP"


def upload_dump(data: bytes, bucket: str, region: str, client=None, now: datetime | None = None) -> str:
    if not bucket.strip():
        raise RuntimeError("S3_BUCKET is empty")
    if not data.startswith(_DUMP_MAGIC):
        raise RuntimeError("stdin is not a pg_dump custom-format archive")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    key = f"dumps/talent-{stamp}.dump"
    s3 = client if client is not None else _client(region)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ServerSideEncryption="AES256",
    )
    return key


def list_dumps(bucket: str, region: str, client=None) -> list[str]:
    s3 = client if client is not None else _client(region)
    keys: list[str] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "dumps/"}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        keys.extend(item["Key"] for item in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")


def fetch_dump(bucket: str, key: str, region: str, client=None) -> bytes:
    if not key.startswith("dumps/") or ".." in key:
        raise RuntimeError("refusing to fetch a key outside dumps/")
    s3 = client if client is not None else _client(region)
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    if not body.startswith(_DUMP_MAGIC):
        raise RuntimeError("object is not a pg_dump custom-format archive")
    return body


def _client(region: str):
    import boto3

    return boto3.client("s3", region_name=region)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    settings = get_settings()
    bucket = settings.s3_bucket.strip()
    if not bucket:
        print("S3_BUCKET is empty", file=sys.stderr)
        return 1
    if args[:1] == ["--list"]:
        for key in list_dumps(bucket, settings.aws_region):
            print(key)
        return 0
    if args[:1] == ["--fetch"]:
        if len(args) != 2:
            print("usage: python -m app.backup --fetch dumps/talent-....dump", file=sys.stderr)
            return 2
        sys.stdout.buffer.write(fetch_dump(bucket, args[1], settings.aws_region))
        return 0
    if args:
        print("usage: python -m app.backup [--list | --fetch KEY]", file=sys.stderr)
        return 2
    data = sys.stdin.buffer.read()
    try:
        key = upload_dump(data, bucket, settings.aws_region)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

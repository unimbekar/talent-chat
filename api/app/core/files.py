"""Original résumé files. Local disk on the Spark. S3 when S3_BUCKET is set."""

from pathlib import Path

from app.config import get_settings


class LocalFileStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def put(self, digest: str, data: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / digest
        path.write_bytes(data)
        return str(path)


class S3FileStore:
    def __init__(self, bucket: str, region: str, client=None) -> None:
        self.bucket = bucket
        self.region = region
        self._client = client

    def put(self, digest: str, data: bytes) -> str:
        key = f"originals/{digest}"
        self._s3().put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self.bucket}/{key}"

    def _s3(self):
        if self._client is not None:
            return self._client
        import boto3

        return boto3.client("s3", region_name=self.region)


def store_original(data: bytes, digest: str, s3_client=None) -> str:
    settings = get_settings()
    bucket = settings.s3_bucket.strip()
    if bucket:
        return S3FileStore(bucket, settings.aws_region, client=s3_client).put(digest, data)
    return LocalFileStore(settings.file_dir).put(digest, data)


def delete_stored(locator: str | None, s3_client=None) -> None:
    if not locator:
        return
    if locator.startswith("s3://"):
        rest = locator.removeprefix("s3://")
        bucket, separator, key = rest.partition("/")
        if not separator or not bucket or not key:
            raise OSError(f"invalid S3 locator {locator}")
        client = s3_client
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=get_settings().aws_region)
        client.delete_object(Bucket=bucket, Key=key)
        return
    path = Path(locator)
    if path.is_file():
        path.unlink()

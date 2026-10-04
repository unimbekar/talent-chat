"""Bring a Drive folder or an S3 prefix onto disk, then use the folder import.

The folder walk, newest-file rule, and unparsed list stay in folder_ingest.
"""

from datetime import datetime, timezone
from pathlib import Path
import os
import re
import shutil
import tempfile

import httpx

from app.config import get_settings

_DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_FOLDER = "application/vnd.google-apps.folder"
_GOOGLE_DOC = "application/vnd.google-apps.document"
_KEEP = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    _DOCX: ".docx",
    "text/plain": ".txt",
}
_MAX_FILES = 1500
_MAX_DEPTH = 6


class RemoteIngestError(Exception):
    pass


def parse_drive_folder(text: str) -> str:
    """Accept a folder id or a Drive folder URL."""
    raw = (text or "").strip()
    match = re.search(r"/folders/([A-Za-z0-9_-]{10,})", raw)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", raw):
        return raw
    raise RemoteIngestError("Paste a Google Drive folder link or folder id.")


_CLOSED_PREFIXES = {"originals", "dumps"}


def parse_s3_location(text: str, *, bucket: str | None = None, default_prefix: str | None = None) -> tuple[str, str]:
    """Return (bucket, key prefix) for a folder the recruiter typed.

    A leading slash or s3:// means the first segment is the bucket:
    /janus-soft-jobs-chat/Resume-Refined/AI Engineer.
    Otherwise the text is a folder inside the configured bucket.
    originals/ and dumps/ stay closed.
    """
    settings = get_settings()
    configured = (settings.s3_bucket if bucket is None else bucket).strip()
    fallback = (settings.s3_ingest_prefix if default_prefix is None else default_prefix).strip().strip("/") or "inbox"
    raw = (text or "").strip()
    names_bucket = False
    if raw.lower().startswith("s3://"):
        raw = raw[5:]
        names_bucket = True
    elif raw.startswith("/"):
        raw = raw[1:]
        names_bucket = True
    parts = [part for part in raw.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise RemoteIngestError("That folder is outside the résumé bucket.")
    chosen = configured
    key_parts = parts
    if names_bucket:
        if not parts:
            raise RemoteIngestError("Paste the bucket and folder, such as /janus-soft-jobs-chat/Resume-Refined/AI Engineer.")
        chosen = parts[0]
        key_parts = parts[1:]
    elif not parts:
        key_parts = [fallback]
    if not chosen:
        raise RemoteIngestError("Paste the bucket and folder, such as /janus-soft-jobs-chat/Resume-Refined/AI Engineer.")
    if configured and chosen != configured:
        raise RemoteIngestError(f"That path is not in bucket {configured}.")
    if key_parts and key_parts[0] in _CLOSED_PREFIXES:
        raise RemoteIngestError("originals and database dumps are not an import source.")
    prefix = "/".join(key_parts)
    return chosen, f"{prefix}/" if prefix else ""


def ingest_prefix(text: str, root: str | None = None) -> str:
    """Key prefix inside a known bucket. The first argument is the folder, not the bucket."""
    _bucket, prefix = parse_s3_location(text, bucket="talent", default_prefix=root or "inbox")
    return prefix or "inbox/"


def materialize_drive(folder: str, access_token: str, *, download: bool) -> Path:
    folder_id = parse_drive_folder(folder)
    root = Path(tempfile.mkdtemp(prefix="talent-drive-"))
    try:
        _walk_drive(root, folder_id, access_token, Path(), 0, download)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def materialize_s3(prefix: str, *, download: bool) -> Path:
    settings = get_settings()
    bucket, key_prefix = parse_s3_location(prefix)
    root = Path(tempfile.mkdtemp(prefix="talent-s3-"))
    try:
        import boto3

        client = boto3.client("s3", region_name=settings.aws_region or "us-east-1")
        pager = client.get_paginator("list_objects_v2")
        count = 0
        for page in pager.paginate(Bucket=bucket, Prefix=key_prefix):
            for item in page.get("Contents") or []:
                key = item.get("Key") or ""
                if key.endswith("/") or not _resume_suffix(Path(key).name):
                    continue
                count += 1
                if count > _MAX_FILES:
                    raise RemoteIngestError(f"That location has more than {_MAX_FILES} résumés. Split it into smaller folders.")
                relative = key[len(key_prefix) :]
                dest = _destination(root, relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if download:
                    client.download_file(bucket, key, str(dest))
                else:
                    _placeholder(dest, item.get("Size"))
                _set_mtime(dest, item.get("LastModified"))
    except RemoteIngestError:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(root, ignore_errors=True)
        code = ""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str((response.get("Error") or {}).get("Code") or "")
        detail = "That S3 folder could not be read."
        if code:
            detail = f"{detail} ({code})"
        elif type(exc).__name__ in {"NoCredentialsError", "PartialCredentialsError"}:
            detail = f"{detail} This server has no AWS credentials."
        raise RemoteIngestError(detail) from exc
    return root


def _walk_drive(root: Path, folder_id: str, token: str, relative: Path, depth: int, download: bool) -> None:
    if depth > _MAX_DEPTH:
        return
    headers = {"Authorization": f"Bearer {token}"}
    page = ""
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "corpora": "allDrives",
        }
        if page:
            params["pageToken"] = page
        try:
            response = httpx.get(_DRIVE_FILES, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = "Google Drive did not return that folder. Sign in again, and use a folder your account can open."
            if status:
                detail = f"{detail} ({status})"
            raise RemoteIngestError(detail) from exc
        for item in body.get("files") or []:
            name = _safe_part(str(item.get("name") or "file"))
            mime = str(item.get("mimeType") or "")
            if mime == _FOLDER:
                _walk_drive(root, str(item["id"]), token, relative / name, depth + 1, download)
                continue
            if mime == _GOOGLE_DOC:
                suffix = ".docx"
            else:
                suffix = _KEEP.get(mime) or _resume_suffix(name)
            if not suffix:
                continue
            dest_name = name if name.lower().endswith(suffix) else name + suffix
            dest = _destination(root, str(relative / dest_name))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if download:
                _download_drive(str(item["id"]), mime, dest, headers)
            else:
                _placeholder(dest, item.get("size"))
            _set_mtime(dest, item.get("modifiedTime"))
            if sum(1 for _ in root.rglob("*") if _.is_file()) > _MAX_FILES:
                raise RemoteIngestError(f"That folder has more than {_MAX_FILES} résumés. Split it into smaller folders.")
        page = body.get("nextPageToken") or ""
        if not page:
            return


def _download_drive(file_id: str, mime: str, dest: Path, headers: dict[str, str]) -> None:
    if mime == _GOOGLE_DOC:
        url = f"{_DRIVE_FILES}/{file_id}/export"
        params = {"mimeType": _DOCX}
    else:
        url = f"{_DRIVE_FILES}/{file_id}"
        params = {"alt": "media", "supportsAllDrives": "true"}
    try:
        with httpx.stream("GET", url, headers=headers, params=params, timeout=60) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    except httpx.HTTPError as exc:
        raise RemoteIngestError(f"Could not download {dest.name} from Drive.") from exc


def _destination(root: Path, relative: str) -> Path:
    parts = [_safe_part(part) for part in Path(relative).parts if part not in {"", ".", ".."}]
    dest = root.joinpath(*parts) if parts else root / "resume"
    if not _within(dest, root):
        raise RemoteIngestError("A file name in that folder could not be saved.")
    return dest


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _safe_part(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ ()-]", "_", name).strip(" .")
    if cleaned in {"", ".", ".."}:
        return "file"
    return cleaned[:120]


def _resume_suffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".pdf", ".doc", ".docx", ".txt"}:
        return suffix
    return ""


def _placeholder(path: Path, size) -> None:
    """Keep the listed size so a folder check can see the file before it is downloaded."""
    try:
        nbytes = int(size)
    except (TypeError, ValueError):
        nbytes = 256
    if nbytes < 0:
        nbytes = 256
    if nbytes > 20 * 1024 * 1024:
        nbytes = 20 * 1024 * 1024
    path.write_bytes(b"")
    os.truncate(path, nbytes)


def _set_mtime(path: Path, value) -> None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return
    else:
        return
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))

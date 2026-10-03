"""Workspace sign-in accepts only the company domain. S3 import stays in the inbox."""

import pytest

from app.admin.google_auth import workspace_account
from app.admin.remote_ingest import RemoteIngestError, ingest_prefix, parse_drive_folder


def test_workspace_account_accepts_the_company_domain():
    assert workspace_account(
        "recruiter@janus-soft.com",
        "janus-soft.com",
        email_verified=True,
        allowed="janus-soft.com",
    )


def test_workspace_account_rejects_personal_gmail_and_unverified_mail():
    assert not workspace_account("recruiter@gmail.com", "", email_verified=True, allowed="janus-soft.com")
    assert not workspace_account("recruiter@janus-soft.com", "gmail.com", email_verified=True, allowed="janus-soft.com")
    assert not workspace_account("recruiter@janus-soft.com", "janus-soft.com", email_verified=False, allowed="janus-soft.com")


def test_drive_folder_link_and_bare_id():
    assert parse_drive_folder("https://drive.google.com/drive/folders/1AbC-def_GHIJK12345") == "1AbC-def_GHIJK12345"
    assert parse_drive_folder("1AbC-def_GHIJK12345") == "1AbC-def_GHIJK12345"
    with pytest.raises(RemoteIngestError):
        parse_drive_folder("https://drive.google.com/file/d/1AbC-def_GHIJK12345/view")


def test_s3_prefix_stays_inside_the_inbox():
    assert ingest_prefix("", "inbox") == "inbox/"
    assert ingest_prefix("inbox/2026", "inbox") == "inbox/2026/"
    with pytest.raises(RemoteIngestError):
        ingest_prefix("originals/", "inbox")
    with pytest.raises(RemoteIngestError):
        ingest_prefix("inbox/../dumps", "inbox")

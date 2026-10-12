"""Recruiter view of the candidate benefits guide. The file lives in the project benefits folder."""

from pathlib import Path
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.admin.access import require_desk

router = APIRouter(prefix="/admin/benefits", tags=["benefits"])
public_router = APIRouter(prefix="/public/benefits", tags=["benefits"])
_MEDIA = re.compile(r"^[a-z0-9-]+\.(jpg|png)$")


def benefits_dir() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "benefits", here.parents[3] / "benefits", Path("/app/benefits")):
        if (candidate / "benefits.json").is_file():
            return candidate
    raise HTTPException(status_code=404, detail="The benefits guide is not installed.")


def load_guide() -> dict:
    folder = benefits_dir()
    try:
        return json.loads((folder / "benefits.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail="The benefits guide could not be read.") from exc


@router.get("")
def read_benefits(session: Session = Depends(require_desk)):
    del session
    guide = load_guide()
    guide["download"] = "/admin/benefits/download"
    return guide


@router.get("/download")
def download_benefits(session: Session = Depends(require_desk)):
    del session
    guide = load_guide()
    path = benefits_dir() / guide["filename"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The benefits document is not on file.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=guide["filename"],
    )


def _media_file(name: str) -> tuple[Path, str]:
    if not _MEDIA.fullmatch(name):
        raise HTTPException(status_code=404, detail="That image is not on file.")
    path = benefits_dir() / "images" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="That image is not on file.")
    media = "image/png" if name.endswith(".png") else "image/jpeg"
    return path, media


@router.get("/media/{name}")
def benefit_media(name: str, session: Session = Depends(require_desk)):
    del session
    path, media = _media_file(name)
    return FileResponse(path, media_type=media)


@public_router.get("")
def public_benefits():
    """The candidate guide. Visitors can read every term; the document file stays on the recruiter desk."""
    guide = load_guide()
    guide.pop("filename", None)
    return guide


@public_router.get("/media/{name}")
def public_benefit_media(name: str):
    path, media = _media_file(name)
    return FileResponse(path, media_type=media)

"""Helpers to materialise an uploaded image as a local file path that the
existing tool functions can consume.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional

import requests
from fastapi import HTTPException, UploadFile


_TMP_DIR = Path(tempfile.gettempdir()) / "lab2phr-uploads"
_TMP_DIR.mkdir(parents=True, exist_ok=True)


def _suffix_for(name: str | None, default: str = ".jpg") -> str:
    if not name:
        return default
    suffix = Path(name).suffix
    return suffix if suffix else default


async def materialize_image(
    file: Optional[UploadFile] = None,
    image_url: Optional[str] = None,
) -> str:
    """Persist an uploaded image (or fetched URL) to a temp path. Returns the path."""
    if file is None and not image_url:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'image_url'.")

    suffix = _suffix_for(file.filename if file else image_url)
    target = _TMP_DIR / f"{uuid.uuid4().hex}{suffix}"

    if file is not None:
        data = await file.read()
        target.write_bytes(data)
    else:
        resp = requests.get(image_url, timeout=30)  # type: ignore[arg-type]
        if resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download image_url ({resp.status_code}).",
            )
        target.write_bytes(resp.content)

    return str(target)

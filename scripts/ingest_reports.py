"""Embed report images with Azure AI Vision and upsert into Azure AI Search.

Public function `ingest(path)` is also used as the IngestAgent's tool.
"""
import hashlib
import os
from pathlib import Path

import requests
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from dotenv import load_dotenv

load_dotenv()

VISION_ENDPOINT = os.environ["ENDPOINT_URL"]
VISION_KEY = os.environ["AZURE_OPENAI_API_KEY"]
VECTOR_DIM = 1024
PROFILE = "hnsw-profile"


def _ensure_index() -> None:
    idx_client = SearchIndexClient(
        os.environ["AZURE_SEARCH_ENDPOINT"],
        AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )
    idx_client.create_or_update_index(SearchIndex(
        name=os.environ["AZURE_SEARCH_INDEX_NAME"],
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
            SearchableField(name="file_path", type=SearchFieldDataType.String, filterable=True),
            SearchField(
                name="image_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=VECTOR_DIM,
                vector_search_profile_name=PROFILE,
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[VectorSearchProfile(name=PROFILE, algorithm_configuration_name="hnsw-config")],
        ),
    ))


def _doc_id(path: Path) -> str:
    """Stable key for local files so re-ingest updates, not duplicates."""
    canonical = path.expanduser().resolve().as_posix().lower()
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _embed_image(image_path: str) -> list[float]:
    """Call Azure AI Vision for a 1024-dim multimodal vector."""
    url = f"{VISION_ENDPOINT.rstrip('/')}/computervision/retrieval:vectorizeImage"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": VISION_KEY,
                     "Content-Type": "application/octet-stream"},
            params={"api-version": "2024-02-01", "model-version": "2023-04-15"},
            data=f.read(),
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["vector"]


def ingest(path: str) -> dict:
    """Embed an image (or every image under a folder) and upsert into the search index."""
    _ensure_index()
    target = Path(path)
    if target.is_dir():
        files = [p for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG")
                 for p in target.rglob(f"*.{ext}")]
        files.sort(key=lambda p: p.as_posix().lower())
    else:
        files = [target]

    docs = []
    for f in files:
        print(f"Embedding {f.name}...")
        docs.append({
            "id": _doc_id(f),
            "file_path": str(f.expanduser().resolve()),
            "image_vector": _embed_image(str(f)),
        })

    if docs:
        client = SearchClient(
            os.environ["AZURE_SEARCH_ENDPOINT"],
            os.environ["AZURE_SEARCH_INDEX_NAME"],
            AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
        )
        client.upload_documents(documents=docs)
    print(f"✅ Uploaded {len(docs)} document(s).")
    return {"uploaded": len(docs), "ids": [d["id"] for d in docs]}


if __name__ == "__main__":
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "").lower()
    folder = os.environ["DATA_FOLDER"] if "blob" in index_name else os.environ["SAMPLE_DATA_FOLDER"]
    ingest(folder)

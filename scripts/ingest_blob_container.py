"""Embed every image in an Azure Blob container and upsert into a *new* AI Search index.

Keeps the existing local index untouched. Index is auto-created if missing.

Env (in .env or shell):
  AZURE_SEARCH_ENDPOINT         (required)
  AZURE_SEARCH_KEY              (required, admin key)
    AZURE_SEARCH_INDEX_NAME       (required; target index)
  ENDPOINT_URL                  (Cognitive Services / Vision endpoint)
  AZURE_OPENAI_API_KEY          (used as Vision key in this repo)
  BLOB_CONTAINER_URL            (required; e.g. https://<acct>.blob.core.windows.net/<container>)
  BLOB_SAS_TOKEN                (optional; if container is private, paste a SAS like "?sv=...&sig=...")

Run:
  python -m scripts.ingest_blob_container
"""
import hashlib
import os
from typing import Iterable

import requests
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
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
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

load_dotenv()

VISION_ENDPOINT = os.environ["ENDPOINT_URL"]
VISION_KEY = os.environ["AZURE_OPENAI_API_KEY"]
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]

CONTAINER_URL = os.environ["BLOB_CONTAINER_URL"]
INDEX_NAME = os.environ["AZURE_SEARCH_INDEX_NAME"]
SAS_TOKEN = os.environ.get("BLOB_SAS_TOKEN", "").strip()

IMAGE_EXT = (".jpg", ".jpeg", ".png")
VECTOR_DIM = 1024
PROFILE = "hnsw-profile"


def _container_client() -> ContainerClient:
    """Try anonymous, then SAS, then AAD."""
    if SAS_TOKEN:
        url = CONTAINER_URL + (SAS_TOKEN if SAS_TOKEN.startswith("?") else "?" + SAS_TOKEN)
        return ContainerClient.from_container_url(url)
    try:
        c = ContainerClient.from_container_url(CONTAINER_URL)
        # touch to verify access
        next(iter(c.list_blob_names(results_per_page=1).by_page()))
        return c
    except Exception:
        return ContainerClient.from_container_url(CONTAINER_URL, credential=DefaultAzureCredential())


def _ensure_index() -> None:
    idx_client = SearchIndexClient(SEARCH_ENDPOINT, AzureKeyCredential(SEARCH_KEY))
    if INDEX_NAME in [i.name for i in idx_client.list_indexes()]:
        print(f"[index] reuse {INDEX_NAME}")
        return

    print(f"[index] creating {INDEX_NAME}")
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="file_path", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="image_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name=PROFILE,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name=PROFILE, algorithm_configuration_name="hnsw-config")],
    )
    idx_client.create_index(SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search))


def _embed_bytes(data: bytes) -> list[float]:
    url = f"{VISION_ENDPOINT.rstrip('/')}/computervision/retrieval:vectorizeImage"
    resp = requests.post(
        url,
        headers={"Ocp-Apim-Subscription-Key": VISION_KEY,
                 "Content-Type": "application/octet-stream"},
        params={"api-version": "2024-02-01", "model-version": "2023-04-15"},
        data=data,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["vector"]


def _iter_image_blobs(container: ContainerClient) -> Iterable[str]:
    for name in container.list_blob_names():
        if name.lower().endswith(IMAGE_EXT):
            yield name


def ingest(_path: str = "") -> dict:
    """Ingest all eligible images from configured blob container into blob index.

    `_path` is accepted for tool signature compatibility with local ingest.
    """
    _ensure_index()
    container = _container_client()
    search = SearchClient(SEARCH_ENDPOINT, INDEX_NAME, AzureKeyCredential(SEARCH_KEY))

    docs: list[dict] = []
    total = 0
    BATCH = 50
    for name in _iter_image_blobs(container):
        try:
            print(f"Embedding {name}...")
            data = container.download_blob(name).readall()
            docs.append({
                "id": hashlib.sha1(name.encode()).hexdigest(),
                "file_path": f"{CONTAINER_URL}/{name}",
                "image_vector": _embed_bytes(data),
            })
        except Exception as exc:
            print(f"  ! failed: {exc}")
            continue

        if len(docs) >= BATCH:
            search.upload_documents(documents=docs)
            total += len(docs)
            print(f"[upload] +{len(docs)} (total {total})")
            docs = []

    if docs:
        search.upload_documents(documents=docs)
        total += len(docs)

    print(f"\n✅ Uploaded {total} documents into index '{INDEX_NAME}'.")
    return {"uploaded": total, "index": INDEX_NAME, "container": CONTAINER_URL}


def main() -> None:
    ingest("")


if __name__ == "__main__":
    main()

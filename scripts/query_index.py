"""Vector-search the report index using Azure AI Vision text embeddings.

Public function `search(query, k)` is also used as the QueryAgent's tool.
"""
import os

import requests
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv

load_dotenv()

VISION_ENDPOINT = os.environ["ENDPOINT_URL"]
VISION_KEY = os.environ["AZURE_OPENAI_API_KEY"]


def _embed_text(text: str) -> list[float]:
    url = f"{VISION_ENDPOINT.rstrip('/')}/computervision/retrieval:vectorizeText"
    resp = requests.post(
        url,
        headers={"Ocp-Apim-Subscription-Key": VISION_KEY, "Content-Type": "application/json"},
        params={"api-version": "2024-02-01", "model-version": "2023-04-15"},
        json={"text": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["vector"]


def search(query: str, k: int = 5) -> list[dict]:
    """Return the top-k report matches: [{id, file_path, score}, ...]."""
    client = SearchClient(
        os.environ["AZURE_SEARCH_ENDPOINT"],
        os.environ["AZURE_SEARCH_INDEX_NAME"],
        AzureKeyCredential(os.environ["AZURE_SEARCH_QUERY_KEY"]),
    )
    vq = VectorizedQuery(vector=_embed_text(query), k_nearest_neighbors=k, fields="image_vector")
    results = client.search(search_text=None, vector_queries=[vq], top=k, select=["id", "file_path"])
    return [
        {"id": d.get("id", ""), "file_path": d.get("file_path", ""), "score": d.get("@search.score", 0.0)}
        for d in results
    ]


if __name__ == "__main__":
    q = "Find the report with HBA1C"
    print(f"Query: {q}\n")
    for i, m in enumerate(search(q), 1):
        print(f"{i}. {m['file_path']}  (score={m['score']:.4f})")

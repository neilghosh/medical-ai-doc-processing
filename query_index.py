import os
from typing import List
import requests
from env_utils import load_env_file, resolve_endpoint, resolve_vision_key


def create_search_client():
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.models import VectorizedQuery
    except ImportError as exc:
        raise ImportError(
            "Missing Azure Search SDK. Install with: pip install azure-search-documents"
        ) from exc

    search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    search_key = os.getenv("AZURE_SEARCH_QUERY_KEY") or os.getenv("AZURE_SEARCH_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "medical-images-index")

    if not search_endpoint or not search_key:
        raise ValueError("Missing AZURE_SEARCH_ENDPOINT and a key (AZURE_SEARCH_QUERY_KEY or AZURE_SEARCH_KEY).")

    return SearchClient(
        endpoint=search_endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(search_key),
    ), VectorizedQuery


def get_text_embedding(query_text: str) -> List[float]:
    vision_endpoint = (
        os.getenv("AZURE_VISION_ENDPOINT")
        or os.getenv("AZURE_AI_SERVICES_ENDPOINT")
        or resolve_endpoint()
    )
    vision_key = resolve_vision_key()

    if not vision_endpoint or not vision_key:
        raise ValueError(
            "Missing vision settings for vector query. Set endpoint and key via AZURE_VISION_ENDPOINT/AZURE_VISION_KEY "
            "or their fallbacks."
        )

    url = f"{vision_endpoint.rstrip('/')}/computervision/retrieval:vectorizeText"
    headers = {
        "Ocp-Apim-Subscription-Key": vision_key,
        "Content-Type": "application/json",
    }
    params = {
        "api-version": "2024-02-01",
        "model-version": "2023-04-15",
    }
    payload = {"text": query_text}

    response = requests.post(url, headers=headers, params=params, json=payload, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"Vision text vectorization failed: {response.status_code} {response.text}")

    return response.json()["vector"]


def main() -> None:
    load_env_file(".env")
    search_client, VectorizedQuery = create_search_client()

    query_text = "Find the report with HBA1C"
    print(f"Running query: {query_text}\n")

    query_vector = get_text_embedding(query_text)
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=5,
        fields="image_vector",
    )

    results = search_client.search(
        search_text=None,
        vector_queries=[vector_query],
        top=5,
        select=["id", "file_path"],
    )

    rows: List[dict] = list(results)
    if not rows:
        print("No matches found.")
        return

    print("Top matches:")
    for i, doc in enumerate(rows, start=1):
        doc_id = doc.get("id", "")
        file_path = doc.get("file_path", "")
        score = doc.get("@search.score", "")
        print(f"{i}. id={doc_id} | file_path={file_path} | score={score}")


if __name__ == "__main__":
    main()

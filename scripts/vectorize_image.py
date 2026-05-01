"""Utility: print the Azure AI Vision vector for a local image file.

Usage:
    python scripts/vectorize_image.py sampledata/report1.jpg

Outputs a JSON array of floats that can be pasted directly into the
Azure AI Search Explorer as a `kind: "vector"` query.
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

VISION_ENDPOINT = os.environ["ENDPOINT_URL"]
VISION_KEY = os.environ["AZURE_OPENAI_API_KEY"]
EXPECTED_DIM = 1024


def vectorize_image(image_path: str) -> list[float]:
    url = f"{VISION_ENDPOINT.rstrip('/')}/computervision/retrieval:vectorizeImage"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            headers={
                "Ocp-Apim-Subscription-Key": VISION_KEY,
                "Content-Type": "application/octet-stream",
            },
            params={"api-version": "2024-02-01", "model-version": "2023-04-15"},
            data=f.read(),
            timeout=60,
        )
    vector = resp.json()["vector"]
    if len(vector) != EXPECTED_DIM:
        raise ValueError(f"Expected {EXPECTED_DIM} dimensions, got {len(vector)}")
    return vector


if __name__ == "__main__":
    vector = vectorize_image(sys.argv[1])
    vector_json = json.dumps(vector, separators=(",", ":"))
    print("{")
    print('  "select": "id, file_path",')
    print('  "vectorQueries": [')
    print("    {")
    print('      "kind": "vector",')
    print(f'      "vector": {vector_json},')
    print('      "fields": "image_vector",')
    print('      "k": 5')
    print("    }")
    print("  ]")
    print("}")

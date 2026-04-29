import os
import glob
import hashlib
import requests
from pathlib import Path
from env_utils import load_env_file, resolve_endpoint, resolve_vision_key

# --- Configuration ---
load_env_file(".env")

# Prefer explicit Vision settings, then fall back to current Foundry/AI service endpoint+key names.
VISION_ENDPOINT = (
    os.getenv("AZURE_VISION_ENDPOINT")
    or os.getenv("AZURE_AI_SERVICES_ENDPOINT")
    or resolve_endpoint()
)
VISION_KEY = resolve_vision_key()

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "medical-images-index")
DATA_FOLDER = os.getenv("DATA_FOLDER", "data")

if not VISION_ENDPOINT:
    raise ValueError(
        "Missing vision endpoint. Set one of: AZURE_VISION_ENDPOINT, AZURE_AI_SERVICES_ENDPOINT, "
        "ENDPOINT_URL, or AZURE_EXISTING_AIPROJECT_ENDPOINT."
    )

if not VISION_KEY:
    raise ValueError(
        "Missing vision key. Set one of: AZURE_VISION_KEY, AZURE_AI_SERVICES_KEY, or AZURE_OPENAI_API_KEY."
    )

if not SEARCH_ENDPOINT or not SEARCH_KEY:
    raise ValueError(
        "Missing Azure AI Search settings. Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY."
    )

# Initialize the Search Client
def create_search_client():
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
    except ImportError as exc:
        raise ImportError(
            "Missing Azure Search SDK. Install with: pip install azure-search-documents"
        ) from exc

    return SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_KEY),
    )

def get_image_embedding(image_path):
    """Calls Azure AI Vision to get the 1024-dimensional vector for an image."""
    with open(image_path, "rb") as img:
        image_data = img.read()
        
    url = f"{VISION_ENDPOINT.rstrip('/')}/computervision/retrieval:vectorizeImage"
    headers = {
        "Ocp-Apim-Subscription-Key": VISION_KEY,
        "Content-Type": "application/octet-stream"
    }
    params = {
        "api-version": "2024-02-01",
        "model-version": "2023-04-15"
    }
    
    print(f"Embedding {os.path.basename(image_path)}...")
    response = requests.post(url, headers=headers, params=params, data=image_data)
    
    if response.status_code != 200:
        raise Exception(f"Vision API Error: {response.text}")
        
    return response.json()["vector"]

def main():
    search_client = create_search_client()

    print(f"Scanning {DATA_FOLDER} for images...")
    # Recursively grab common image file formats from the data folder.
    image_files = []
    data_dir = Path(DATA_FOLDER)
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        image_files.extend(str(path) for path in data_dir.rglob(pattern))
    
    documents_to_upload = []
    
    for file_path in image_files:
        try:
            # 1. Generate the multimodal embedding
            vector = get_image_embedding(file_path)
            
            # 2. Create the document schema for Azure Search
            doc = {
                # Stable id makes repeated ingestions perform upserts instead of creating duplicates.
                "id": hashlib.sha1(file_path.encode("utf-8")).hexdigest(),
                "file_path": file_path,
                "image_vector": vector
            }
            documents_to_upload.append(doc)
            
        except Exception as e:
            print(f"Failed to process {file_path}: {e}")

    # 3. Upload batch to Azure AI Search
    if documents_to_upload:
        print(f"\nUploading {len(documents_to_upload)} documents to Azure AI Search...")
        result = search_client.upload_documents(documents=documents_to_upload)
        print("✅ Ingestion Complete. Data is ready for the live demo.")
    else:
        print("No valid images found or processed.")

if __name__ == "__main__":
    main()
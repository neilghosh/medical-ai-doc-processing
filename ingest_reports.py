import os
import glob
import hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

VISION_ENDPOINT = os.environ["ENDPOINT_URL"]
VISION_KEY = os.environ["AZURE_OPENAI_API_KEY"]
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
INDEX_NAME = os.environ["AZURE_SEARCH_INDEX_NAME"]
DATA_FOLDER = os.environ["DATA_FOLDER"]

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
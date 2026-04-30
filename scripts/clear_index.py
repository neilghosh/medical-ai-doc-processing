import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient


KEY_FIELD = "id"


def main() -> None:
    load_dotenv()
    client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )

    total = 0
    while True:
        batch = list(client.search("*", select=[KEY_FIELD], top=1000))
        if not batch:
            break
        client.delete_documents(documents=[{KEY_FIELD: d[KEY_FIELD]} for d in batch])
        total += len(batch)
        print(f"Deleted {total} documents so far...")

    print(f"Index emptied. Total deleted: {total}")


if __name__ == "__main__":
    main()

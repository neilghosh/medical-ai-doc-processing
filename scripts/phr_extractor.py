"""Extract and explain PHR records from lab-report images."""
import base64
import json
import logging
import os

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()
log = logging.getLogger(__name__)

# Demo: always dump raw chat-completion HTTP traffic to stdout.
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
os.environ["OPENAI_LOG"] = "debug"

_client = AzureOpenAI(
    azure_endpoint=os.environ["ENDPOINT_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2025-01-01-preview",
)
_DEPLOYMENT = os.environ["DEPLOYMENT_NAME"]

_PHR_JSON_SCHEMA = {
    "name": "phr_record",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "report_date": {"type": ["string", "null"]},
            "patient_name": {"type": ["string", "null"]},
            "test_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "test_name": {"type": "string"},
                        "result": {"type": ["number", "null"]},
                        "ref_range": {"type": ["string", "null"]},
                        "unit": {"type": ["string", "null"]},
                    },
                    "required": ["test_name", "result", "ref_range", "unit"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["report_date", "patient_name", "test_results"],
        "additionalProperties": False,
    },
}

_EXTRACTION_INSTRUCTIONS = (
    "Extract the lab report into structured JSON using the provided schema. "
    "For each test in test_results, always fill test_name, result, ref_range, and unit. "
    "For ref_range, copy the reference interval text exactly from the report if present. "
    "Look for labels like: Ref Range, Reference Range, Normal Range, Bio Ref Interval, Range. "
    "If low/high bounds are shown in separate columns, combine as '<low>-<high>'. "
    "Do not invent ranges. Use null only when no reference interval is visible for that test."
)


def _read_image_bytes(image_path: str) -> bytes:
    """Read image bytes from a local path or an Azure blob URL (via MI)."""
    log.info("reading image: %s", image_path)
    try:
        if image_path.startswith(("http://", "https://")):
            return BlobClient.from_blob_url(
                image_path, credential=DefaultAzureCredential()
            ).download_blob().readall()
        return open(image_path, "rb").read()
    except Exception:
        log.exception("failed to read image: %s", image_path)
        raise


def extract(image_path: str) -> dict:
    """Extract PHR data from lab-report image."""
    b64 = base64.b64encode(_read_image_bytes(image_path)).decode()
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": _EXTRACTION_INSTRUCTIONS,
                },
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        response_format={"type": "json_schema", "json_schema": _PHR_JSON_SCHEMA},
        temperature=0,
        max_tokens=800,
    )
    content = resp.choices[0].message.content or "{}"
    # Remove markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1]).strip()
    return json.loads(content)




def explain(record: dict) -> str:
    """Return patient-friendly explanation of PHR record."""
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You are a clinical assistant. Summarize this PHR in 3-4 plain sentences for the patient. Flag unusual values."},
            {"role": "user", "content": json.dumps(record)},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    return resp.choices[0].message.content or ""


if __name__ == "__main__":
    img = os.environ.get("LAB_IMAGE_PATH", "data/report1.jpg")
    record = extract(img)
    print(json.dumps(record, indent=2))
    print("\n--- Explanation ---")
    print(explain(record))

"""Extract a structured PHR record from a lab-report image and explain it.

Public functions `extract(image_path)` and `explain(record)` are also used as
the PHRAgent's tools.
"""
import base64
import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import AzureOpenAI
from pydantic import BaseModel, Field

load_dotenv()

_client = AzureOpenAI(
    azure_endpoint=os.environ["ENDPOINT_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2025-01-01-preview",
)
_DEPLOYMENT = os.environ["DEPLOYMENT_NAME"]


class PHRRecord(BaseModel):
    report_date: Optional[str] = None
    patient_name: Optional[str] = None
    platelet_count: Optional[float] = None
    platelet_unit: Optional[str] = None
    hemoglobin: Optional[float] = None
    hemoglobin_unit: Optional[str] = None
    wbc_count: Optional[float] = None
    wbc_unit: Optional[str] = None
    rbc_count: Optional[float] = None
    rbc_unit: Optional[str] = None
    hematocrit: Optional[float] = None
    total_cholesterol: Optional[float] = None
    ldl_cholesterol: Optional[float] = None
    hdl_cholesterol: Optional[float] = None
    triglycerides: Optional[float] = None
    glucose: Optional[float] = None
    notes: Optional[str] = Field(default=None, description="Important observations")


_EXTRACT_PROMPT = (
    "Extract this lab report into JSON with these keys exactly: "
    + ", ".join(PHRRecord.model_fields.keys())
    + ". Use null if a value is not present. Return valid JSON only."
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    return text


def extract(image_path: str) -> dict:
    """Run GPT-4o vision on a lab-report image; return a validated PHRRecord dict."""
    b64 = base64.b64encode(open(image_path, "rb").read()).decode()
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _EXTRACT_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        temperature=0,
        max_tokens=800,
    )
    raw = resp.choices[0].message.content or "{}"
    return PHRRecord.model_validate(json.loads(_strip_fences(raw))).model_dump()


_EXPLAIN_SYS = (
    "You are a friendly clinical assistant. Given a structured PHR JSON record, "
    "produce a 4-6 sentence plain-language summary for the patient. Flag values "
    "that look outside common reference ranges and recommend confirming with a "
    "clinician. Do not invent missing values."
)


def explain(record: dict) -> str:
    """Return a patient-friendly explanation of a PHR record."""
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[
            {"role": "system", "content": _EXPLAIN_SYS},
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

import json
import os
import base64
from typing import Optional

from openai import AzureOpenAI
from pydantic import BaseModel, Field, ValidationError


def load_env_file(env_path: str = ".env") -> None:
    """Load .env key-value pairs into process env if not already set."""
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class PHRRecord(BaseModel):
    report_date: Optional[str] = Field(default=None, description="Date of report or sample collection")
    patient_name: Optional[str] = None
    platelet_count: Optional[float] = Field(default=None, description="Platelet count numeric value")
    platelet_unit: Optional[str] = None
    hemoglobin: Optional[float] = Field(default=None, description="Hemoglobin numeric value")
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
    notes: Optional[str] = Field(default=None, description="Any important observations from the report")


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def parse_json_content(raw_content: str) -> dict:
    """Parse model JSON response, with fallback for fenced blocks."""
    text = raw_content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return json.loads(text)


def main() -> None:
    load_env_file(".env")

    endpoint = os.getenv("ENDPOINT_URL", "https://medical-document-processing.cognitiveservices.azure.com/")
    deployment = os.getenv("DEPLOYMENT_NAME", "gpt-4o")
    subscription_key = os.getenv("AZURE_OPENAI_API_KEY", "REPLACE_WITH_YOUR_KEY_VALUE_HERE")

    image_path = os.getenv("LAB_IMAGE_PATH", "data/report1.jpg")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=subscription_key,
        api_version="2025-01-01-preview",
    )

    base64_image = encode_image(image_path)

    prompt = (
        "Extract this lab report into JSON with these keys exactly: "
        "report_date, patient_name, platelet_count, platelet_unit, hemoglobin, hemoglobin_unit, "
        "wbc_count, wbc_unit, rbc_count, rbc_unit, hematocrit, total_cholesterol, "
        "ldl_cholesterol, hdl_cholesterol, triglycerides, glucose, notes. "
        "Use null if a value is not present. Return valid JSON only."
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        temperature=0,
        max_tokens=800,
    )

    raw = response.choices[0].message.content or "{}"

    try:
        parsed = parse_json_content(raw)
        record = PHRRecord.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        print("Failed to parse structured output. Raw response:")
        print(raw)
        raise exc

    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

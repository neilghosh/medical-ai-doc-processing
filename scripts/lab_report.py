"""Step 1 baseline: zero-shot vision Q&A on a single lab-report image."""
import base64
import os

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.environ["ENDPOINT_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2025-01-01-preview",
)

image_path = os.environ.get("LAB_IMAGE_PATH", "sampledata/report1.jpg")
b64 = base64.b64encode(open(image_path, "rb").read()).decode()

print(f"Passing {image_path} to GPT-4o (zero-shot)...\n")

resp = client.chat.completions.create(
    model=os.environ["DEPLOYMENT_NAME"],
    messages=[{
        "role": "user",
        "content": [
            {"type": "text",
             "text": "Read this lab report. What is the patient's platelet count? Just give me the number."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ],
    }],
    max_tokens=300,
)

print("--- RAW MODEL RESPONSE ---")
print(resp.choices[0].message.content)

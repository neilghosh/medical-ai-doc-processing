import os
import base64
from openai import AzureOpenAI
from dotenv import load_dotenv

# 1. Helper function to encode the local image to Base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 2. Initialize the Azure Client
load_dotenv()

endpoint = os.environ["ENDPOINT_URL"]
deployment = os.environ["DEPLOYMENT_NAME"]
subscription_key = os.environ["AZURE_OPENAI_API_KEY"]

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=subscription_key,
    api_version="2025-01-01-preview"
)

# 3. Target the image
image_path = "data/report1.jpg"
base64_image = encode_image(image_path)

print(f"Passing {image_path} to GPT-4o (Zero-Shot)...\n")

# 4. Standard Chat Completion (No strict schema yet)
response = client.chat.completions.create(
    model=deployment,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Read this lab report. What is the patient's Platelate count ? Just give me the numbers."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    max_tokens=300
)

# 5. Print the raw text response
print("--- RAW AGENT RESPONSE ---")
print(response.choices[0].message.content)
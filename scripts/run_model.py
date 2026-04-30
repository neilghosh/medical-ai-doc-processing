"""Step 0 baseline: confirm the Azure OpenAI deployment is reachable."""
import os

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.environ["ENDPOINT_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2025-01-01-preview",
)

completion = client.chat.completions.create(
    model=os.environ["DEPLOYMENT_NAME"],
    messages=[
        {"role": "system", "content": "You are an AI assistant that helps people find information."},
        {"role": "user", "content": "I am going to Paris, what should I see?"},
    ],
    max_tokens=300,
    temperature=0.7,
)

print(completion.choices[0].message.content)

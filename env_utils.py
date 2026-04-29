import os
from typing import Optional


DEFAULT_ENDPOINT = "https://medical-document-processing.cognitiveservices.azure.com/"


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


def resolve_endpoint() -> str:
    return (
        os.getenv("ENDPOINT_URL")
        or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        or os.getenv("AZURE_VISION_ENDPOINT")
        or DEFAULT_ENDPOINT
    )


def resolve_openai_key(default: Optional[str] = None) -> Optional[str]:
    return os.getenv("AZURE_OPENAI_API_KEY", default)


def resolve_vision_key() -> Optional[str]:
    return (
        os.getenv("AZURE_VISION_KEY")
        or os.getenv("AZURE_AI_SERVICES_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
    )

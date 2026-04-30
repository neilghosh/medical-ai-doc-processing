"""Sequential demo pipeline: Ingest -> Query -> PHR (extract + explain).

Runs the same script functions the agents use as tools.

    python -m agents.pipeline --image data/report1.jpg --query "platelet count"
"""
import argparse
import json
import os

from scripts.ingest_reports import ingest
from scripts.phr_extractor import explain, extract
from scripts.query_index import search


def _hr(title: str) -> None:
    print("\n" + "=" * 8 + f" {title} " + "=" * 8)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image", default=os.environ.get("LAB_IMAGE_PATH", "data/report1.jpg"))
    p.add_argument("--query", default="Find the report with HBA1C")
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    _hr("Stage 1 - IngestAgent")
    print(json.dumps(ingest(args.image), indent=2))

    _hr("Stage 2 - QueryAgent")
    matches = search(args.query, k=args.top_k)
    print(json.dumps(matches, indent=2))

    target = matches[0]["file_path"] if matches else args.image
    _hr(f"Stage 3 - PHRAgent.extract ({target})")
    record = extract(target)
    print(json.dumps(record, indent=2))

    _hr("Stage 3 - PHRAgent.explain")
    print(explain(record))


if __name__ == "__main__":
    main()

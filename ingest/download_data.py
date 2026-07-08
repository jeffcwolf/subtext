#!/usr/bin/env python3
"""Download the kurry earnings-call dataset and save it to ./data/.

The rest of the pipeline reads the transcripts from a local, on-disk copy at
``./data/kurry_transcripts/`` (see CLAUDE.md). This script fetches the dataset
from the HuggingFace Hub once and persists it with ``save_to_disk`` so every
later step can load it offline via ``datasets.load_from_disk``.

Usage:
    python ingest/download_data.py

Requires outbound network access to huggingface.co. If your environment blocks
that host, run this script somewhere with access and copy the resulting
``data/kurry_transcripts/`` directory into place, or set HF_ENDPOINT to a
reachable mirror.
"""

from __future__ import annotations

import sys
from pathlib import Path

from datasets import load_dataset

# The primary MVP dataset. See CLAUDE.md — 33,000+ S&P 500 earnings-call
# transcripts, 2005-2025, with speaker-by-speaker `structured_content`.
DATASET_ID = "kurry/sp500_earnings_transcripts"

# Where the pipeline expects to find the on-disk copy.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = DATA_DIR / "kurry_transcripts"


def main() -> int:
    print(f"Downloading '{DATASET_ID}' from the HuggingFace Hub...")
    print("(This is a few hundred MB and may take a while.)\n")

    # The dataset publishes a single split; load everything.
    dataset = load_dataset(DATASET_ID)

    print("Loaded splits:")
    for split_name, split in dataset.items():
        print(f"  - {split_name}: {split.num_rows:,} rows")

    OUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving to {OUT_DIR} ...")
    dataset.save_to_disk(str(OUT_DIR))
    print("Done. You can now run: python ingest/explore_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

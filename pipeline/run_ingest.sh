#!/usr/bin/env bash
#
# Phase 1, Step 6 — run the full Subtext ingestion pipeline.
#
# Builds ./data/subtext.duckdb from the kurry earnings-call transcripts:
#   Step 2  build_schema.py       create the DuckDB tables
#   Step 3  load_transcripts.py   parse, classify speakers/sections, load
#   Step 4  compute_sentiment.py  Loughran-McDonald sentiment per utterance
#   Step 5  build_indices.py      BM25 full-text index over utterances
#
# Prerequisites (see README.md):
#   - ./data/kurry_transcripts/  (saved via pipeline/download_data.py)
#   - a Loughran-McDonald Master Dictionary CSV under ./data/ (or $LM_DICT)
#   - dependencies installed with `uv sync` (from pipeline/)
#
# Usage:
#   ./pipeline/run_ingest.sh
#   RUN_EXPLORE=1 ./pipeline/run_ingest.sh   # also run the Step 1 exploration
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Prefer the project virtualenv (`uv sync` creates pipeline/.venv), then a
# repo-root .venv, then whatever python is on PATH.
if [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
  PY="${SCRIPT_DIR}/.venv/bin/python"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PY="${REPO_ROOT}/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi
echo "Using Python: ${PY}"

if [[ ! -d "${REPO_ROOT}/data/kurry_transcripts" ]]; then
  echo "ERROR: ./data/kurry_transcripts not found." >&2
  echo "Run: ${PY} pipeline/download_data.py   (needs HuggingFace access)" >&2
  exit 2
fi

step() { echo; echo "==================== $1 ===================="; }

if [[ "${RUN_EXPLORE:-0}" == "1" ]]; then
  step "Step 1: explore_data.py"
  "${PY}" pipeline/explore_data.py
fi

step "Step 2: build_schema.py"
"${PY}" pipeline/build_schema.py

step "Step 3: load_transcripts.py"
"${PY}" pipeline/load_transcripts.py

step "Step 3b: load_glopardo.py (financial metrics + sector/CIK)"
"${PY}" pipeline/load_glopardo.py

# LOAD_ONLY=1 stops here — schema + classification only, skipping the slow
# sentiment scoring and FTS index. Handy while iterating on classification.
if [[ "${LOAD_ONLY:-0}" == "1" ]]; then
  echo
  echo "==================== LOAD_ONLY: stopping after Step 3 ===================="
  echo "Skipped sentiment + FTS. Run without LOAD_ONLY to complete the build."
  exit 0
fi

step "Step 4: compute_sentiment.py"
"${PY}" pipeline/compute_sentiment.py

step "Step 5: build_indices.py"
"${PY}" pipeline/build_indices.py

echo
echo "==================== DONE ===================="
echo "Built: ${REPO_ROOT}/data/subtext.duckdb"

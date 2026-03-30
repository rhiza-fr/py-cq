#!/usr/bin/env bash
# Build the image, record the demo, and convert to GIF.
# Output: demo/output/demo.cast, demo/output/demo.gif
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$SCRIPT_DIR/output"

docker build -t cq-demo "$SCRIPT_DIR"

# Use Windows-style host path so Docker Desktop accepts it;
# MSYS_NO_PATHCONV=1 prevents Git Bash from translating /output (container path).
HOST_OUTPUT="$(cd "$SCRIPT_DIR/output" && pwd -W 2>/dev/null || pwd)"

MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$HOST_OUTPUT:/output" \
  cq-demo \
  asciinema rec /output/demo.cast \
    --command "bash /demo.sh" \
    --title "cq: LLM-assisted code quality" \
    --cols 110 \
    --rows 30 \
    --overwrite

MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$HOST_OUTPUT:/output" \
  cq-demo \
  agg /output/demo.cast /output/demo.gif

echo ""
echo "Saved: demo/output/demo.cast"
echo "Saved: demo/output/demo.gif"

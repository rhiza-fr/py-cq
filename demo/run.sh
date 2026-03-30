#!/usr/bin/env bash
# Build the image and record the demo.
# Output: demo/output/demo.cast
#
# To upload:  asciinema upload demo/output/demo.cast
# To convert to GIF: docker run --rm -v "$(pwd):/data" asciinema/agg \
#     /data/demo/output/demo.cast /data/demo/output/demo.gif
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$SCRIPT_DIR/output"

docker build -t cq-demo "$SCRIPT_DIR"

docker run --rm \
  -v "$SCRIPT_DIR/output:/output" \
  cq-demo \
  asciinema rec /output/demo.cast \
    --command "bash /demo.sh" \
    --title "cq: LLM-assisted code quality" \
    --cols 110 \
    --rows 30 \
    --overwrite

echo ""
echo "Saved: demo/output/demo.cast"
echo "Upload: asciinema upload demo/output/demo.cast"

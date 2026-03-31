#!/usr/bin/env bash
source /demo-magic.sh

NO_WAIT=true
TYPE_SPEED=80

# Green prompt, no extra newline after commands
DEMO_PROMPT="${GREEN}❯ ${COLOR_RESET}"

stty cols 110 rows 30 2>/dev/null || true
clear

sleep 0.5

# ── Install ───────────────────────────────────────────────────────────────────

uv tool uninstall python-code-quality 2>/dev/null || true
pe "uv tool install python-code-quality"
sleep 1.5
pei "cq --version"
sleep 1.5

# ── Navigate to project ───────────────────────────────────────────────────────

pe "cd ~/demo-project"
sleep 0.5

# ── LLM output: top defect ────────────────────────────────────────────────────

pei "cq check . -o llm"
sleep 8

# ── Table: full overview ──────────────────────────────────────────────────────

pei "cq check ."
sleep 8

# ── JSON output:  ──────────────────────────────────────────────────────

pei "cq check . --only interrogate -o json"
sleep 8




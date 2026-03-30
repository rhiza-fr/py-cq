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

p "uv tool install python-code-quality"
sleep 0.3
cat <<'EOF'
Resolved 67 packages in 218ms
Installed 22 packages in 2.1s
 + bandit==1.8.3
 + coverage==7.8.2
 + diskcache==5.6.3
 + interrogate==1.7.0
 + python-code-quality==0.1.13
 + pytest==8.4.0
 + radon==6.0.1
 + rich==14.0.0
 + ruff==0.14.1
 + typer==0.16.0
 + vulture==2.14
EOF
sleep 1.5

# ── Navigate to project ───────────────────────────────────────────────────────

pe "cd ~/demo-project"
sleep 0.5

# ── LLM output: top defect ────────────────────────────────────────────────────

pei "cq check . -o llm"
sleep 3

# ── Table: full overview ──────────────────────────────────────────────────────

pei "cq check ."
sleep 4

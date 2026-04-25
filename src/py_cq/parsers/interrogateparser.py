"""Parses output from interrogate into a standardized ToolResult.

Interrogate is invoked with ``-v --fail-under 0``, producing a table of
per-file docstring coverage on stdout::

    | src/foo.py  |  5 |  2 |  3 |  60% |
    | TOTAL       |  5 |  2 |  3 |  60.0% |

The parser extracts per-file coverage and the TOTAL row, storing the TOTAL
as the ``doc_coverage`` metric (0.0–1.0).
"""

import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult

_ROW_RE = re.compile(r"^\|\s+(.+?)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+\d+\s+\|\s+(\d+(?:\.\d+)?)%\s*\|")


class InterrogateParser(AbstractParser):
    """Parses raw output from ``interrogate -v`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        files: dict[str, dict] = {}
        total_coverage: float | None = None
        for line in (raw_result.stdout or "").splitlines():
            m = _ROW_RE.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            total = int(m.group(2))
            miss = int(m.group(3))
            cover = float(m.group(4))
            if name == "TOTAL":
                total_coverage = cover / 100.0
            elif total > 0:
                files[name.replace("\\", "/")] = {
                    "total": total,
                    "missing": miss,
                    "coverage": cover / 100.0,
                }
        score = total_coverage if total_coverage is not None else 1.0
        return ToolResult(raw=raw_result, metrics={"doc_coverage": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15) -> str:
        score = tr.metrics.get("doc_coverage", 0)
        uncovered = sorted(
            [(f, d) for f, d in tr.details.items() if isinstance(d, dict) and d.get("missing", 0) > 0],
            key=lambda x: x[1].get("coverage", 0.0),
        )[:5]
        if not uncovered:
            return f"**doc_coverage** score: {score:.3f}"
        lines = [f"**doc coverage** {score:.1%} — files with most missing docstrings:"]
        for path, data in uncovered:
            miss = data.get("missing", 0)
            pct = data.get("coverage", 0.0)
            lines.append(f"- `{path}`: {pct:.0%} ({miss} undocumented)")
        return "\n".join(lines)

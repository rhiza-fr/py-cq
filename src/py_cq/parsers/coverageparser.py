"""Parses raw coverage tool output into a standardized `ToolResult` for consistent analysis across different coverage utilities.
The module defines `CoverageParser`, a concrete implementation of `AbstractParser`, which extracts overall and per-file coverage metrics from a `RawResult` object and normalises the data format for downstream processing."""

import logging

from py_cq.localtypes import AbstractParser, RawResult, ToolResult

log = logging.getLogger("cq")


class CoverageParser(AbstractParser):
    """Parses raw coverage output into structured ToolResult instances.
    Extends AbstractParser, extracting overall coverage percentages, per-file coverage values, normalising file paths, and preserving the tool's return code."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse raw coverage output into a :class:`ToolResult`.

        Given a :class:`RawResult` containing the stdout of a coverage tool, the
        method extracts every line that ends with a percent sign.  Each such line
        is expected to follow the format::

            <file> <total_lines> <covered_lines> <coverage>%

        The coverage percentage is converted to a fraction (e.g. 90\u202f% → 0.9) and
        stored in ``metrics['coverage']`` for the overall ``TOTAL`` line, while
        the per-file values are placed in ``details`` with the file path
        normalised to use forward slashes.  The tool's return code is added to
        ``details`` under the key ``'return_code'``.

        Args:
            raw_result (RawResult): The raw output from a coverage tool.

        Returns:
            ToolResult: A structured result containing the overall coverage
            metric, per-file coverage percentages, and the tool's return code.

        Example:
            >>> parser = CoverageParser()
            >>> raw = RawResult(
            ...     stdout='src/main.py 100 90 90%\\\\nTOTAL 200 180 90%',
            ...     return_code=0)
            >>> result = parser.parse(raw)
            >>> result.metrics['coverage']
            0.9
            >>> result.details['src/main.py']
            0.9"""
        tr = ToolResult(raw=raw_result)
        lines = raw_result.stdout.splitlines()
        coverage_lines = [line for line in lines if line.endswith("%")]
        details = {}
        for line in coverage_lines:
            parts = line.split()
            if len(parts) >= 2:
                file_name = parts[0]
                try:
                    coverage_percentage = float(parts[-1].rstrip('%')) / 100.0
                except ValueError:
                    log.warning("Error parsing coverage percentage from line: %s", line)
                    continue
                if file_name == "TOTAL":
                    tr.metrics["coverage"] = coverage_percentage
                else:
                    try:
                        missing = int(parts[2]) if len(parts) >= 4 else None
                    except (ValueError, IndexError):
                        missing = None
                    details[file_name.replace("\\", "/")] = {
                        "coverage": coverage_percentage,
                        "missing": missing,
                    }
        tr.details = details
        return tr

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        """Return the files with lowest coverage as a defect description."""
        score = tr.metrics.get("coverage", 0)
        uncovered = sorted(
            [(f, d) for f, d in tr.details.items() if isinstance(d, dict) and d.get("missing")],
            key=lambda x: x[1].get("coverage", 0.0),
        )[:5]
        if not uncovered:
            return f"**coverage** score: {score:.3f}"
        lines = [f"**coverage** score: {score:.3f} — files with lowest coverage:"]
        for path, data in uncovered:
            pct = data.get("coverage", 0.0)
            miss = data.get("missing", 0)
            lines.append(f"- `{path}`: {pct:.0%} ({miss} uncovered statements)")
        return "\n".join(lines)

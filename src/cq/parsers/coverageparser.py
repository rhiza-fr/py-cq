'''"""Parses raw coverage tool output into a standardized `ToolResult` for consistent analysis across different coverage utilities.
The module defines `CoverageParser`, a concrete implementation of `AbstractParser`, which extracts overall and per-file coverage metrics from a `RawResult` object and normalises the data format for downstream processing.'''

from cq.localtypes import AbstractParser, RawResult, ToolResult


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
        normalised to use forward slashes.  The tool’s return code is added to
        ``details`` under the key ``'return_code'``.

        Args:
            raw_result (RawResult): The raw output from a coverage tool.

        Returns:
            ToolResult: A structured result containing the overall coverage
            metric, per-file coverage percentages, and the tool’s return code.

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
        # Simplified parsing - replace with actual logic
        tr = ToolResult(raw=raw_result)
        tr.metrics["coverage"] = 0.0
        # data\problems\travelling_salesman\ts_good.py      37     26    30%
        # TOTAL                                             37     26    30%
        lines = raw_result.stdout.splitlines()
        coverage_lines = [line for line in lines if line.endswith("%")]
        # print(f"Coverage lines found: {coverage_lines}")
        details = {}
        for line in coverage_lines:
            parts = line.split()
            if len(parts) == 4:
                file_name = parts[0]
                try:
                    coverage_percentage = float(parts[2]) / 100.0
                except ValueError:
                    print(f"Error parsing coverage percentage from line: {line}")
                    coverage_percentage = 0.0
                if file_name == "TOTAL":
                    tr.metrics["coverage"] = coverage_percentage
                else:
                    details[file_name.replace("\\", "/")] = coverage_percentage
        tr.details = details
        tr.details["return_code"] = raw_result.return_code
        return tr

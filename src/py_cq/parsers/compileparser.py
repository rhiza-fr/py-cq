"""This module defines the :class:`CompileParser`, a concrete subclass of
:class:`AbstractParser`.  The parser translates raw compiler output into a
structured :class:`ToolResult`, extracting diagnostics, computing a
compile score, and providing concise help messages for any failures."""

import logging

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import format_source_context, score_logistic_variant

log = logging.getLogger("cq")


class CompileParser(AbstractParser):
    """Parses raw compiler output into a structured ToolResult.

    The `CompileParser` implements the `AbstractParser` interface, converting
    `RawResult` objects into `ToolResult` instances that include diagnostics,
    metrics, and a mapping of failed files. It also supplies a human-readable
    help string summarizing any compilation errors for a given `ToolResult`."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses compiler output into a structured ``ToolResult``.

        The method scans the ``stdout`` of a ``RawResult`` object for compilation
        events and error messages. For each file that emits an error, it extracts
        the line number, source snippet, error type, and help text, normalizes the
        file path, and stores this information in a dictionary keyed by file path.
        It then computes a failure ratio (failed files / total compilations) and
        derives a compile score via ``score_logistic_variant``.  The original
        ``stdout`` is cleaned of ``Listing`` lines and back-slash path separators
        are replaced with forward slashes.  A ``ToolResult`` containing the raw
        result, a compile metric, and, if any, a mapping of failed files is
        returned.

        Args:
            raw_result (RawResult): Raw compiler output, typically containing a
                ``stdout`` attribute.

        Returns:
            ToolResult: A structured result containing diagnostics, a compile
                metric, and a mapping of failed files (if any).

        Example:
            >>> parser = CompileParser()
            >>> raw = RawResult(stdout=(
            ...     'Compiling a.c\\\\n'
            ...     '***   File "a.c" line 10, column 5:\\\\n'
            ...     '    error: unknown type name \\\\'foo\\\\'\\\\n'
            ...     '\\\\n'))
            >>> result = parser.parse(raw)
            >>> result.metrics['compile']
            0.5
            >>> result.details['failed_files']['a.c']['type']
            'error'"""

        compilations = 0
        failed_files: dict[str, dict] = {}
        current_error = None
        # Process stdout first for successful compilations
        if raw_result.stdout:
            for line in raw_result.stdout.splitlines():
                if line.startswith("Compiling "):
                    compilations += 1
                elif line.startswith("***   File "):
                    # This indicates a compilation error
                    parts = line.split('"')
                    if len(parts) < 2:
                        continue
                    file_path = parts[1]
                    current_error = {"file": file_path, "error": line}
                elif current_error and line.strip():
                    # Append additional error context
                    current_error["error"] += "\n" + line
                elif line.startswith("Listing "):
                    # Skip directory listings
                    continue
                elif current_error and (not line.strip()):
                    # Empty line ends the error block
                    # Parse error details from the error block
                    error_lines = current_error["error"].splitlines()
                    log.debug("Compile error lines: %s", error_lines)
                    error_info = {}
                    # Extract line number if present
                    if "line " in error_lines[0]:
                        try:
                            error_info["line"] = int(
                                error_lines[0].split("line ")[1].split(",")[0]
                            )
                        except ValueError:
                            pass
                    # Get source code context if available
                    if len(error_lines) > 1:
                        error_info["src"] = error_lines[1].strip()
                    if len(error_lines) > 3:
                        if "Error:" in error_lines[3]:
                            error_parts = error_lines[3].split(":")
                            type_tokens = error_parts[0].strip().split()
                            error_info["type"] = (
                                type_tokens[-1] if type_tokens else "Unknown"
                            )  # Gets "SyntaxError"
                            error_info["help"] = ",".join(
                                error_parts[1:]
                            ).strip()  # Gets help message
                    else:
                        error_info["type"] = "Unknown"
                        error_info["help"] = "\n".join(error_lines[2:]).strip()
                    file_path = current_error["file"].replace("\\", "/")
                    failed_files[file_path] = error_info
                    current_error = None
        failure_ratio = len(failed_files) / compilations if compilations > 0 else 0.0
        score = score_logistic_variant(failure_ratio, scale_factor=0.25)
        raw_result.stdout = "\n".join(
            [
                line.replace("\\\\", "/")
                for line in raw_result.stdout.splitlines()
                if not line.startswith("Listing")
            ]
        )
        tr = ToolResult(raw=raw_result, metrics={"compile": score})
        if failed_files:
            tr.details["failed_files"] = failed_files
        return tr

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        """Return the first compilation failure as a defect description."""
        failed = tr.details.get("failed_files", {})
        if not failed:
            return "Compilation failed (no details available)"
        file, info = next(iter(failed.items()))
        line = info.get("line", "?")
        typ = info.get("type", "Error")
        help_msg = info.get("help", "")
        code_block = format_source_context(file, line, count=context_lines) or (f"\n```python\n{info['src']}\n```" if info.get("src") else "")
        callee = ""
        src_line = info.get("src", "")
        if src_line:
            from py_cq.parsers.common import extract_callee_name, format_callee_context
            func_name = extract_callee_name(src_line)
            if func_name:
                callee = format_callee_context(func_name, file)
        return f"{file}:{line} - {typ}: {help_msg}{code_block}{callee}"

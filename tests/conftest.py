"""Shared test helpers."""

from py_cq.localtypes import RawResult


def raw(stdout="", return_code=0):
    """Returns a RawResult instance."""
    return RawResult(tool_name="test", command="cmd", stdout=stdout, return_code=return_code)

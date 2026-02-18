"""Shared test helpers."""

from cq.localtypes import RawResult


def raw(stdout="", return_code=0):
    return RawResult(tool_name="test", command="cmd", stdout=stdout, return_code=return_code)

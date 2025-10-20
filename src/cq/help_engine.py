"""Utility module for generating user-friendly help text from tool configurations and
execution results.  It exposes the `provide_help` function, which retrieves help
information from a compile-tool configuration when available; otherwise it
returns a default `'No help available.'` message.  This module is used to
display help to end-users or embed help in system responses."""

from cq.localtypes import CombinedToolResults


def provide_help(tool_configs, crt: CombinedToolResults) -> str:
    """Return help text from the compile tool if available; otherwise `No help available.`"""
    # tool_configs[""]
    # print(tool_configs)
    for tr in crt.tool_results:
        if tr.raw.tool_name == "compile":
            parser = tool_configs["compilation"].parser_class()
            return parser.provide_help(tr)
    return "No help available."

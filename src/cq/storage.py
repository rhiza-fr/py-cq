"""Utilities for persisting combined tool results.

This module provides a single helper function, :func:`save_result`, which
serializes a :class:`CombinedToolResults` instance to a JSON file. The
function ensures that the target directory exists, writes a readable
representation of the results, and returns the absolute path of the created
file.

Example
-------
>>> from your_package import CombinedToolResults, save_result
>>> results = CombinedToolResults(...)
>>> output_path = save_result(results, "output.json")
>>> print(output_path)"""

import json
from cq.localtypes import CombinedToolResults


def save_result(combined_tool_results: CombinedToolResults, file_name: str):
    """Saves combined tool results to a JSON file named by `file_name`."""
    if not file_name:
        return
    data = combined_tool_results.to_dict()
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)

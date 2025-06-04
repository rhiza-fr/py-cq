import json

from codeoptim.localtypes import CombinedToolResults


def save_result(combined_tool_results: CombinedToolResults, file_name: str):
    if not file_name:
        return
    data = combined_tool_results.to_dict()
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)

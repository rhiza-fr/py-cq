import logging
import subprocess
import time
from pathlib import Path

from cachier import cachier

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from codeoptim.localtypes import RawResult, ToolConfig, ToolResult

log = logging.getLogger("codeoptim")


def get_hash(args, kwargs):
    p = Path(kwargs["context_path"]).resolve()
    t = p.stat().st_mtime
    return f"{kwargs['tool_config'].command.format(context_path=str(p))}:{t}"


@cachier(hash_func=get_hash)
def run_tool(tool_config: ToolConfig, context_path: str) -> RawResult:
    # get_hash(tool_config.command, context_path=context_path)
    command = tool_config.command.format(context_path=context_path)
    log.info(f"Running: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return RawResult(
        tool_name=tool_config.name,
        command=command,
        stdout=result.stdout,
        stderr=result.stderr,
        return_code=result.returncode,
        timestamp=timestamp,
    )


def run_tools(tool_configs, path: str, parallel: bool = False) -> List[ToolResult]:
    """Run multiple tools and return their parsed results."""
    tool_results = []

    if parallel:
        with ThreadPoolExecutor(max_workers=min(4, len(tool_configs))) as executor:
            future_to_tool = {
                executor.submit(run_tool, tool_config, path): tool_config
                for tool_config in tool_configs
            }
            
            for future in as_completed(future_to_tool):
                tool_config = future_to_tool[future]
                try:
                    raw_result = future.result()
                    parser = tool_config.parser_class()
                    tr = parser.parse(raw_result)
                    tool_results.append(tr)
                except Exception as exc:
                    log.error(f"{tool_config.name} generated an exception: {exc}")
    else:
        for tool_config in tool_configs:
            raw_result = run_tool(tool_config, path)
            parser = tool_config.parser_class()
            tr = parser.parse(raw_result)
            tool_results.append(tr)

    return tool_results

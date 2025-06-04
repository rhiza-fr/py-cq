import logging
import subprocess
import time
from pathlib import Path

from cachier import cachier

from codeoptim.localtypes import RawResult, ToolConfig

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

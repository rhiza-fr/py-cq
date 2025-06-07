
from cq.localtypes import CombinedToolResults


def provide_help(tool_configs, crt: CombinedToolResults) -> str:
    #tool_configs[""]
    #print(tool_configs)
    for tr in crt.tool_results:
        if tr.raw.tool_name == "compile":
            parser = tool_configs["compilation"].parser_class()
            return parser.provide_help(tr)





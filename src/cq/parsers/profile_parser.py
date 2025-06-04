import json
import pstats

from cq.localtypes import AbstractParser, RawResult, ToolResult


class ProfileParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        tr = ToolResult(raw=raw_result, metrics={"profile": 1})

        p = pstats.Stats("profile.prof")  # THIS WILL FAIL IF CACHING IS ENABLED
        s = p.strip_dirs().sort_stats("cumulative")  # Show top 20 by cumulative time
        s.calc_callees()
        tr.details = self.pstats_to_dict(s, filter="ts_good.py")  # FIXME
        return tr

    def format_func_tuple(self, func_tuple):
        """Converts ('filename.py', 10, 'my_func') to 'filename.py:10(my_func)'"""
        if not func_tuple:
            return "None"
        # Handle special case for built-in functions represented by pstats
        if len(func_tuple) == 3 and func_tuple[0] == "~" and func_tuple[1] == 0:
            return f"built-in function {func_tuple[2]}"  # e.g. built-in function len
        if len(func_tuple) == 3:  # Standard (filename, lineno, funcname)
            return f"{func_tuple[0]}:{func_tuple[1]}({func_tuple[2]})"
        # Could be other formats, e.g. for C extensions. Provide a generic fallback.
        return str(func_tuple)

    def pstats_to_dict(self, stats_obj, top_n=100, filter=""):
        """
        Converts a pstats.Stats object to a JSON-serializable dictionary.
        Assumes sort_stats() has been called if a specific order is desired in the 'functions' list.
        """
        result = {
            "summary": {
                "total_calls": stats_obj.total_calls,  # Total primitive calls
                "total_tt": stats_obj.total_tt,  # Total time spent in all functions (sum of tottime)
                # Note: pstats doesn't directly store a "total cumulative time" for the whole program in one variable,
                # as the entry point's cumulative time usually serves this purpose.
            },
            "functions": [],
        }

        # stats_obj.fcn_list contains the function keys in the order determined by the last sort_stats() call
        # If sort_stats() hasn't been called, it's in an arbitrary order.
        # If no sort_stats applied, fcn_list might be None or empty. Fallback to .stats.keys()
        function_keys_to_iterate = stats_obj.fcn_list
        if not function_keys_to_iterate:
            function_keys_to_iterate = stats_obj.stats.keys()

        for func_tuple in function_keys_to_iterate:
            # func_tuple is (filename, line_number, function_name)
            # stats_data is (cc, nc, tt, ct, callers_dict)
            stats_data = stats_obj.stats[func_tuple]

            # Process callers
            callers_info = []
            # stats_data[4] is the callers_dict
            # It's {caller_func_tuple: (cc, nc, tt, ct_for_this_call_path)}
            for caller_func_tuple, caller_stats in stats_data[4].items():
                callers_info.append(
                    {
                        "caller": self.format_func_tuple(caller_func_tuple),
                        "primitive_calls_from_caller": caller_stats[0],  # cc
                        "total_calls_from_caller": caller_stats[1],  # nc
                        "time_in_callee_from_this_caller": caller_stats[
                            2
                        ],  # tt (time in callee when called by this)
                        "cumulative_time_in_callee_from_this_caller": caller_stats[
                            3
                        ],  # ct (cumulative time in callee when called by this)
                    }
                )

            # Process callees (functions called by this function)
            # pstats.Stats has a helper for this: get_callees(func_tuple)
            # It returns a dict {callee_func_tuple: (cc, nc, tt, ct)}
            callees_info = []
            # if hasattr(stats_obj, 'get_callees'): # Check if method exists
            callees_data = stats_obj.all_callees[func_tuple]
            # print(len(callees_data), f"for {func_tuple}")
            for callee_func_tuple, callee_stats in callees_data.items():
                callees_info.append(
                    {
                        "callee": self.format_func_tuple(callee_func_tuple),
                        "primitive_calls_to_callee": callee_stats[0],
                        "total_calls_to_callee": callee_stats[1],
                        "time_in_callee": callee_stats[
                            2
                        ],  # This is tt of the callee *for this call path*
                        "cumulative_time_in_callee": callee_stats[
                            3
                        ],  # This is ct of the callee *for this call path*
                    }
                )

            func_entry = {
                "function_name_long": self.format_func_tuple(func_tuple),
                "filename": func_tuple[0],
                "lineno": func_tuple[1],
                "function_name_short": func_tuple[2],
                "primitive_calls": stats_data[0],  # cc
                "total_calls": stats_data[1],  # nc
                "total_time_exclusive": stats_data[2],  # tt (time in this func only)
                "cumulative_time_inclusive": stats_data[3],  # ct (time in this func + sub-calls)
                "callers": callers_info,
                "callees": callees_info,  # Added callees
            }
            if not filter:
                result["functions"].append(func_entry)  # type: ignore
            elif filter in func_entry["function_name_long"]:
                result["functions"].append(func_entry)  # type: ignore

        return result

    def pstats_to_json(self, stats_obj, indent=2):
        """
        Converts a pstats.Stats object to a JSON string.
        """
        dict_data = self.pstats_to_dict(stats_obj)
        return json.dumps(dict_data, indent=indent)

'''"""
This module defines **ProfileParser**, a concrete implementation of
`AbstractParser` that transforms profiling output (e.g., from
`cProfile`/`pstats`) into a structured `ToolResult`.
It provides helper methods to format function signatures, convert a
`pstats.Stats` instance into a JSON-serialisable dictionary, and serialize
that dictionary to JSON.  The parser removes file-path prefixes,
sorts functions by cumulative time, and filters results to the
functions defined in the user's source code.  It is intended for use
within a profiling-tooling pipeline that expects `AbstractParser`
instances.'''

import json
import pstats

from cq.localtypes import AbstractParser, RawResult, ToolResult


class ProfileParser(AbstractParser):
    """Parses profiling data and produces structured output for the profiling tool pipeline.

    The :class:`ProfileParser` accepts raw profiling results (for example, a
    ``pstats.Stats`` object) and converts them into JSON-serializable dictionaries
    or JSON strings. It provides helper methods for formatting function signatures
    and for extracting the top\u202fN most-called functions. The class implements the
    ``parse`` method from :class:`AbstractParser`, enabling seamless use within
    the tool's pipeline."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses profiling data from ``profile.prof`` and wraps it in a
        :class:`ToolResult` for the tool pipeline.

        The method performs the following steps:

        1. Loads the profiling statistics from the file ``profile.prof`` using
           :mod:`pstats`.
        2. Strips directory information from the function paths.
        3. Sorts the functions by cumulative time and calculates callee
           statistics.
        4. Converts the processed statistics into a JSON-serialisable dictionary,
           keeping only functions defined in ``ts_good.py``.
        5. Packages the result together with the original *raw_result* and a
           metrics dictionary indicating a single profiling metric.

        Args:
            raw_result (RawResult): The raw profiling output to be wrapped in
                the result. The current implementation does not use this value
                directly but retains it for API compatibility.

        Returns:
            ToolResult: A tool result containing the original raw result, a
            metrics mapping, and a ``details`` field with the processed
            profiling data.

        Raises:
            FileNotFoundError: If ``profile.prof`` does not exist.
            OSError: If the profiling file cannot be read."""
        tr = ToolResult(raw=raw_result, metrics={"profile": 1})
        p = pstats.Stats("profile.prof")  # THIS WILL FAIL IF CACHING IS ENABLED
        s = p.strip_dirs().sort_stats("cumulative")  # Show top 20 by cumulative time
        s.calc_callees()
        tr.details = self.pstats_to_dict(s, filter="ts_good.py")  # FIXME
        return tr

    def format_func_tuple(self, func_tuple):
        """Formats a function tuple into a readable string representation for profiling output."""
        if not func_tuple:
            return "None"
        # Handle special case for built-in functions represented by pstats
        if len(func_tuple) == 3 and func_tuple[0] == "~" and (func_tuple[1] == 0):
            return f"built-in function {func_tuple[2]}"  # e.g. built-in function len
        if len(func_tuple) == 3:  # Standard (filename, lineno, funcname)
            return f"{func_tuple[0]}:{func_tuple[1]}({func_tuple[2]})"
        # Could be other formats, e.g. for C extensions. Provide a generic fallback.
        return str(func_tuple)

    def pstats_to_dict(self, stats_obj, top_n=100, filter=""):
        """Converts a :class:`pstats.Stats` object into a JSON-serialisable dictionary.

        The resulting dictionary contains a summary of the total calls and total
        cumulative time as well as a list of function entries.  Each function entry
        stores the function's qualified name, file name, line number, and various
        performance counters such as primitive calls, total calls, exclusive time,
        and inclusive cumulative time.  Additionally, the entry lists callers and
        callees with detailed statistics about the interactions between functions.

        Args:
            stats_obj (pstats.Stats): The profiling statistics to convert.
            top_n (int, optional): Reserved for future use; currently all functions
                are processed.
            filter (str, optional): If supplied, only functions whose fully
                qualified name contains this string are included in the result.

        Returns:
            dict: A JSON-serialisable mapping with a ``summary`` key and a
                ``functions`` list.  Each item in ``functions`` is a dictionary with
                the keys ``function_name_long``, ``filename``, ``lineno``,
                ``function_name_short``, ``primitive_calls``, ``total_calls``,
                ``total_time_exclusive``, ``cumulative_time_inclusive``, ``callers``,
                and ``callees``."""  # Total primitive calls
        # Total time spent in all functions (sum of tottime)
        # Note: pstats doesn't directly store a "total cumulative time" for the whole program in one variable,
        # as the entry point's cumulative time usually serves this purpose.
        result = {
            "summary": {
                "total_calls": stats_obj.total_calls,
                "total_tt": stats_obj.total_tt,
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
            for caller_func_tuple, caller_stats in stats_data[4].items():  # cc
                # nc
                # tt (time in callee when called by this)
                # ct (cumulative time in callee when called by this)
                callers_info.append(
                    {
                        "caller": self.format_func_tuple(caller_func_tuple),
                        "primitive_calls_from_caller": caller_stats[0],
                        "total_calls_from_caller": caller_stats[1],
                        "time_in_callee_from_this_caller": caller_stats[2],
                        "cumulative_time_in_callee_from_this_caller": caller_stats[3],
                    }
                )
            # Process callees (functions called by this function)
            # pstats.Stats has a helper for this: get_callees(func_tuple)
            # It returns a dict {callee_func_tuple: (cc, nc, tt, ct)}
            callees_info = []
            # if hasattr(stats_obj, 'get_callees'): # Check if method exists
            callees_data = stats_obj.all_callees[func_tuple]
            # print(len(callees_data), f"for {func_tuple}")
            for (
                callee_func_tuple,
                callee_stats,
            ) in callees_data.items():  # This is tt of the callee *for this call path*
                # This is ct of the callee *for this call path*
                callees_info.append(
                    {
                        "callee": self.format_func_tuple(callee_func_tuple),
                        "primitive_calls_to_callee": callee_stats[0],
                        "total_calls_to_callee": callee_stats[1],
                        "time_in_callee": callee_stats[2],
                        "cumulative_time_in_callee": callee_stats[3],
                    }
                )  # cc
            # nc
            # tt (time in this func only)
            # ct (time in this func + sub-calls)
            # Added callees
            func_entry = {
                "function_name_long": self.format_func_tuple(func_tuple),
                "filename": func_tuple[0],
                "lineno": func_tuple[1],
                "function_name_short": func_tuple[2],
                "primitive_calls": stats_data[0],
                "total_calls": stats_data[1],
                "total_time_exclusive": stats_data[2],
                "cumulative_time_inclusive": stats_data[3],
                "callers": callers_info,
                "callees": callees_info,
            }
            if not filter:
                result["functions"].append(func_entry)
            elif filter in func_entry["function_name_long"]:
                result["functions"].append(func_entry)
        return result

    def pstats_to_json(self, stats_obj, indent=2):
        """Converts a pstats.Stats object to a JSON string."""
        dict_data = self.pstats_to_dict(stats_obj)
        return json.dumps(dict_data, indent=indent)

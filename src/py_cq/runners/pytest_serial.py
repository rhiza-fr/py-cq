"""Run pytest in a single process, for the coverage tool.

cq runs this script under ``coverage run``. Coverage only measures the process
it starts, so if the target project enables pytest-xdist through its own
``addopts``, the tests run in worker processes that coverage never sees and the
coverage score collapses. Passing ``-n 0`` keeps the tests in this process. It
is only passed when xdist is installed, because pytest rejects ``-n`` otherwise.

The script runs in the target project's environment, so it imports only the
standard library and pytest. It lives in its own directory because running a
script puts that directory first on ``sys.path``; that entry is replaced with
the working directory so imports behave as they do under ``python -m pytest``.
"""

import os
import sys
from importlib.util import find_spec

if __name__ == "__main__":
    sys.path[0] = os.getcwd()

    import pytest

    args = sys.argv[1:]
    if find_spec("xdist") is not None:
        args += ["-n", "0"]
    sys.exit(pytest.main(args))

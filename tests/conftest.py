"""Shared test helpers."""

from unittest.mock import patch

import pytest
from diskcache import Cache, JSONDisk

from py_cq.localtypes import RawResult


def raw(stdout="", return_code=0):
    """Returns a RawResult instance."""
    return RawResult(
        tool_name="test", command="cmd", stdout=stdout, return_code=return_code
    )


@pytest.fixture(autouse=True, scope="session")
def _isolated_cache(tmp_path_factory):
    """Redirect the shared diskcache to a temp dir for the entire test session.

    Without this, runner.invoke tests write to the real ~/.cache/cq/, which
    races with the outer `cq check D:\\ai\\py-cq` process when the test suite
    is run as part of that project's own cq check.
    """
    cache_dir = tmp_path_factory.mktemp("cq_cache", numbered=False)
    isolated = Cache(str(cache_dir), disk=JSONDisk)
    with (
        patch("py_cq.execution_engine._cache", isolated),
        patch("py_cq.api._cache", isolated),
    ):
        yield isolated

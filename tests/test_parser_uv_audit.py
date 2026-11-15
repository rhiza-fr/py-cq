"""Tests for UvAuditParser."""

import json

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.uvauditparser import UvAuditParser


def _vuln(name, vuln_id, aliases=(), fix_versions=("2.0.0",)):
    return {
        "dependency": {"name": name, "version": "1.0.0"},
        "id": vuln_id,
        "aliases": list(aliases),
        "summary": f"{name} is unsafe",
        "link": f"https://example.test/{vuln_id}",
        "fix_versions": list(fix_versions),
    }


def _report(*vulns):
    return json.dumps({"vulnerabilities": list(vulns)})


def test_uv_audit_parse_clean():
    """No vulnerabilities scores 1.0 with no details."""
    tr = UvAuditParser().parse(raw(_report()))
    assert tr.metrics == {"dependencies": 1.0}
    assert tr.details == {}


def test_uv_audit_parse_vulnerability():
    """A fixable vulnerability lowers the score and is listed against uv.lock."""
    tr = UvAuditParser().parse(raw(_report(_vuln("foo", "GHSA-1")), return_code=1))
    assert tr.metrics["dependencies"] < 1.0
    assert tr.details == {
        "uv.lock": [
            {
                "code": "GHSA-1",
                "package": "foo",
                "version": "1.0.0",
                "fix_versions": ["2.0.0"],
                "message": "foo is unsafe",
                "link": "https://example.test/GHSA-1",
            }
        ]
    }


def test_uv_audit_skips_vulnerabilities_without_a_fix():
    """An advisory with no fix version cannot be resolved by upgrading."""
    tr = UvAuditParser().parse(
        raw(_report(_vuln("foo", "GHSA-1", fix_versions=())), return_code=1)
    )
    assert tr.metrics == {"dependencies": 1.0}
    assert tr.details == {}


def test_uv_audit_dedupes_aliased_advisories():
    """The same vulnerability reported by two databases counts once."""
    tr = UvAuditParser().parse(
        raw(
            _report(
                _vuln("foo", "GHSA-1", aliases=["CVE-1", "PYSEC-1"]),
                _vuln("foo", "PYSEC-1", aliases=["CVE-1", "GHSA-1"]),
                _vuln("bar", "GHSA-2"),
            ),
            return_code=1,
        )
    )
    assert [i["code"] for i in tr.details["uv.lock"]] == ["GHSA-1", "GHSA-2"]


def test_uv_audit_more_vulnerabilities_lower_score():
    one = UvAuditParser().parse(raw(_report(_vuln("foo", "GHSA-1"))))
    two = UvAuditParser().parse(
        raw(_report(_vuln("foo", "GHSA-1"), _vuln("bar", "GHSA-2")))
    )
    assert two.metrics["dependencies"] < one.metrics["dependencies"]


def test_uv_audit_no_report_gives_no_metric():
    """A failed audit (no uv, no lockfile, offline) is skipped, not failed."""
    result = RawResult(
        tool_name="uv-audit",
        stdout="",
        stderr="warning: experimental\nerror: No `pyproject.toml` found",
        return_code=2,
    )
    tr = UvAuditParser().parse(result)
    assert tr.metrics == {}
    assert tr.details == {}


def test_uv_audit_unexpected_json_gives_no_metric():
    assert UvAuditParser().parse(raw("[]")).metrics == {}
    assert UvAuditParser().parse(raw("{}")).metrics == {}


def test_uv_audit_format_llm_with_issue():
    tr = UvAuditParser().parse(raw(_report(_vuln("foo", "GHSA-1")), return_code=1))
    msg = UvAuditParser().format_llm_message(tr)
    assert "uv.lock - GHSA-1" in msg
    assert "foo 1.0.0" in msg
    assert "Fixed in 2.0.0" in msg
    assert "uv lock --upgrade-package foo" in msg
    assert "https://example.test/GHSA-1" in msg


def test_uv_audit_format_llm_no_details():
    tr = ToolResult(metrics={"dependencies": 0.5}, details={}, raw=RawResult())
    assert "no details" in UvAuditParser().format_llm_message(tr).lower()

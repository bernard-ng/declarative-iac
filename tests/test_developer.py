from __future__ import annotations

from declarative_iac.domain.developer import runner

CARGO = """
running 3 tests
test result: ok. 3 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.1s
test result: FAILED. 7 passed; 2 failed; 0 ignored; 0 measured; 0 filtered out; finished in 2s
"""

REPORT = """kind            pass  skip  fail
registry          24     3     0
mount@application 20     4     0
mount@compose     20     4     1
FAIL mount@compose delete: something
"""


def test_cargo_totals():
    assert runner.parse_cargo_tests(CARGO) == {
        "binaries": 2,
        "passed": 10,
        "failed": 2,
        "ignored": 1,
        "failed_binaries": 1,
    }


def test_conformance_report_rows_and_totals():
    parsed = runner.parse_conformance_report(REPORT)
    assert parsed["kinds"] == 2
    assert parsed["scenarios"] == {"pass": 64, "skip": 11, "fail": 1}


def test_fingerprint_key_format():
    key = runner.fingerprint_key()
    left, right = key.split(":")
    assert len(left) == 36 and len(right) == 64

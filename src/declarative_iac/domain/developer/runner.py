"""Running the system's own test suites at the pinned commit, and parsing what they report.

These results are *developer evidence* (paper Section 9): they show what the system claims about
itself. They are stored apart from the independent evidence of this harness.
"""

from __future__ import annotations

import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from declarative_iac.core.shell import run

TEST_RESULT = re.compile(
    r"test result: (?P<status>ok|FAILED)\. (?P<passed>\d+) passed; (?P<failed>\d+) failed; "
    r"(?P<ignored>\d+) ignored"
)
REPORT_ROW = re.compile(r"^(?P<kind>[a-z_@]+)\s+(?P<pass>\d+)\s+(?P<skip>\d+)\s+(?P<fail>\d+)$")


def parse_cargo_tests(output: str) -> dict[str, int]:
    """Totals over every `test result:` line cargo prints."""

    totals = {"binaries": 0, "passed": 0, "failed": 0, "ignored": 0, "failed_binaries": 0}
    for match in TEST_RESULT.finditer(output):
        totals["binaries"] += 1
        for key in ("passed", "failed", "ignored"):
            totals[key] += int(match.group(key))
        totals["failed_binaries"] += match.group("status") == "FAILED"
    return totals


def parse_conformance_report(output: str) -> dict[str, Any]:
    """The per-kind table the conformance suite prints (`kind pass skip fail`)."""

    kinds: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        match = REPORT_ROW.match(line.strip())
        if match:
            row = {k: int(match.group(k)) for k in ("pass", "skip", "fail")}
            counts = {"pass": 0, "skip": 0, "fail": 0}  # nosec B105
            previous = kinds.setdefault(match.group("kind"), counts)
            for key, value in row.items():
                previous[key] += value
    return {
        "kinds": len({kind.split("@")[0] for kind in kinds}),
        "rows": dict(sorted(kinds.items())),
        "scenarios": {k: sum(r[k] for r in kinds.values()) for k in ("pass", "skip", "fail")},
    }


@dataclass(frozen=True)
class Step:
    """One command of the system's verification machinery."""

    id: str
    args: tuple[str, ...]
    parse: Callable[[str], dict[str, Any]] | None = None
    env: dict[str, str] = field(default_factory=dict)
    needs_docker: bool = False
    timeout: float = 7200


def cargo_steps(openapi_versions: list[tuple[str, str]]) -> list[Step]:
    steps = [
        Step(
            "workspace-tests",
            ("cargo", "test", "--workspace", "--locked", "--no-fail-fast"),
            parse_cargo_tests,
        ),
        Step(
            "conformance",
            (
                "cargo",
                "test",
                "--locked",
                "-p",
                "dokploy-conformance",
                "--test",
                "conformance",
                "--",
                "--nocapture",
            ),
            parse_conformance_report,
        ),
    ]
    for version, openapi in openapi_versions:
        args = ["cargo", "xtask", "specs", "--check"]
        if openapi != "openapi/dokploy.json":
            args += ["--against", openapi]
        steps.append(Step(f"ledger-{version}", tuple(args)))
    return steps


def live_steps(version: str, image: str) -> list[Step]:
    env = {"DOKPLOY_VERSION": version, "DOKPLOY_IMAGE": image}
    scripts = "scripts/integration"
    return [
        Step(f"live-reset-{version}", (f"{scripts}/reset.sh",), env=env, needs_docker=True),
        Step(f"live-up-{version}", (f"{scripts}/up.sh",), env=env, needs_docker=True),
        Step(
            f"engine-live-{version}",
            (f"{scripts}/test-engine-live.sh",),
            parse_cargo_tests,
            env=env,
            needs_docker=True,
        ),
        Step(f"live-teardown-{version}", (f"{scripts}/reset.sh",), env=env, needs_docker=True),
        Step(
            f"round-trip-live-{version}",
            (f"{scripts}/test-round-trip-live.sh",),
            env=env,
            needs_docker=True,
        ),
    ]


def fingerprint_key() -> str:
    """A fresh headless fingerprint key in the system's format; never recorded."""

    return f"{uuid.uuid4()}:{secrets.token_hex(32)}"


def execute(step: Step, source: Path, log_dir: Path, extra_env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    completed = run(
        step.args, cwd=source, env={**extra_env, **step.env}, check=False, timeout=step.timeout
    )
    duration = round(time.monotonic() - started, 1)
    log = log_dir / f"{step.id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"$ {' '.join(step.args)}\n{completed.stdout}\n--- stderr ---\n{completed.stderr}",
        encoding="utf-8",
    )
    record: dict[str, Any] = {
        "command": list(step.args),
        "exit_code": completed.returncode,
        "passed": completed.ok,
        "duration_seconds": duration,
    }
    if step.parse is not None:
        record["parsed"] = step.parse(completed.stdout + "\n" + completed.stderr)
    return record

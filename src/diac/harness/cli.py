"""Run the SUT CLI as a black box. Exit codes follow ADR 0017:
0 = success / no changes, 1 = error or blocked plan, 2 = applyable plan with changes (--detailed-exitcode).
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    args: list[str]
    code: int
    stdout: str
    stderr: str


@dataclass
class DokployCli:
    binary: Path
    workspace: Path
    env: dict[str, str]

    def run(self, *args: str, timeout: int = 1800) -> Result:
        e = {**os.environ, **self.env}
        p = subprocess.run([str(self.binary), *args], cwd=self.workspace, env=e,
                           capture_output=True, text=True, timeout=timeout)
        return Result(list(args), p.returncode, p.stdout, p.stderr)

    def plan(self) -> Result:
        return self.run("plan", "--json", "--detailed-exitcode")

    def apply(self, deploy: bool = False) -> Result:
        args = ["apply", "--auto-approve"] + (["--deploy"] if deploy else [])
        return self.run(*args)

    def recover(self) -> Result:
        return self.run("recover", "--auto-approve")

    def import_all(self) -> Result:
        return self.run("import", "all")

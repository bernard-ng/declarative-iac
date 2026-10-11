"""Smoke tests: the snapshot resolves, specs load, and harness modules import."""
import importlib

from diac.specs import load_specs, spec_operation_roles
from diac.sut import Snapshot


def test_snapshot_and_specs():
    snap = Snapshot.load("B1")
    specs = load_specs(snap)
    assert len(specs) >= 30
    roles = spec_operation_roles(specs)
    assert "registry.create" in roles


def test_harness_imports():
    for m in ("raw", "proxy", "cli", "scenarios", "oracle", "perturb"):
        importlib.import_module(f"diac.harness.{m}")

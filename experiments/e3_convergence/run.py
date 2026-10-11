import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

"""E3 - Convergence and idempotency matrix (RQ2; H1-H5, H7).

For each scenario x initial condition x repetition:
  1. fresh workspace from the scenario template, fresh Dokploy (SUT reset scripts or a clean volume);
  2. construct the initial condition (empty | engine_partial | brownfield | drifted:<operator>);
  3. loop: apply, then plan --detailed-exitcode, until the plan exit code is 0 or k_max+3 applies;
  4. after convergence: oracle O-raw (independent state check), O-traffic (mutations on the extra
     apply must be 0), O-unmanaged (snapshot diff), plan determinism (3 plans, byte-equal JSON),
     canary leak scan of the workspace and all captured output.

Requires Docker, a Dokploy instance, and a dokploy binary built at the snapshot commit.
Usage: python experiments/e3_convergence/run.py --binary /path/to/dokploy --reps 5
"""
import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from diac.harness.cli import DokployCli
from diac.harness.proxy import CallRecorder, summarize
from diac.harness.scenarios import load_all
from diac.results import output_dir, write_manifest
from diac.sut import Snapshot

HERE = Path(__file__).resolve().parent


def leak_scan(paths: list[Path], texts: list[str], canaries: list[str]) -> list[str]:
    hits = []
    for c in canaries:
        if any(c in t for t in texts):
            hits.append(f"output:{c[:6]}...")
        for root in paths:
            for f in root.rglob("*"):
                if f.is_file() and ".dokploy/secrets" not in str(f):
                    try:
                        if c in f.read_text(errors="ignore"):
                            hits.append(f"{f.relative_to(root)}:{c[:6]}...")
                    except OSError:
                        pass
    return hits


def converge(cli: DokployCli, k_max: int, rec_log: Path) -> dict:
    trace = []
    for k in range(1, k_max + 4):
        t0 = time.time()
        a = cli.apply()
        p = cli.plan()
        calls = summarize(rec_log, since=t0)
        trace.append({"k": k, "apply_code": a.code, "plan_code": p.code, **calls})
        if a.code == 1 and p.code == 1:
            return {"outcome": "error", "k": k, "trace": trace, "stderr_tail": a.stderr[-2000:]}
        if p.code == 0:
            return {"outcome": "converged", "k": k, "trace": trace}
    return {"outcome": "not_converged", "k": None, "trace": trace}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    ap.add_argument("--binary", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--scenario", action="append", help="limit to scenario ids")
    args = ap.parse_args()
    snap = Snapshot.load(args.snapshot)
    out = output_dir("e3_convergence", snap)
    raw_dir = out / "raw"
    upstream = os.environ["DOKPLOY_URL"]

    results = []
    for sc in load_all(HERE / "scenarios"):
        if args.scenario and sc.id not in args.scenario:
            continue
        for condition in sc.conditions:
            for rep in range(1, args.reps + 1):
                run_id = f"{sc.id}__{condition}__r{rep}"
                ws = Path(tempfile.mkdtemp(prefix="diac-"))
                shutil.copytree(sc.workspace, ws, dirs_exist_ok=True)
                log = raw_dir / f"{run_id}.calls.jsonl"
                rec = CallRecorder(upstream=upstream, log_path=log)
                proxied = rec.start()
                cli = DokployCli(Path(args.binary), ws, {**sc.secrets_env, "DOKPLOY_URL": proxied})
                # TODO(E3): construct `condition` (reset instance; engine_partial; brownfield via import;
                # drifted via diac.harness.perturb). Only `empty` is implemented here.
                if condition != "empty":
                    results.append({"run": run_id, "outcome": "skipped", "reason": "condition not implemented"})
                    rec.stop(); continue
                r = converge(cli, sc.k_max, log)
                t0 = time.time(); extra = cli.apply(); idem = summarize(log, since=t0)
                plans = [cli.plan().stdout for _ in range(3)]
                r.update(run=run_id, scenario=sc.id, condition=condition, rep=rep,
                         idempotent_mutations=idem["mutations"], deterministic_plan=len(set(plans)) == 1,
                         leaks=leak_scan([ws], [extra.stdout, extra.stderr, *plans], list(sc.secrets_env.values())))
                results.append(r)
                rec.stop()
                shutil.rmtree(ws, ignore_errors=True)
    (out / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))
    write_manifest(out, "e3_convergence", snap, binary=args.binary, reps=args.reps)


if __name__ == "__main__":
    main()

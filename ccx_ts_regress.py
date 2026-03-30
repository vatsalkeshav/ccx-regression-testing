#!/usr/bin/env python3
"""
CCExtractor regression harness (macOS / cmake+make).

Goals:
- Generate a "baseline" output set once (from master-branch binary).
- Always run the candidate build (new/) and compare:
  1) Subtitle outputs (byte-exact)
  2) Console output (stdout + stderr, byte-exact after normalization)

Artifacts are stored under test-results/.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import List, Optional, Tuple


DEFAULT_ARGS = [
    "--no-progress-bar",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _relpath(p: Path, root: Path) -> str:
    return str(p.relative_to(root)).replace(os.sep, "/")


def _safe_case_id(sample_path: Path) -> str:
    name = sample_path.name
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", "+"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


@dataclasses.dataclass(frozen=True)
class RunResult:
    argv: List[str]
    exit_code: int
    term_signal: Optional[int]
    duration_sec: float


@dataclasses.dataclass(frozen=True)
class CaseDef:
    case_id: str
    sample: Path
    ccx_args: List[str]


def run_capture(
    *,
    argv: List[str],
    cwd: Path,
    env: dict,
    timeout_sec: int,
    stdout_path: Path,
    stderr_path: Path,
) -> RunResult:
    start = time.monotonic()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
        try:
            p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=out_f, stderr=err_f)
            try:
                rc = p.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                try:
                    p.terminate()
                    rc = p.wait(timeout=5)
                except Exception:
                    p.kill()
                    rc = p.wait()
        except FileNotFoundError:
            raise

    dur = time.monotonic() - start
    term_sig = None
    exit_code = int(rc)
    if exit_code < 0:
        term_sig = -exit_code
    return RunResult(argv=argv, exit_code=exit_code, term_signal=term_sig, duration_sec=dur)


def list_samples(samples_dir: Path) -> List[Path]:
    exts = {".ts", ".m2ts", ".ps", ".mpg", ".mpeg", ".mp4", ".mkv"}
    out = []
    for p in samples_dir.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    out.sort(key=lambda x: x.name)
    return out


def load_cases(
    *,
    cases_file: Optional[Path],
    samples_dir: Path,
    extra_args: List[str],
    match_substrings: List[str],
) -> List[CaseDef]:
    if cases_file is None:
        samples = list_samples(samples_dir)
        if match_substrings:
            samples = [s for s in samples if any(n in s.name for n in match_substrings)]
        ccx_args = list(DEFAULT_ARGS) + list(extra_args)
        return [CaseDef(case_id=_safe_case_id(s), sample=s, ccx_args=ccx_args) for s in samples]

    data = json.loads(cases_file.read_text(encoding="utf-8"))
    defaults = data.get("defaults")
    if defaults is None:
        defaults = DEFAULT_ARGS
    if not isinstance(defaults, list) or not all(isinstance(x, str) for x in defaults):
        raise ValueError("cases defaults must be a list of strings")

    cases_in = data.get("cases")
    if not isinstance(cases_in, list) or not cases_in:
        raise ValueError("cases must contain a non-empty 'cases' list")

    out: List[CaseDef] = []
    for item in cases_in:
        if not isinstance(item, dict):
            raise ValueError("each case must be an object")
        sample_s = item.get("sample")
        if not isinstance(sample_s, str) or not sample_s:
            raise ValueError("case.sample must be a non-empty string")
        sample_p = Path(sample_s)
        if not sample_p.is_absolute():
            sample_p = (samples_dir / sample_p).resolve()
        if not sample_p.exists():
            raise FileNotFoundError(str(sample_p))
        extra = item.get("args", [])
        if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
            raise ValueError(f"case.args for {sample_s} must be a list of strings")
        case_id = item.get("id")
        if case_id is None:
            case_id = _safe_case_id(sample_p)
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case.id for {sample_s} must be a non-empty string")

        ccx_args = list(defaults) + list(extra_args) + list(extra)
        out.append(CaseDef(case_id=case_id, sample=sample_p, ccx_args=ccx_args))

    if match_substrings:
        needles = list(match_substrings)
        out = [c for c in out if any(n in c.sample.name or n in c.case_id for n in needles)]

    out.sort(key=lambda c: c.case_id)
    return out


def rm_tree(p: Path) -> None:
    if not p.exists():
        return
    shutil.rmtree(p)


def read_bytes(p: Path) -> bytes:
    return p.read_bytes() if p.exists() else b""


_RE_ANSI_CSI = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")
_RE_ANSI_OSC = re.compile(rb"\x1b\][^\x07]*(\x07|\x1b\\)")


def normalize_console(b: bytes) -> bytes:
    b = _RE_ANSI_OSC.sub(b"", b)
    b = _RE_ANSI_CSI.sub(b"", b)
    b = b.replace(b"\r", b"")

    lines = b.splitlines(keepends=False)
    out_lines: List[bytes] = []
    for ln in lines:
        if b"processing time =" in ln:
            out_lines.append(b"Done, processing time = <redacted>")
        else:
            out_lines.append(ln)
    return b"\n".join(out_lines) + (b"\n" if b.endswith(b"\n") else b"")


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def compare_files(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return _sha256_file(a) == _sha256_file(b)


def collect_dir_files(root: Path) -> List[str]:
    files = []
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if p.is_file():
            files.append(_relpath(p, root))
    files.sort()
    return files


def copy_sub_outputs(work_dir: Path, subs_dir: Path) -> None:
    """Copy all subtitle/caption output files from work dir."""
    subs_dir.mkdir(parents=True, exist_ok=True)
    sub_exts = {".srt", ".ttxt", ".sami", ".smi", ".vtt", ".ass", ".ssa", ".txt", ".bin"}
    for p in work_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in sub_exts:
            shutil.copy2(p, subs_dir / p.name)


def ensure_exe(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(str(p))
    if not os.access(str(p), os.X_OK):
        raise PermissionError(f"Not executable: {p}")


def format_signal(sig: Optional[int]) -> str:
    if sig is None:
        return ""
    try:
        return signal.Signals(sig).name
    except Exception:
        return f"SIG{sig}"


def should_skip_baseline(baseline_dir: Path, manifest_expected: dict) -> bool:
    man_path = baseline_dir / "manifest.json"
    done_path = baseline_dir / ".complete"
    if not (man_path.exists() and done_path.exists()):
        return False
    try:
        got = json.loads(man_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return got == manifest_expected


def build_candidate(repo_dir: Path, *, debug: bool) -> Tuple[bool, str]:
    """Build ccextractor using cmake + make (macOS)."""
    build_dir = repo_dir / "build"
    rm_tree(build_dir)
    build_dir.mkdir(parents=True)

    env = dict(os.environ)
    env.setdefault("CARGO_BUILD_JOBS", "1")
    env.setdefault("RUST_MIN_STACK", "16777216")

    cmake_args = ["cmake", "../src/"]
    if debug:
        cmake_args = ["cmake", "-DCMAKE_BUILD_TYPE=Debug", "../src/"]

    try:
        out = subprocess.check_output(
            cmake_args, cwd=str(build_dir), stderr=subprocess.STDOUT, env=env
        )
        out += subprocess.check_output(
            ["make"], cwd=str(build_dir), stderr=subprocess.STDOUT, env=env
        )
        return True, out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return False, (e.output or b"").decode("utf-8", errors="replace")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Run regression tests comparing baseline (master branch) vs candidate (new/).",
        epilog=textwrap.dedent(
            """\
            Examples:
              python3 ccx_ts_regress.py --samples ~/samples
              python3 ccx_ts_regress.py --force-baseline
              python3 ccx_ts_regress.py --timeout 900 --match myfile.ts
            """
        ),
    )
    ap.add_argument("--samples", default="samples", help="Samples directory (default: samples)")
    ap.add_argument(
        "--cases-file",
        default="",
        help="Optional JSON file defining per-sample args.",
    )
    ap.add_argument(
        "--baseline-bin",
        default="",
        help="Baseline ccextractor binary. If empty, looks for <baseline-repo>/build/ccextractor.",
    )
    ap.add_argument(
        "--baseline-repo",
        default="",
        help="Baseline (master branch) repo dir. Used to locate binary if --baseline-bin not set.",
    )
    ap.add_argument("--candidate-repo", default="", help="Candidate repo dir to build and test.")
    ap.add_argument("--outdir", default="test-results", help="Artifacts directory (default: test-results)")
    ap.add_argument("--timeout", type=int, default=1200, help="Per-sample timeout in seconds (default: 1200)")
    ap.add_argument(
        "--match",
        action="append",
        default=[],
        help="Only run samples whose filename contains this substring (repeatable).",
    )
    ap.add_argument("--debug-build", action="store_true", help="Build candidate with -DCMAKE_BUILD_TYPE=Debug")
    ap.add_argument("--skip-build", action="store_true", help="Skip building candidate (expects build/ccextractor exists)")
    ap.add_argument("--force-baseline", action="store_true", help="Regenerate baseline outputs")
    ap.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra argument to pass to ccextractor (repeatable). Added after defaults.",
    )
    args = ap.parse_args(argv)

    root = Path.cwd()
    samples_dir = (root / args.samples).resolve()

    # Resolve candidate repo.
    if args.candidate_repo:
        candidate_repo = Path(args.candidate_repo).expanduser().resolve()
    else:
        # Default: look for new/ccextractor relative to cwd.
        candidate_repo = (root / "new" / "ccextractor").resolve()
        if not candidate_repo.exists():
            print(f"ERROR: candidate repo not found at {candidate_repo}", file=sys.stderr)
            print("  Use --candidate-repo to specify.", file=sys.stderr)
            return 2

    # Resolve baseline binary.
    if args.baseline_bin:
        baseline_bin = Path(args.baseline_bin).expanduser().resolve()
    elif args.baseline_repo:
        baseline_bin = Path(args.baseline_repo).expanduser().resolve() / "build" / "ccextractor"
    else:
        # Default: look for master branch build.
        baseline_bin = (root / "master" / "ccextractor" / "build" / "ccextractor").resolve()

    cases_file: Optional[Path]
    if args.cases_file:
        cases_file = (root / args.cases_file).resolve()
    else:
        default_cases = root / "scripts" / "ts_cases.json"
        cases_file = default_cases.resolve() if default_cases.exists() else None

    outdir = (root / args.outdir).resolve()
    baseline_dir = outdir / "baseline"
    candidate_dir = outdir / "candidate"
    report_dir = outdir / "report"

    try:
        cases = load_cases(
            cases_file=cases_file,
            samples_dir=samples_dir,
            extra_args=list(args.extra_arg),
            match_substrings=list(args.match),
        )
    except Exception as e:
        print(f"ERROR: failed to load cases: {e}", file=sys.stderr)
        return 2

    if not cases:
        print(f"ERROR: No samples found in {samples_dir}", file=sys.stderr)
        return 2

    # Stabilize environment.
    base_env = dict(os.environ)
    base_env.setdefault("LC_ALL", "C")
    base_env.setdefault("LANG", "C")
    base_env.setdefault("TZ", "UTC")
    base_env.setdefault("ASAN_OPTIONS", "detect_leaks=0")
    base_env.setdefault("LSAN_OPTIONS", "verbosity=0")

    # Baseline binary must exist.
    try:
        ensure_exe(baseline_bin)
    except Exception as e:
        print(f"ERROR: baseline binary not usable: {baseline_bin}: {e}", file=sys.stderr)
        return 2
    baseline_bin_sha256 = _sha256_file(baseline_bin)

    # Build candidate (cmake + make).
    cand_bin = candidate_repo / "build" / "ccextractor"
    build_log_path = report_dir / "candidate_build.log"
    if not args.skip_build:
        print("Building candidate...", flush=True)
        ok, out = build_candidate(candidate_repo, debug=args.debug_build)
        write_text(build_log_path, out)
        if not ok:
            print(f"ERROR: candidate build failed. See: {build_log_path}", file=sys.stderr)
            return 3
        print("Build OK.", flush=True)
    else:
        write_text(build_log_path, "<skip-build>\n")
        print("NOTE: --skip-build set; using existing candidate binary.", flush=True)

    try:
        ensure_exe(cand_bin)
    except Exception as e:
        print(f"ERROR: candidate binary not usable: {cand_bin}: {e}", file=sys.stderr)
        return 3
    candidate_bin_sha256 = _sha256_file(cand_bin)

    manifest_expected = {
        "samples_dir": str(samples_dir),
        "baseline_bin": str(baseline_bin),
        "baseline_bin_sha256": baseline_bin_sha256,
        "baseline_bin_size": baseline_bin.stat().st_size,
        "baseline_bin_mtime": int(baseline_bin.stat().st_mtime),
        "cases_file": str(cases_file) if cases_file else "",
        "cases_file_sha256": _sha256_file(cases_file) if cases_file else "",
        "cases": [
            {
                "id": c.case_id,
                "sample": c.sample.name,
                "args": c.ccx_args,
                "size": c.sample.stat().st_size,
                "mtime": int(c.sample.stat().st_mtime),
            }
            for c in cases
        ],
    }

    # Baseline generation (once, cached).
    if args.force_baseline:
        rm_tree(baseline_dir)
    if not should_skip_baseline(baseline_dir, manifest_expected):
        print("Baseline: generating fresh outputs.", flush=True)
        rm_tree(baseline_dir)
        (baseline_dir / "cases").mkdir(parents=True, exist_ok=True)
        for i, case in enumerate(cases, start=1):
            print(f"  [baseline] {i}/{len(cases)} {case.sample.name}", flush=True)
            case_root = baseline_dir / "cases" / case.case_id
            work_dir = case_root / "work"
            subs_dir = case_root / "subs"
            rm_tree(case_root)
            work_dir.mkdir(parents=True, exist_ok=True)
            subs_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = case_root / "stdout.txt"
            stderr_path = case_root / "stderr.txt"
            meta_path = case_root / "meta.json"

            cmd = [str(baseline_bin), *case.ccx_args, str(case.sample), "-o", "out"]
            rr = run_capture(
                argv=cmd, cwd=work_dir, env=base_env,
                timeout_sec=args.timeout,
                stdout_path=stdout_path, stderr_path=stderr_path,
            )
            copy_sub_outputs(work_dir, subs_dir)
            meta = {
                "case_id": case.case_id,
                "exit_code": rr.exit_code,
                "term_signal": rr.term_signal,
                "term_signal_name": format_signal(rr.term_signal),
                "files": collect_dir_files(subs_dir),
            }
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

        (baseline_dir / "manifest.json").write_text(
            json.dumps(manifest_expected, indent=2, sort_keys=True), encoding="utf-8"
        )
        (baseline_dir / ".complete").write_text(_now_iso() + "\n", encoding="utf-8")
        print("Baseline: done.", flush=True)
    else:
        print("Baseline: cached.", flush=True)

    # Candidate run (always).
    rm_tree(candidate_dir)
    (candidate_dir / "cases").mkdir(parents=True, exist_ok=True)
    case_results = []
    for i, case in enumerate(cases, start=1):
        print(f"  [candidate] {i}/{len(cases)} {case.sample.name}", flush=True)
        case_root = candidate_dir / "cases" / case.case_id
        work_dir = case_root / "work"
        subs_dir = case_root / "subs"
        work_dir.mkdir(parents=True, exist_ok=True)
        subs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = case_root / "stdout.txt"
        stderr_path = case_root / "stderr.txt"
        meta_path = case_root / "meta.json"

        cmd = [str(cand_bin), *case.ccx_args, str(case.sample), "-o", "out"]
        rr = run_capture(
            argv=cmd, cwd=work_dir, env=base_env,
            timeout_sec=args.timeout,
            stdout_path=stdout_path, stderr_path=stderr_path,
        )
        copy_sub_outputs(work_dir, subs_dir)
        meta = {
            "case_id": case.case_id,
            "exit_code": rr.exit_code,
            "term_signal": rr.term_signal,
            "term_signal_name": format_signal(rr.term_signal),
            "files": collect_dir_files(subs_dir),
        }
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        case_results.append((case.case_id, meta))

    # Compare.
    diffs = []
    for case_id, cand_meta in case_results:
        base_case = baseline_dir / "cases" / case_id
        cand_case = candidate_dir / "cases" / case_id
        problems = []

        for name in ("stdout.txt", "stderr.txt"):
            a = base_case / name
            b = cand_case / name
            if normalize_console(read_bytes(a)) != normalize_console(read_bytes(b)):
                problems.append(f"console_diff:{name}")

        try:
            base_meta = json.loads((base_case / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            base_meta = {}
        if base_meta.get("exit_code") != cand_meta.get("exit_code") or \
           base_meta.get("term_signal") != cand_meta.get("term_signal"):
            problems.append("exit_diff")

        base_subs = base_case / "subs"
        cand_subs = cand_case / "subs"
        base_files = collect_dir_files(base_subs)
        cand_files = collect_dir_files(cand_subs)
        if base_files != cand_files:
            problems.append("subs_file_list_diff")
        else:
            for rel in base_files:
                if not compare_files(base_subs / rel, cand_subs / rel):
                    problems.append(f"subs_diff:{rel}")
                    break

        if problems:
            diffs.append({"case": case_id, "problems": problems})

    # Report.
    report = {
        "generated_at": _now_iso(),
        "baseline_bin": str(baseline_bin),
        "baseline_bin_sha256": baseline_bin_sha256,
        "candidate_bin": str(cand_bin),
        "candidate_bin_sha256": candidate_bin_sha256,
        "num_samples": len(cases),
        "diffs": diffs,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if diffs:
        print(f"\nFAIL: {len(diffs)}/{len(cases)} cases differ.")
        for d in diffs:
            print(f"  {d['case']}: {', '.join(d['problems'])}")
        print(f"\nReport: {report_dir / 'report.json'}")
        return 1

    print(f"\nPASS: {len(cases)}/{len(cases)} cases match baseline.")
    print(f"Report: {report_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

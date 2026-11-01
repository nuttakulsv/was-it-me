#!/usr/bin/env python3
"""was-it-me: did my change break this test, was it already broken, or is it flaky?

    python3 wasitme.py -- pytest tests/test_tax.py
    python3 wasitme.py --runs 5 -- npm test -- cart
    python3 wasitme.py --base main -- go test ./billing/...
    python3 wasitme.py --test

Runs the command a few times in your working tree, then a few times in a temporary git worktree
of the base commit (your work without your changes), and tells you which of these it is:

    PASSES        nothing to explain
    YOURS         fails with your changes, passes without them
    PARTLY YOURS  fails either way, but some tests fail only with your changes
    PRE-EXISTING  fails the same way without your changes
    FLAKY         passes and fails on the same code

Your files are never touched. The worktree is removed afterwards.
Exit codes: 0 passes or pre-existing, 1 yours or partly yours, 3 flaky, 2 usage or setup error.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

DEPS = {"node_modules", ".venv", "venv", "env", "vendor", ".bundle", "Pods", "__pypackages__", ".yarn", ".pnp.cjs", ".pnp.loader.mjs"}
ENV_FILE = re.compile(r"^\.env(\.[\w-]+)?$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FAILURE_NAMES = [re.compile(rx, re.M) for rx in [
    r"^(?:FAILED|ERROR) (\S+)",                       # pytest short summary
    r"^--- FAIL: (\S+)",                              # go test
    r"^test (\S+) \.\.\. FAILED",                     # cargo test
    r"^rspec (\./\S+)",                               # rspec
    r"^not ok \d+ - (.+?)\s*$",                       # TAP, node --test
    r"^\s*(?:✕|×)\s+(.+?)(?:\s+\(\d+(?:\.\d+)?\s*m?s\))?\s*$",   # jest / vitest test lines
    r"^\s*FAIL\s+(\S.*?)(?:\s+\(?\d+(?:\.\d+)?\s*m?s\)?)?\s*$",  # jest / vitest file lines
    r"^\d+\) (\S+::\S+)",                             # phpunit
]]
SETUP_ERROR = re.compile(r"command not found|No such file or directory|Cannot find module|ERR_MODULE_NOT_FOUND"
                         r"|ModuleNotFoundError|ImportError while|No module named|cannot find package|not installed", re.I)


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    return r.stdout.strip() if r.returncode == 0 else None


def pick_base(top, explicit=None):
    """(commit, what it means). Uncommitted work -> HEAD; otherwise the fork point or the last commit."""
    if explicit:
        sha = git(top, "rev-parse", "--verify", "-q", explicit + "^{commit}")
        if not sha:
            raise SystemExit(f"was-it-me: can't find {explicit!r}")
        return sha, f"{explicit}"
    head = git(top, "rev-parse", "-q", "--verify", "HEAD")
    if not head:
        raise SystemExit("was-it-me: this repository has no commits yet, so there's nothing to compare with")
    if git(top, "status", "--porcelain"):
        return head, "HEAD, i.e. without your uncommitted changes"
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        fork = git(top, "merge-base", "HEAD", ref)
        if fork and fork != head:
            return fork, f"where you branched off {ref}"
    parent = git(top, "rev-parse", "-q", "--verify", "HEAD~1")
    if not parent:
        raise SystemExit("was-it-me: no uncommitted changes and no earlier commit to compare with")
    return parent, "HEAD~1, i.e. without your last commit"


def link_deps(top, wt, extra=()):
    """Point the worktree at the main tree's installed dependencies and .env files (git ignores them)."""
    listed = (git(top, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z") or "").split("\0")
    paths = [p.rstrip("/") for p in listed if p and (os.path.basename(p.rstrip("/")) in DEPS
                                                    or ENV_FILE.match(os.path.basename(p.rstrip("/"))))]
    linked = []
    for rel in paths[:200] + list(extra):
        src, dst = os.path.join(top, rel), os.path.join(wt, rel)
        if os.path.exists(src) and not os.path.lexists(dst) and os.path.isdir(os.path.dirname(dst)):
            os.symlink(src, dst)
            linked.append(rel)
    return linked


def run(command, cwd, timeout, env=None):
    start = time.time()
    try:
        r = subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        code, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        code = 124
        out = ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[timed out]"
    return {"ok": code == 0, "code": code, "out": ANSI.sub("", out), "secs": time.time() - start}


def failing_names(out):
    names = set()
    for rx in FAILURE_NAMES:
        names |= {m.strip() for m in rx.findall(out) if m.strip()}
    return names


def verdict(mine, base):
    """-> (exit code, headline, details)"""
    n_mine, n_base = len(mine), len(base)
    f_mine, f_base = sum(not r["ok"] for r in mine), sum(not r["ok"] for r in base)
    names_mine = set().union(*(failing_names(r["out"]) for r in mine if not r["ok"])) if f_mine else set()
    names_base = set().union(*(failing_names(r["out"]) for r in base if not r["ok"])) if f_base else set()
    only_mine = sorted(names_mine - names_base)
    details = []
    if f_mine == 0:
        head = "PASSES. It passed every time with your changes." + (" (It fails without them, so you fixed something.)" if f_base == n_base else "")
        return 0, head, details
    if 0 < f_mine < n_mine or 0 < f_base < n_base:
        if f_base == 0:
            head = (f"FLAKY, but only with your changes: failed {f_mine} of {n_mine} with them, 0 of {n_base} without. "
                    "That can be a race or ordering problem you introduced. Run more (--runs 10) before blaming the test.")
        else:
            head = f"FLAKY. It fails some of the time even without your changes ({f_base} of {n_base}), so the test or its setup is unreliable."
        if only_mine:
            details = ["Seen failing only with your changes:"] + [f"  {n}" for n in only_mine[:20]]
        return 3, head, details
    if f_base == 0:
        head = f"YOURS. It fails every time with your changes ({f_mine} of {n_mine}) and passes every time without them."
        if names_mine:
            details = ["Failing:"] + [f"  {n}" for n in sorted(names_mine)[:20]]
        return 1, head, details
    if only_mine:
        head = "PARTLY YOURS. It fails without your changes too, but some tests fail only with them."
        details = ["Failing only with your changes:"] + [f"  {n}" for n in only_mine[:20]]
        if names_base:
            details += ["Failing either way:"] + [f"  {n}" for n in sorted(names_base)[:20]]
        return 1, head, details
    head = "PRE-EXISTING. It fails the same way without your changes."
    if names_base:
        details = ["Failing either way:"] + [f"  {n}" for n in sorted(names_base)[:20]]
    elif names_mine != names_base or not names_mine:
        details = ["(Couldn't read test names from the output, so this compares pass/fail only. Check the output below.)"]
    return 0, head, details


def tail(out, n=12):
    lines = [l for l in out.rstrip().splitlines() if l.strip()]
    return "\n".join("    " + l[:200] for l in lines[-n:])


def report(command, label, mine, base, linked):
    code, head, details = verdict(mine, base)
    marks = lambda rs: " ".join("pass" if r["ok"] else "FAIL" for r in rs)  # noqa: E731
    lines = [f"was-it-me: `{command}`", "",
             f"  with your changes:  {marks(mine)}",
             f"  without them:       {marks(base)}    (base: {label})", "", f"Verdict: {head}"]
    if details:
        lines += [""] + details
    bad_base = next((r for r in base if not r["ok"]), None)
    bad_mine = next((r for r in mine if not r["ok"]), None)
    if bad_base and SETUP_ERROR.search(bad_base["out"]) and not (bad_mine and SETUP_ERROR.search(bad_mine["out"])):
        lines += ["", "Warning: the run without your changes looks like it failed to start (missing command, module or file),",
                  "not like the tests failed. Don't call it pre-existing yet. Try --setup 'npm ci' (or your install command)",
                  "or --link for files the tests need."]
    if bad_mine:
        lines += ["", "Last lines with your changes:", tail(bad_mine["out"])]
    if bad_base:
        lines += ["", "Last lines without your changes:", tail(bad_base["out"])]
    if linked:
        lines += ["", "Shared with the base worktree: " + ", ".join(linked[:8]) + (" ..." if len(linked) > 8 else "")]
    return code, "\n".join(lines)


def main(argv):
    p = argparse.ArgumentParser(prog="wasitme.py", description="Did my change break this test?",
                                usage="wasitme.py [--base REF] [--runs N] [--timeout SEC] [--setup CMD] [--link PATH] -- COMMAND")
    p.add_argument("--base", help="commit to compare with (default: HEAD if you have uncommitted changes, else your fork point)")
    p.add_argument("--runs", type=int, default=3, help="runs on each side (default 3)")
    p.add_argument("--timeout", type=int, default=600, help="seconds per run (default 600)")
    p.add_argument("--setup", help="command to run once in the base worktree first, e.g. 'npm ci'")
    p.add_argument("--link", action="append", default=[], help="extra path to share with the base worktree")
    p.add_argument("--no-link", action="store_true", help="don't share node_modules, .venv, .env and friends")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd or a.runs < 1:
        p.print_usage(sys.stderr)
        return 2
    command = cmd[0] if len(cmd) == 1 else shlex.join(cmd)

    cwd = os.getcwd()
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        print("was-it-me: run this inside a git repository", file=sys.stderr)
        return 2
    base, meaning = pick_base(top, a.base)
    label = f"{git(top, 'rev-parse', '--short', base)}, {meaning}"
    rel = os.path.relpath(os.path.realpath(cwd), os.path.realpath(top))

    print(f"was-it-me: running `{command}` {a.runs}x with your changes, then {a.runs}x on {label} ...", file=sys.stderr)
    mine = [run(command, cwd, a.timeout) for _ in range(a.runs)]

    tmp = tempfile.mkdtemp(prefix="was-it-me-")
    wt = os.path.join(tmp, os.path.basename(top))
    try:
        if git(top, "worktree", "add", "--detach", "--quiet", wt, base) is None:
            print("was-it-me: couldn't create a worktree for the base commit", file=sys.stderr)
            return 2
        linked = [] if a.no_link else link_deps(top, wt, a.link)
        env = dict(os.environ)
        # editable installs point at your working tree; put the base copy first on the import path
        env["PYTHONPATH"] = os.pathsep.join([os.path.join(wt, "src"), wt] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        where = os.path.join(wt, rel) if rel != "." else wt
        if not os.path.isdir(where):
            print(f"was-it-me: {rel} doesn't exist in the base commit", file=sys.stderr)
            return 2
        if a.setup:
            s = run(a.setup, wt, a.timeout, env)
            if not s["ok"]:
                print(f"was-it-me: --setup failed (exit {s['code']}):\n{tail(s['out'])}", file=sys.stderr)
                return 2
        base_runs = [run(command, where, a.timeout, env) for _ in range(a.runs)]
    finally:
        git(top, "worktree", "remove", "--force", wt)
        shutil.rmtree(tmp, ignore_errors=True)
        git(top, "worktree", "prune")

    code, text = report(command, label, mine, base_runs, linked)
    print(text)
    return code


def test():
    import contextlib
    import io

    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, check=True)  # noqa: E731

        def put(path, text):
            p = os.path.join(root, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write(text)

        def go(*args):
            buf = io.StringIO()
            old = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                    code = main(list(args))
            finally:
                os.chdir(old)
            return code, buf.getvalue()

        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        # a tiny "test runner": fails the names listed in broken.txt, needs node_modules/dep.txt to start
        put("check.py", "import os, sys\nif not os.path.exists('node_modules/dep.txt'):\n    sys.exit('Cannot find module dep')\n"
                        "bad = [l for l in open('broken.txt').read().split() if l]\n"
                        "for name in bad:\n    print('FAILED tests/test_app.py::' + name)\nsys.exit(1 if bad else 0)\n")
        put("broken.txt", "")
        put(".gitignore", "node_modules/\n")
        put("node_modules/dep.txt", "installed\n")
        g("add", ".")
        g("commit", "-qm", "green")

        try:  # clean tree, one commit: nothing to compare with
            go("--runs", "2", "--", "python3", "check.py")
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert "no earlier commit" in str(e), e

        put("broken.txt", "test_total\n")                                 # my change breaks it
        code, out = go("--runs", "2", "--", "python3 check.py")
        assert code == 1 and "YOURS" in out and "test_total" in out and "node_modules" in out, out
        assert git(root, "worktree", "list").count("\n") == 0, "worktree must be cleaned up"

        g("commit", "-qam", "broken on main")                              # now it's broken before my change
        put("other.txt", "unrelated\n")
        code, out = go("--runs", "2", "--", "python3 check.py")
        assert code == 0 and "PRE-EXISTING" in out and "test_total" in out, out

        put("broken.txt", "test_total test_tax\n")                        # I break one more on top
        code, out = go("--runs", "2", "--", "python3 check.py")
        assert code == 1 and "PARTLY YOURS" in out and "Failing only with your changes:\n  tests/test_app.py::test_tax" in out, out

        code, out = go("--runs", "2", "--no-link", "--", "python3 check.py")  # base can't start without deps
        assert "failed to start" in out, out

        counter = os.path.join(root, "..", os.path.basename(root) + "-count")
        put("flaky.py", f"import sys\np = {counter!r}\nn = int(open(p).read()) if __import__('os').path.exists(p) else 0\n"
                        "open(p, 'w').write(str(n + 1))\nsys.exit(n % 2)\n")
        g("add", "flaky.py")
        g("commit", "-qm", "flaky")
        put("other.txt", "changed\n")
        code, out = go("--runs", "2", "--", "python3 flaky.py")
        assert code == 3 and "FLAKY. It fails some of the time even without" in out, out
        os.remove(counter)

        put("other.txt", "unrelated\n")
        g("add", "-A")
        g("commit", "-qm", "clean")
        assert pick_base(root)[1].startswith("HEAD~1"), pick_base(root)
        put("broken.txt", "")
        assert pick_base(root)[1].startswith("HEAD, i.e."), pick_base(root)

    assert failing_names("FAILED tests/a.py::t1 - assert 1 == 2\n--- FAIL: TestX (0.01s)\ntest m::y ... FAILED\n"
                         "  ✕ adds tax (3 ms)\n FAIL  src/cart.test.ts > total\nnot ok 2 - rounds\n") == {
        "tests/a.py::t1", "TestX", "m::y", "adds tax", "src/cart.test.ts > total", "rounds"}
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        test()
    else:
        sys.exit(main(sys.argv[1:]))

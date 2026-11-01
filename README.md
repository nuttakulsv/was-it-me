# was-it-me

[ภาษาไทย](README.th.md) · From the maker of [receipts](https://github.com/nuttakulsv/receipts) and [honest-tests](https://github.com/nuttakulsv/honest-tests)

> "The 3 remaining failures are pre-existing and unrelated to my changes."

Every coding agent says this eventually. Sometimes it's true. Often it isn't, and you only find out after the merge. People do it too ("that test is just flaky").

was-it-me settles it. It runs the failing command with your changes, then again in a throwaway git worktree without them, a few times each, and gives you a verdict:

```
$ python3 wasitme.py -- pytest tests/test_tax.py

was-it-me: `pytest tests/test_tax.py`

  with your changes:  FAIL FAIL FAIL
  without them:       pass pass pass    (base: 1a2b3c4, HEAD, i.e. without your uncommitted changes)

Verdict: YOURS. It fails every time with your changes (3 of 3) and passes every time without them.

Failing:
  tests/test_tax.py::test_rounding_half_even

Last lines with your changes:
    E       assert Decimal('10.13') == Decimal('10.12')
    FAILED tests/test_tax.py::test_rounding_half_even - assert Decimal('10.13') == Decimal('10.12')
    1 failed, 13 passed in 0.21s
```

| Verdict | Means | Exit code |
|---|---|---|
| **PASSES** | nothing to explain | 0 |
| **YOURS** | fails with your changes, passes without them | 1 |
| **PARTLY YOURS** | fails either way, but some tests fail only with your changes (it lists them) | 1 |
| **PRE-EXISTING** | fails the same way without your changes | 0 |
| **FLAKY** | passes and fails on the same code. It tells you whether that also happens without your changes | 3 |

It reads failing test names from pytest, Jest, Vitest, Go, cargo, RSpec, PHPUnit and TAP output, so "the same 2 tests fail on main" and "one more test fails with my change" come out differently.

## Use it

You need `python3` and `git`. Nothing to install:

```
curl -O https://raw.githubusercontent.com/nuttakulsv/was-it-me/main/skills/was-it-me/wasitme.py

python3 wasitme.py -- npm test -- cart
python3 wasitme.py --runs 10 -- go test ./billing/ -run TestInvoice
python3 wasitme.py --base main -- bundle exec rspec spec/models/order_spec.rb
```

**What it compares with.** If you have uncommitted changes, it compares with `HEAD`. If your tree is clean, it compares with where your branch forked from `main` (or `master`), or with the previous commit if you're on main. `--base` picks anything else.

**Your files are safe.** It never stashes or checks out in your working tree. The base copy is a separate `git worktree` in a temp folder, removed when it's done.

**Dependencies.** The base worktree gets symlinks to your installed `node_modules`, `.venv`, `vendor` and `.env` files, so tests can start without a reinstall. For Python it also puts the base copy first on `PYTHONPATH`, so an editable install doesn't quietly import your changed code. If the base run can't start (missing module, command not found), it warns you instead of calling the failure pre-existing.

## For coding agents

There's a skill that tells the agent to run was-it-me before it calls anything pre-existing or flaky, and what to do with each verdict (fix it if it's yours, never add retries or skips to hide flakiness).

Claude Code:

```
/plugin marketplace add nuttakulsv/was-it-me
/plugin install was-it-me@was-it-me
```

Codex, Cursor and anything else that reads SKILL.md:

```
npx skills add nuttakulsv/was-it-me
```

Pairs well with [receipts](https://github.com/nuttakulsv/receipts), which sends the agent back when it calls a failure pre-existing without having checked.

## Limits

- In monorepos where workspace packages are symlinked inside `node_modules`, the shared `node_modules` points back at your changed packages. Use `--setup 'pnpm install --frozen-lockfile'` (or `npm ci`) to install fresh in the base worktree.
- It runs your command twice as many times as `--runs`. For a slow suite, narrow the command first.
- Three runs can't prove a test isn't flaky. If it matters, use `--runs 20`.
- Tests that depend on shared state outside the repo (a local database, a fixed port) can interfere between the two sides.

## Tests

```
python3 skills/was-it-me/wasitme.py --test
```

## License

MIT

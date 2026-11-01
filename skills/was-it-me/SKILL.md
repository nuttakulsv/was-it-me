---
name: was-it-me
description: Use when a test, build or check fails after you changed code and you're about to call the failure pre-existing, flaky, unrelated to your changes, or "also failing on main". Also use when the user asks whether a failure is theirs. Runs the failing command with and without the changes and gives a verdict.
---

# Was it me?

"These failures are pre-existing and unrelated to my changes" is the easiest sentence to write and the one users trust least. Don't write it until you've checked.

## How to check

1. Narrow the command to the failing tests (one file or one test name). It's faster and the verdict is clearer.
2. Run, from the directory you'd normally run the tests in:

   ```
   python3 <this skill's folder>/wasitme.py -- <the failing command>
   ```

   For example `python3 .../wasitme.py -- pytest tests/test_tax.py -k rounding` or `python3 .../wasitme.py -- npm test -- cart`.

   It runs the command 3 times as things are now, then 3 times in a temporary git worktree of the base commit (HEAD when you have uncommitted changes, otherwise where the branch forked). It shares `node_modules`, `.venv` and `.env` files with that worktree so the tests can start. Nothing in the working tree is changed.
3. Read the verdict and act on it:
   - **YOURS**: your change broke it. Fix it. Don't skip, loosen or delete the test.
   - **PARTLY YOURS**: some failures were already there, the ones it lists under "only with your changes" are yours. Fix those.
   - **PRE-EXISTING**: it fails the same way without your changes. You can say so, and quote the verdict.
   - **FLAKY** without your changes: the test is unreliable. Say so with the numbers. Don't add retries, sleeps or skips to hide it unless the user asks.
   - **FLAKY, but only with your changes**: treat it as yours. That's usually a race or an ordering problem you introduced. Run more (`--runs 10`) to be sure.
   - **Warning: failed to start**: the base run couldn't start (missing install, missing file). That isn't evidence of anything. Rerun with `--setup '<install command>'` or `--link <path>`.
4. In your reply, quote the verdict line and the command you checked.

## Options

- `--base main` compares with another commit, for example to include commits you've already made on the branch.
- `--runs 5` runs each side more times.
- `--setup 'npm ci'` runs an install in the base worktree first, for monorepos where shared `node_modules` would point back at your changed packages.

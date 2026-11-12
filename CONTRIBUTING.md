# Contributing

Thanks for looking at this. It's a small project, so the bar for a good
contribution is low — but I do try to keep `main` green and readable.

## Before you start

- Read the [README](README.md) first. Most "how do I…" questions are answered
  there, and a lot of feature ideas already exist as issues.
- Search the open and closed issues before opening a new one. Duplicates make
  everyone's life harder.

## Development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt      # playwright + pytest + ruff
python -m playwright install chromium     # one-time browser download
```

Then run the same checks CI runs:

```bash
ruff check askgo tests
python -m unittest discover -s tests
python -m compileall -q askgo tests
```

All three need to pass before you open a PR.

## How I like to work

- **One thing per PR.** A small, focused change is easier to review and merge
  than a big grab-bag.
- **Open an issue first** for anything non-trivial, so we agree on the
  direction before you spend time on the code.
- **No secrets, ever.** Don't commit `.env`, login state, keys, or personal
  data. The `.gitignore` already covers the usual ones — don't weaken it.
- Keep commit messages short and specific, e.g. `feat: …`, `fix: …`,
  `docs: …`, `chore: …`.
- Don't force-push to `main`. Open a branch and a PR instead.

## Selectors

If you touch `askgo/selectors.py`, run `python -m askgo.cli probe` against the
live page and note what you changed. Selectors drift, so a short comment or an
issue link helps the next person.

## Reporting a problem

Use the bug report template. Paste the JSON from stdout, the exact commands,
your OS and Python version, and whether you ran `login`. Redact anything
sensitive — a screenshot from `debug/` is a huge help.

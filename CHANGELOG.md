# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Synced the README env-var table and the `config.py` docstring with the two
  variables `Config.from_env` reads but neither listed: `ASKGO_AUTH_STATE_FILE`
  (where the auth state is saved) and `ASKGO_LOGIN_TIMEOUT_S` (seconds to wait
  for a first-time login). Closes the same gap the `.env.example` sync left in
  the table.
- Synced `.env.example` with the variables `Config.from_env` actually reads:
  added `ASKGO_LOGIN_TIMEOUT_S` (integer seconds for a first-time login) and
  `ASKGO_AUTH_STATE_FILE`, and noted that the two numeric vars are plain
  integers.
- Made `Config.from_env` tolerate a malformed numeric `.env` value: a typo like
  `ASKGO_TIMEOUT_MS=60s` or an empty value used to raise a bare `int()` traceback
  that skipped the "always print one JSON object on stdout" contract (config is
  built before the CLI's error handler). It now falls back to the default and
  warns on stderr instead, with a regression test in `tests/test_config.py`.
- Fixed a stale reference in the README: the Development section still said CI
  runs on Python 3.9 and 3.12, but the matrix moved to 3.11 and 3.12 when 3.9
  was dropped.
- Made the Playwright import in `askgo/selectors.py` type-only so the hand-tuned
  selector patterns can be imported and tested without a browser, and added
  `tests/test_selectors.py` to lock those patterns in (login / logout markers,
  the model picker, the composer, and the send / stop / new-chat buttons, in
  both Chinese and English).
- Dropped Python 3.9 from the CI test matrix: it reached end-of-life in October
  2025 and the runner image no longer ships it, so the 3.9 leg could not even
  start. The matrix now runs on 3.11 and 3.12.
- Added a test suite for the IPC file-queue layer (`tests/test_ipc.py`) covering the
  path helpers, the timeout-and-cleanup path, and `process_request`'s success /
  empty-reply / new-session / model-fallback / unexpected-error branches.
- Added a "How it works" diagram to the README.

## [0.2.0] - 2026-11-12

### Added
- A unit test suite in `tests/` covering config, error mapping, and the CLI
  argument parsing (18 tests, run with `python -m unittest discover -s tests`).
- A CI matrix that runs on both Python 3.9 and 3.12, plus a ruff lint job.
- `requirements-dev.txt` for the test/lint tooling.
- A rendered terminal screenshot in the README.
- A `CONTRIBUTING.md`, a `SECURITY.md`, and an issue-template config so new
  issues come in through the right template.

### Changed
- Tidied imports and a few small cleanups flagged by ruff.
- Refreshed the README's Development section with test and lint commands.

## [0.1.0] - 2026-11-11

### Added
- The `ask` command: send a prompt and get the reply back as JSON.
- The `login` command for a one-time interactive login that saves the session.
- The `serve` / `stop` pair for a long-lived browser so multi-turn chats carry on.
- The `probe` command to dump candidate selectors to `debug/` for tuning.
- Media handling: images / video / audio are downloaded to `media/` by default,
  or returned as links with `--no-save-media`.
- A basic CI workflow that byte-compiles the package and checks imports.
- The MIT license and a `.gitignore` that keeps login state and secrets out.

### Changed
- Wrote the README and all docs in English.

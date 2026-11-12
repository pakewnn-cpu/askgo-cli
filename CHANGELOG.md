# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

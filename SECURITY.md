# Security

Thanks for helping keep this safe.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | yes       |

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Use GitHub's
[private vulnerability reporting](https://github.com/pakewnn-cpu/askgo-cli/security/advisories/new)
instead, so we can fix it quietly before it goes public.

## What to include

- The version or commit you're on.
- The steps to reproduce, and what you expected vs. what happened.
- Which command or step is affected (`ask`, `login`, `serve`, `probe`).

## A note on this project

This tool only ever touches your own AskGo account. It stores the session
cookie state, not your password, and it never bypasses captchas or human
checks. If you find a way to make it do either of those, that's worth
reporting — it means the guardrails have a hole.

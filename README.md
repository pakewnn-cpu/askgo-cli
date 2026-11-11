# AskGo CLI

A small command-line client that drives the [askgo.co](https://askgo.co) web UI
with [Playwright](https://playwright.dev/python/). I built it because AskGo only
has a web interface and no public API, so a terminal agent (like Codex CLI) can
send prompts and get structured JSON back instead of me clicking around.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # or: pip install playwright
python -m playwright install chromium
cp .env.example .env                 # then edit .env
```

## First-time login (once)

```bash
python -m askgo.cli login
```

A visible browser opens; log in by hand. The session is saved to
`.askgo/storage_state.json` and reused on every later run. If it expires, re-run
`login` — a run that can't authenticate returns exit code **2** with a screenshot.

## Usage

```bash
# one-shot: fresh headless browser, uses the saved login state
python -m askgo.cli ask "explain closures" --model <model-name>

# media only, don't download the files
python -m askgo.cli ask "draw a cat" --no-save-media

# multi-turn: keep a browser alive and reuse the conversation
python -m askgo.cli serve &            # in one terminal
python -m askgo.cli ask "what was my last question?"   # continues the chat
python -m askgo.cli ask "and now..." --new-session      # start a fresh chat
python -m askgo.cli stop               # stop the serve browser
```

`ask` decides for itself: if a `serve` browser is reachable on the CDP endpoint
(default `http://127.0.0.1:9222`), the call is routed through it so the
conversation carries on. If nothing is running, it spins up a fresh headless
browser for that single call and exits. `--serve` forces the IPC path, and
`--new-session` starts a clean conversation even when a `serve` is up.

## Output

Every run prints **one JSON object to stdout**; all logs and warnings go to
stderr so the JSON stays parseable.

```json
{
  "ok": true,
  "model": "gpt-x",
  "reply": "...",
  "media": [{"type": "image", "url": "...", "path": "media/image_....png", "ok": true}],
  "session_id": null,
  "error": null,
  "debug": {}
}
```

- A text reply fills `reply`; `media` is an empty list.
- A media-only reply (image / video / audio) leaves `reply` as `null` and puts
  the result under `media[]`. By default each file is downloaded into `./media`
  and the local `path` is returned; with `--no-save-media` only the `url` is
  returned. One failed download doesn't fail the whole run — that item's `ok` is
  `false` and the text result is still returned.
- On failure, `ok` is `false`, `error` says what happened, and `debug` names the
  failed step/selector plus a screenshot path under `./debug`.

## Exit codes

| code | meaning |
|------|---------|
| 0    | success |
| 1    | client / generation error (selector missing, timeout, empty reply) |
| 2    | not logged in / login expired |

## Config

Everything is read from `.env` and can be overridden on the command line; nothing
is hardcoded.

| variable | default | what it does |
|----------|---------|--------------|
| `ASKGO_BASE_URL` | `https://askgo.co` | site base URL |
| `ASKGO_DEFAULT_MODEL` | *(empty)* | model used when `--model` is omitted |
| `ASKGO_HEADLESS` | `1` | `0` keeps the browser visible |
| `ASKGO_TIMEOUT_MS` | `60000` | per-step timeout |
| `ASKGO_STATE_FILE` | `.askgo/storage_state.json` | saved login state |
| `ASKGO_MEDIA_DIR` | `media` | where media is saved |
| `ASKGO_DEBUG_DIR` | `debug` | where screenshots go |
| `ASKGO_SERVE_URL` | `http://127.0.0.1:9222` | CDP endpoint for `serve` |
| `ASKGO_USER_AGENT` | *(empty)* | optional user-agent override |

## Selectors

All page selectors live in `askgo/selectors.py`. They're best-effort (role / aria
/ placeholder based) and need tuning against the real page. Run
`python -m askgo.cli probe` to dump candidate elements to `debug/`.

## Safety

- No account or password is stored — only the session cookie state is saved.
- Captchas and human checks are not bypassed; a login challenge exits and waits
  for a person.
- Only my own account is used, low-frequency, single-threaded, no scraping of
  history or other people's data.

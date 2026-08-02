# AGENTS.md

See `CLAUDE.md` for the project identity guard and evidence-first rules; they
apply to all agents. This file adds environment/run guidance.

## Cursor Cloud specific instructions

This repo is two products in one tree:

1. A **Python** evidence/data pipeline (`scripts/`, `tests/`, `national/`,
   `corpus/`, `data/`) that builds and validates hash-locked public-finance
   receipts. Pinned deps are in `requirements.txt`.
2. A **web** app in `web/` — the resident-facing Vite + React static reader.
   This is the runnable application. It has its own `web/package.json` and
   `web/package-lock.json`.

The root `package.json` only pins `wrangler` for the Cloudflare deploy path,
which is **production-only** (see `wrangler.jsonc`, `docs/DEPLOY.md`). It is not
needed to run or test the app locally.

Standard commands are already documented — Python setup/checks in
`CONTRIBUTING.md`, and app commands in `README.md` ("Run" section) and
`web/package.json` scripts. Use those; below are only the non-obvious caveats.

### Environment / setup caveats

- Target runtimes are Python 3.12 and Node.js 22 (matching CI). The VM ships
  compatible versions; the update script only refreshes dependencies.
- `pip install -r requirements.txt` installs into the user site
  (`~/.local/bin`) on this VM. That is expected and fine.
- `cryptography` in `requirements.txt` is required so `pypdf` can open an
  AES-encrypted committed source PDF; without it the extract gate raises
  `DependencyError`.

### Running the app

- Dev server: `npm --prefix web run dev` → http://127.0.0.1:5401 with
  `strictPort: true`, so it **fails closed** if 5401 is occupied (it will not
  hop to another port). `npm --prefix web run preview` serves the built
  `web/dist` on 127.0.0.1:5402, also strict-port.
- The browser is a static reader: it makes no runtime AI or government-site
  requests and needs no secrets or backend. No `.env` is required for dev.

### Testing / building caveats

- Web: `npm --prefix web test -- --run` (vitest) and `npm --prefix web run
  build` (tsc + vite). Node 22.14 emits `EBADENGINE` warnings for `jsdom` /
  `undici` (they want a slightly newer Node 22); tests still pass — the warning
  is not a failure.
- `web/package.json` runs `tsc`/`vitest` via `node --max-old-space-size=2048`
  on purpose: the default V8 heap aborts them with an allocation failure on
  some installs. Keep that wrapper if you touch those scripts.
- Python tests: `python -m unittest discover -s tests -p "*test*.py"`. The
  suite prints `WARNING:` / `ERROR:` / `REFUSED:` lines by design — several
  tests exercise failure paths. Trust the final `OK` / `FAILED` line, not those
  intra-test messages.
- The evidence pipeline is deterministic: `python scripts/build_evidence_model.py`
  and the other builders regenerate committed artifacts byte-for-byte, so a
  clean checkout stays clean after running them. CI fails if a builder rewrites
  a tracked file, so never hand-edit generated files under `web/src/data/` or
  the README's `<!-- generated:* -->` blocks — rerun the builder instead
  (`scripts/render_readme_facts.py --check` verifies the README).

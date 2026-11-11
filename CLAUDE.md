# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

WoW Chat Voice reads World of Warcraft chat aloud (WoW Forever, Russian client), each player in their own voice: race voices cloned by F5-TTS from the user's CatQuest_Voices pack, or Russian Windows (SAPI) voices. Two parts: a Lua addon and a Python companion program for Windows. User docs (Russian): README.md; design, protocol, research notes: DEVELOPMENT.md.

## Commands

Tools come from mise: `.mise.toml` pins Python, uv and LuaJIT, points uv at mise's Python (`UV_PYTHON`) and lets mise create and activate `.venv` from the uv project (`python.uv_venv_auto`); the test/icon libraries are the `dev` group of `pyproject.toml`, locked in `uv.lock`. `mise install` once, then:

- `mise run test` — every test: Python (numpy, pymorphy3, num2words installed, so nothing is skipped) and Lua
- `mise run test-py` / `mise run test-lua` — one side only; a single Python test: `mise exec -- uv run --locked python -m unittest discover -s companion/tests -k NumberAgreement`
- `mise run icon` — regenerate `addon/WowChatVoice/Icon.tga` (and `tools/icon_preview.png`) from `tools/make_icon.py`
- The Lua tests `loadfile` the addon's files by relative path, so `test-lua` runs in `addon/WowChatVoice`; `test_protocol.py` runs the addon's `Protocol.lua` encoder with `luajit`.
- The companion runs only on Windows (`companion/WowChatVoice.cmd` makes `.venv`, installs `requirements.txt` and `requirements-f5.txt`, runs `python -m wcv`; `--selftest` / `--selftest-f5` render test audio to files). Development happens on macOS; testing is on a Windows machine with the game, over SSH: copy `addon/WowChatVoice/*` (except `VoiceList.lua`, which the companion writes) into the client's `Interface\AddOns\WowChatVoice\` and `companion/wcv/*.py` into the program's folder; the addon picks changes up on `/reload`, the program on restart. Screen capture can only be tested in the user's desktop session, never from SSH. Never launch or kill the game while someone plays.

## Architecture

- **Transport — the pixel strip** (`addon/WowChatVoice/Protocol.lua` + `Strip.lua` → `companion/wcv/capture.py` + `protocol.py`). Addons can't write files and WoW only loads signed SAPI DLLs, so the addon paints each line as dark cells along the top edge of the screen and the companion grabs the WoW window (Windows Graphics Capture, `mss` fallback) and decodes it. Frame: sync cells, 4 calibration cells (the decoder takes its thresholds from them, so `P.LEVELS` can change in the addon alone), header with version/seq/length/CRC-16, UTF-8 payload. Drawn from the left: on the right a minimap at the top edge covers it. The channel is one-way (addon → program); the only way back is files the program writes into the addon folder that the game reads on `/reload` (`VoiceList.lua`).
- **Payload**: `kind␟sender␟race␟sex␟class␟channel␟options␟text[␟raw]` with `\x1f`; options `rate=;vol=;voice=;decl=;raw=1` come from `ns.LineOptions()` in `Core.lua`. Non-chat kinds: `control` (settings, every 2 min), `regex` (dictionary regexes in parts), `stop`, `reset`; the companion speaks only kinds in `LABELS` (`__main__.py`).
- **Text pipeline** (order matters for context rules): addon cleans markup and applies dictionary words/phrases/stems, marking replacements `\x02…\x03` → companion declines marked replacements after prepositions (`morph.py`, pymorphy3) → dictionary regexes (`dictionary.py`), then number forms `N [a|b|c]` and ordinals `<N>` → stress (`text.Accentor`, RUAccent; the dictionary's `+` wins) → numbers to words agreeing with the next word (`text.agree`) → engine. Regexes see text after the addon's replacements (e.g. "кд" is already "кулд+аун").
- **Dictionary layers** (`Dictionary.lua`): the default `D.DEFAULT` lives in the addon; SavedVariables keep only the player's diff `dictionaryEdits` (changed/added blocks by key, deleted keys, header). Key = normalised words (`*` for stems) or, for a regex, its pattern (text before the last `=`). Changing a default entry needs no migration; changing a default regex's pattern needs `D.RENAMED[old] = new`. The merged regexes are also saved as `regexes` for the companion to read without the game.
- **Engines** (`engines.py`): the addon's choice per line; F5 is loaded lazily and unloaded when the addon switches to Windows voices. `speech.py` (SAPI via pywin32, voice per player by rendezvous hashing, per-engine stress format). `f5engine.py`: voice bank from CatQuest (`catquest.py`, Whisper-checked refs `refcheck.py`, pitch-shifted copies), voice per character with memory (`assign.py`, `assignments.json`), lines split into statement runs and single questions (`sentence_groups`), `intonation.py` (Praat PSOLA: yes/no rise + last-syllable boost, peak on the wh-word), then `tidy`/`limit` loudness. One shared `audio.Player` plays everything in order; `stop` drops queued and in-flight lines by generation.
- **Config**: `DEFAULT_CONFIG` in `companion/wcv/__main__.py`; new keys are written into the user's `config.json` on start. The addon's settings are `ns.DEFAULTS` in `Core.lua`.

## Conventions

- Commit messages: no Claude/AI attribution footer. Commits use the repo's git identity (Roman Geraskin; the e-mail stays out of the files). Commit only when asked.
- Default branch is `master`.
- Tools through mise only: exact versions in `.mise.toml`; Python libraries for development in the `dev` group of `pyproject.toml` (exact versions; `uv add --group dev <pkg>==<ver>` updates `uv.lock`, commit both); tests and scripts run as mise tasks (`uv run --locked …`; add a task for a new script). No system Python, Homebrew LuaJIT, `pip install` or ad-hoc `uv run --with`. The companion's runtime on the player's machine is separate: `WowChatVoice.cmd` + `companion/requirements*.txt`.
- Amending: a commit not pushed yet may be amended when that is the sensible thing (a fix-up of the same change, a forgotten file); a pushed commit is not rewritten — fix it with a new commit.
- Name: the display name is "WoW Chat Voice" (addon title, UI, docs); the addon folder and identifiers stay `WowChatVoice` (`WowChatVoiceDB` is tied to the folder name: renaming it would reset players' settings).
- Markdown: no hard line wraps. A paragraph or list item is one line; the renderer wraps long lines.
- No local identifiers in the repo: machine names, local paths, account or character names (examples use made-up or lore names).
- The version lives in `addon/WowChatVoice/WowChatVoice.toc` (`## Version`); CHANGELOG.md sections are `## <version>`. Planned: 0.2.0 retail, 0.3.0 Rust + ONNX Runtime, 0.4.0 distribution, 0.5.0 all game languages.
- User-facing text (addon UI, README, program log) is Russian; code, comments and CLAUDE.md are English. The WoW client font has no "→" or en dash: use "=", "—" or "-" in addon strings.
- Reference clips, models and game audio are never committed: they are made or downloaded on the user's machine (F5 model CC BY-NC, CatQuest pack CC BY-NC-SA, game audio Blizzard's).

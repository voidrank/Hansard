# Installing Trainlint

## Quickest — install from the marketplace (two lines)

Trainlint's repo *is* a Claude Code plugin marketplace, so once it's public anyone can:

```
/plugin marketplace add voidrank/Trainlint
/plugin install trainlint@trainlint
/reload-plugins
```

That's it — no clone, no editing `settings.json`. The plugin ships **both layers**: the
action doorman (`UserPromptSubmit`/`PreToolUse`) *and* the research lint
(`SessionStart`→lint, `PreCompact`/`SessionEnd`→harvest).

> Needs a normal Claude Code session (`/plugin` is unavailable over Remote Control).

## Even simpler — once listed in the official community directory

If Trainlint is accepted into Anthropic's built-in `claude-plugins-community` marketplace
(submit at <https://platform.claude.com/plugins/submit>), there's nothing to add — it's
already available to every Claude Code user:

```
/plugin install trainlint@claude-plugins-community
```

## Requirements

Pure Python **standard library — zero dependencies**. The only optional extra is the
opt-in small-model classifier: `pip install anthropic` + `ANTHROPIC_API_KEY` (without it
it falls back to the regex floor; nothing else is affected).

---

## Form A — settings.json hooks (advanced: Remote Control, or no plugin system)

Use this only when `/plugin` isn't available (e.g. Remote Control) or you don't want the
plugin system. Route through a **stable symlink** so moving/renaming later can't lock you
out (see the footgun):

```bash
git clone git@github.com:voidrank/Trainlint.git ~/Trainlint
ln -sfn ~/Trainlint/trainlint ~/trainlint
```

Add to the `hooks` block of `~/.claude/settings.json` (use **absolute paths** — `~` may
not expand there; replace `<user>`):

```json
"hooks": {
  "UserPromptSubmit": [
    { "hooks": [ { "type": "command", "command": "python3 /home/<user>/trainlint/hooks/router.py" } ] }
  ],
  "PreToolUse": [
    { "matcher": "Bash|Edit|Write|SendUserFile",
      "hooks": [ { "type": "command", "command": "python3 /home/<user>/trainlint/hooks/router.py" } ] }
  ],
  "PreCompact":   [ { "hooks": [ { "type": "command", "command": "python3 /home/<user>/trainlint/research/harvest.py" } ] } ],
  "SessionEnd":   [ { "hooks": [ { "type": "command", "command": "python3 /home/<user>/trainlint/research/harvest.py" } ] } ],
  "SessionStart": [ { "hooks": [ { "type": "command", "command": "python3 /home/<user>/trainlint/research/lint.py" } ] } ]
}
```

> Using Form A and the plugin together double-injects — after installing the plugin,
> remove this `hooks` block.

---

## Form B — OpenAI Codex CLI

Codex cloned Claude Code's hook protocol — verified against the real `codex-cli` binary
(v0.142.4): identical event names (`SessionStart` / `UserPromptSubmit` / `PreToolUse` /
`PreCompact` / `Stop`), identical input fields (`tool_name` / `tool_input`), and an identical
output schema (`hookSpecificOutput` · `permissionDecision` · `permissionDecisionReason` ·
`additionalContext` · `systemMessage`). So the entire Python pipeline runs unchanged. The
installer bakes absolute paths into `hooks.json` (Codex's own plugin system uses
`.codex-plugin/plugin.json`, not `${CLAUDE_PLUGIN_ROOT}`, so we don't rely on that env alias).
One script does the Codex-specific plumbing:

```bash
git clone git@github.com:voidrank/Trainlint.git ~/Trainlint
~/Trainlint/trainlint/install-codex.sh        # CODEX_HOME=~/.codex by default
```

It (1) merges trainlint's hooks — with absolute paths baked in — into `~/.codex/hooks.json`
(non-destructive: your other hooks are kept; idempotent: re-run anytime, no duplicates), and
(2) renders `commands/*.md` into `~/.codex/prompts/trainlint-*.md`, so you get
`/trainlint-plan`, `/trainlint-quiz`, `/trainlint-viz`, `/trainlint-lint`, `/trainlint-init`.
Start a fresh Codex session to load the hooks. Re-run after moving the repo (paths are baked).

**Two Codex deltas, handled for you:**
- *Tool names.* Codex's `PreToolUse` fires for `Bash` / `apply_patch` (no Edit/Write/Read).
  `hooks/codex_compat.py` rewrites an `apply_patch` envelope (and the Bash-heredoc form) into
  Claude-style Edit `tool_input` before the pipeline sees it, so every check/verifier is
  tool-agnostic.
- *No `SessionEnd`.* Harvest runs on `PreCompact` only (the moment-before-loss case); `flow.py`
  is already turn-anchored, not session-anchored, so nothing else is affected.

---

## Form C — Kimi CLI (Kimi Code)

Kimi is a Python coding agent (`uv tool install kimi-cli`) with a Claude-shaped hook system —
but it is **block-only**: its hook runner reads only `action` (allow/block) + `reason`
(`kimi_cli/hooks/runner.py`), so the soft channels (silent coach, always-on compass, non-blocking
escalate) have no native home. Install:

```bash
~/Trainlint/trainlint/install-kimi.sh        # writes to $KIMI_SHARE_DIR or ~/.kimi
```

It merges trainlint's hooks into the `hooks = [...]` array in `~/.kimi/config.toml` (preserving
your other hooks; idempotent) and installs the 5 commands as Kimi skills under `~/.kimi/skills/`,
callable as `/skill:trainlint-plan` etc. Each hook command is prefixed `TRAINLINT_HOST=kimi` so the
router adapts its output to Kimi's model.

**What ports, and what doesn't (per the `kimi-output-model` decision):**
- *Reject* — a PreToolUse hook emitting `permissionDecision:deny` blocks the tool and returns the
  reason to the agent as a `ToolError` (`tools/.../toolset.py:397`). **Verified live** on an
  authenticated session: the blocked Shell command never ran and the reason reached the model.
- *Report doorman* — Stop `block`+reason re-runs the turn with the reason (`soul/kimisoul.py:665`),
  exactly `reportcheck.py`'s rewrite.
- *Harvest* — runs on `PreCompact` **and** `SessionEnd` (Kimi has both).
- *Escalate* — converted to a (rare, destructive) block carrying the alert as the reason —
  "escalate-by-block."
- *Tool names* — `hooks/kimi_compat.py` maps `Shell`/`WriteFile`/`StrReplaceFile`
  (fields `command`/`path`/`edit:{old,new}`) to Claude-style Bash/Write/Edit `tool_input`.
- *Coach + always-on compass* — **dropped.** Kimi never injects hook stdout into context.

---

## Verify

```bash
cd ~/Trainlint/trainlint && python3 tests/run.py              # 21/21
cd ~/Trainlint/trainlint/research && python3 test_research.py # 9/9
python3 tests/test_codex_compat.py                            # Codex apply_patch shim
```

## Opt-in knobs (default off)

- `HARNESS_MODEL=1` (+ `ANTHROPIC_API_KEY`) — small-model semantic recall booster (a Haiku
  selector over the vetted rule catalog; it never invents advice).

(The concept-gap quiz needs no knob — it fires automatically as a popup the moment you ask what a
term means. The old opt-in `HARNESS_QUIZ` / `.quiz-gate` mid-action gate was removed.)

## Use it on another project (not MiMo)

Default project is `mimo`. Point it at a new one:

```bash
echo myproj > ~/Trainlint/trainlint/.active-project   # or: export HARNESS_PROJECT=myproj
```

Then write the facts (mechanism unchanged — you only swap facts):
`trainlint/project.myproj.json` (action-rule facts), `trainlint/research/facts.myproj.json`,
`trainlint/research/knowledge.myproj.jsonl`, and an empty `trainlint/research/log.myproj.jsonl`.
See `trainlint/DESIGN.md` §10.

---

## ⚠️ Footgun (Form A only)

Never move/delete the script a settings.json hook points at without first making the new
path valid. A missing script makes `python3` exit 2, which Claude Code treats as a
**block** → every Bash/Edit/Write (incl. subagents) is denied, unrecoverable from inside
the session. Order: **new path exists → change settings → remove old.** Routing through the
stable symlink `~/trainlint` avoids this — future moves just re-point the symlink.

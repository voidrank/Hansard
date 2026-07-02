Bind THIS session to an existing project — the explicit switch for session-project-lock.

`/trainlint:use <name>` points the current session at a project WITHOUT touching any other session.
It's how you switch when the auto-resolver can't tell (you're chatting about project A while sitting
in repo B), and how an existing project gets its `home` stamped the first time you touch it.

Run:

    python3 "${CLAUDE_PLUGIN_ROOT}/research/use.py" <name> [--home DIR]

It (1) stamps the project's `home` = `--home`, else its existing home, else the current directory
(the context→project link); (2) writes this session's lock at `data_root()/sessions/<session_id>.json`
from `$CLAUDE_CODE_SESSION_ID`, keyed to the session so concurrent sessions never clobber; and
(3) transitionally — until the global `.active-project` is removed — also sets it, so the bind takes
effect immediately under the current resolver. Surface the confirmation line it prints.

Sticky + explicit: the session stays on this project until you run `/trainlint:use` again or
`/trainlint:plan <other>`. There is NO cwd auto-switch — moving directories mid-session never
silently retargets the compass.

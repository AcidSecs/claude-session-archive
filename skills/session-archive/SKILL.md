---
name: session-archive
description: Keep and search old Claude chats on the user's own PC. Use when the user says "archive my chats", "find what we decided in an old chat", "search my old sessions", or "file this note". OFF by default; only works when the Session Archive module is switched on.
---

# Session Archive

## Step 0: settings and warning
Read `Documents\ClaudeSetup\settings.json`. If `modules.session_archive` is not true, say "Session Archive is off. Say 'turn on session archive' to the Setup Wizard" and stop.
When turning it on, warn in plain words: **full chats are stored on your disk, word for word, in a folder you choose. Nothing is sent anywhere.** Ask for the folder (default `Documents\Claude_Session_Archive`) and save it as `paths.archive_folder`. Secrets such as keys and passwords are scrubbed when files are written.

## Needs
Python 3.8 or newer (command `python`). Nothing else to install: the tools use only Python's own library.

## Filing chats (user's own export)
1. User exports their data in claude.ai: Settings, Privacy, Export data. They get an email link to a zip.
2. User puts the zip in `<archive folder>\_incoming`.
3. Run: `python "<plugin folder>\skills\session-archive\tools\convert_export.py"` (it uses the newest zip in `_incoming`). Only new or changed chats are rewritten.
4. To file a single note (for example a handoff): `python convert_export.py --md FILE --project PROJECT --session SESSION`.
Chats are saved as folders: project, then session, then numbered parts of about 20 exchanges, plus an `INDEX.md`.

## Searching (cheap way, always)
Never open or list whole sessions. Do this:
1. `python search_archive.py "two or three key words"` (add `--project NAME` to narrow). It prints at most 5 short hits, each with a path.
2. Read only the best hit: `python search_archive.py --show "path from the hit"` (about 8000 characters; add `--offset N` for the next piece).
3. No good hit: try other words, find the session with `--sessions word`, or read that session's `index.md`. Still nothing: ask the user.

## Health check
On request: Python runs; archive folder exists and is writable; `archive.db` exists after the first filing; a test search returns. If something fails, search Anthropic's current docs, PROPOSE a fix, ASK before changing anything.

## Safety
Local files only. Never read the archive unless the user asked for a search. Never copy archive text to anywhere outside the user's PC.

## Guides for steps the user must do
Whenever the user must do a multi-step job themselves (connect an app, install something, request a download), do not write a long reply. Make a tick-box guide: copy `guide/GUIDE_TEMPLATE.html` (in this plugin's folder) to a new file in the user's Documents folder, change only the GUIDE object near the bottom, and follow the instructions at the top of the template. Make it extremely detailed: about five small steps for each real step, plain English, the reason in brackets, a copy chip for anything to type, and only the steps a human must do. Keep the chat reply short and point to the guide.

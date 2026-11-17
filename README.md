# Session Archive for Claude (vn-session-archive)

Switched OFF by default. Turn it on only if you want your old chats kept word for word on your own PC and searchable, so a new chat can find what you decided without you pasting old text.

## What it does
- Takes the data export you request yourself from claude.ai and files every chat as markdown: project folder, session folder, numbered parts of about 20 exchanges.
- Scrubs obvious secrets (private keys, API keys, tokens, passwords) while filing.
- Gives a small search tool: at most 5 short hits, then you open only the one part you need. This keeps usage low.

## Read this first
Full chats are stored on your disk in the folder you choose (default: Documents\Claude_Session_Archive). Nothing is sent anywhere. Delete the folder any time to remove it.

## What it needs
Python 3.8 or newer. No other packages (standard library only).

## What it runs
Two readable Python tools, stored in the plugin as `.txt` files so they cannot run by accident. Claude shows them to you and copies them into your archive folder only after you agree, and runs them only when you ask it to file or search. They read the export you placed in the archive folder and write inside the archive folder. They make no network connections.

## Part of a set
Switch it on or off with claude-setup-wizard.

Created by Soroosh Hedayat

Designed in Collaboration by: VectorNine Systems Inc. & Acid Secs Productions Inc.

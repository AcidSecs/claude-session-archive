#!/usr/bin/env python3
"""Turn a claude.ai data export (zip or conversations.json) into the Session Archive.

Usage (from any folder):
  python convert_export.py                      -> uses the newest export in ..\\_incoming
  python convert_export.py PATH_TO_ZIP_OR_JSON  -> uses that export
  python convert_export.py --md FILE --project PROJECT --session SESSION
                                                -> files a markdown note (for example a handoff)
Only new or changed chats are rewritten. Standard library only.
"""
import argparse, collections, datetime, io, json, os, re, sqlite3, sys, zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = os.path.dirname(os.path.abspath(__file__))
def default_root(tools):
    """Archive folder: env SESSION_ARCHIVE, else paths.archive_folder in Documents/ClaudeSetup/settings.json, else Documents/Claude_Session_Archive."""
    if os.environ.get("SESSION_ARCHIVE"):
        return os.environ["SESSION_ARCHIVE"]
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    try:
        s = json.load(open(os.path.join(docs, "ClaudeSetup", "settings.json"), encoding="utf-8"))
        if s.get("paths", {}).get("archive_folder"):
            return s["paths"]["archive_folder"]
    except (OSError, ValueError):
        pass
    return os.path.join(docs, "Claude_Session_Archive")
ROOT = default_root(TOOLS)
MAX_EXCH = 20      # exchanges (you + Claude) per part
MAX_CHARS = 12000  # characters per part
BIG = 20000        # one exchange longer than this is split

STOP = set("""this that with have from they will would there their what when which about were been your into than then them
also just like more some such only over very much many most other these those here where while does done doing make made
need needs want wants should could using used uses file files please thanks thank okay yes the and for are but not you all
can has had its it's let's don't i'm you're claude human assistant""".split())

SECRETS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "hf_[REDACTED]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|passcode|api[_ -]?key)\b(\s*[=:]\s*)(\S{4,})"), r"\1\2[REDACTED]"),
]


def scrub(t):
    for rx, rep in SECRETS:
        t = rx.sub(rep, t)
    return t


def safe(name):
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").replace(" | ", " - ")).strip(" .")
    return n[:80] or "Untitled"


def stamp(ts):
    return (ts or "")[:16].replace("T", " ")


def msg_text(m):
    c = m.get("content")
    parts = []
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                parts.append(b["text"])
    t = (m.get("text") or "") or "\n\n".join(parts)
    names = []
    for key in ("attachments", "files"):
        for a in m.get(key) or []:
            if isinstance(a, dict):
                n = a.get("file_name") or a.get("name")
                if n:
                    names.append(n)
    if names:
        t += "\n\n[attached: " + ", ".join(names) + "]"
    return scrub(t)


def exchanges_of(msgs):
    out, cur = [], []
    for m in msgs:
        if m["sender"] == "human" and cur:
            out.append(cur)
            cur = []
        cur.append(m)
    if cur:
        out.append(cur)
    return out


def render(m):
    who = {"human": "You", "assistant": "Claude"}.get(m["sender"], "Note")
    return "## %s (%s)\n\n%s\n\n" % (who, stamp(m["ts"]), m["text"].strip())


def split_big(text):
    pieces, cur = [], ""
    for para in text.split("\n\n"):
        while len(para) > BIG:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(para[:BIG])
            para = para[BIG:]
        if len(cur) + len(para) + 2 > BIG and cur:
            pieces.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        pieces.append(cur)
    return pieces


def build_parts(msgs):
    units = []
    for no, ex in enumerate(exchanges_of(msgs), 1):
        text = "".join(render(m) for m in ex)
        opener = next((m["text"] for m in ex if m["sender"] == "human"), ex[0]["text"])
        opener = re.sub(r"\s+", " ", opener).strip()[:110]
        for p in ([text] if len(text) <= BIG else split_big(text)):
            units.append((no, p, ex[0]["ts"], ex[-1]["ts"], opener))
    parts, cur = [], []
    for u in units:
        chars = sum(len(x[1]) for x in cur)
        n_ex = len({x[0] for x in cur})
        new_ex = bool(cur) and u[0] != cur[-1][0]
        if cur and ((n_ex >= MAX_EXCH and new_ex) or chars + len(u[1]) > MAX_CHARS):
            parts.append(cur)
            cur = []
        cur.append(u)
    if cur:
        parts.append(cur)
    return parts


def keywords(text, n=8):
    words = re.findall(r"[a-z][a-z0-9_]{3,}", text.lower())
    c = collections.Counter(w for w in words if w not in STOP)
    return [w for w, _ in c.most_common(n)]


def paths_in(text, n=3):
    seen = []
    for p in re.findall(r"[A-Za-z]:\\[^\s\"'`<>|*?]{3,60}", text):
        p = p.rstrip(".,;:)")
        if p not in seen:
            seen.append(p)
        if len(seen) >= n:
            break
    return seen


def db_connect():
    con = sqlite3.connect(os.environ.get("SESSION_ARCHIVE_DB") or os.path.join(ROOT, "archive.db"))
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS parts USING fts5("
        "key UNINDEXED, project, session, part UNINDEXED, path UNINDEXED, dates UNINDEXED, text, "
        "tokenize='porter unicode61')"
    )
    return con


def write_session(con, state, folder_rel, project, session, msgs):
    """Write all parts + index.md for one session; refresh the search table."""
    folder = os.path.join(ROOT, *folder_rel.split("/"))
    os.makedirs(folder, exist_ok=True)
    parts = build_parts(msgs)
    con.execute("DELETE FROM parts WHERE key=?", (folder_rel,))
    lines = []
    first = stamp(msgs[0]["ts"])
    last = stamp(msgs[-1]["ts"])
    for i, part in enumerate(parts, 1):
        fname = "part_%03d.md" % i
        body = "".join(u[1] for u in part)
        ex_lo, ex_hi = part[0][0], part[-1][0]
        d0, d1 = stamp(part[0][2]), stamp(part[-1][3])
        head = "# %s - part %03d\n\nProject: %s | Dates (UTC): %s to %s | Exchanges: %d-%d\n\n" % (
            session, i, project, d0, d1, ex_lo, ex_hi)
        with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
            f.write(head + body)
        kw = keywords(body)
        pth = paths_in(body)
        lines.append("- %s | %s | keywords: %s | opens: %s%s" % (
            fname, d0[:10], ", ".join(kw), part[0][4],
            (" | paths: " + "; ".join(pth)) if pth else ""))
        con.execute("INSERT INTO parts(key,project,session,part,path,dates,text) VALUES (?,?,?,?,?,?,?)",
                    (folder_rel, project, session, fname, folder_rel + "/" + fname, d0 + " to " + d1, body))
    with open(os.path.join(folder, "index.md"), "w", encoding="utf-8") as f:
        f.write("# %s\n\nProject: %s | %s to %s | %d parts. One line per part. Open only the part you need.\n\n%s\n" % (
            session, project, first, last, len(parts), "\n".join(lines)))
    state["sessions"][folder_rel] = {"project": project, "session": session, "first": first,
                                     "last": last, "parts": len(parts)}
    return len(parts)


def write_master(state, note):
    rows = sorted(state["sessions"].items(), key=lambda kv: (kv[1]["project"].lower(), kv[1]["session"].lower()))
    out = ["# Session Archive - master index", "",
           "Last update: %s. %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), note),
           "The archive is only as fresh as the last export or note filed. Newer facts come from handoff files and the ledgers.",
           "Search: python search_archive.py \"key words\"   (see README.md)", "",
           "One line per session: project :: session :: first to last date :: parts :: folder", ""]
    for k, v in rows:
        out.append("- %s :: %s :: %s to %s :: %d parts :: %s" % (v["project"], v["session"], v["first"][:10],
                                                          v["last"][:10], v["parts"], k))
    with open(os.path.join(ROOT, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def load_state():
    p = os.path.join(ROOT, "_state.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            s = json.load(f)
    else:
        s = {}
    s.setdefault("convs", {})
    s.setdefault("folders", {})
    s.setdefault("sessions", {})
    return s


def save_state(s):
    with open(os.path.join(ROOT, "_state.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


def newest_export():
    inc = os.path.join(ROOT, "_incoming")
    cands = []
    for n in os.listdir(inc):
        p = os.path.join(inc, n)
        if n.startswith(("_", "manifest")):
            continue
        if n.lower().endswith((".zip", ".json")) or os.path.isdir(p):
            cands.append(p)
    if not cands:
        sys.exit("Nothing found in " + inc + ". Put the export zip there.")
    return max(cands, key=os.path.getmtime)


def iter_json_array(f, chunk=1 << 20):
    """Yield the items of a huge JSON array one by one (never loads the whole file)."""
    dec = json.JSONDecoder()
    buf = ""
    eof = False

    def more():
        nonlocal buf, eof
        s = f.read(chunk)
        if not s:
            eof = True
        else:
            buf += s

    while not buf.lstrip().startswith("["):
        if eof:
            raise ValueError("conversations file is not a JSON list")
        more()
    buf = buf.lstrip()[1:]
    while True:
        buf = buf.lstrip(" \r\n\t,")
        if not buf:
            if eof:
                return
            more()
            continue
        if buf[0] == "]":
            return
        try:
            obj, end = dec.raw_decode(buf)
        except json.JSONDecodeError:
            if eof:
                raise
            more()
            continue
        yield obj
        buf = buf[end:]


def projects_near(path):
    """Project names from projects*.zip or projects.json next to the export, if present."""
    pmap = {}
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        names = os.listdir(folder)
    except OSError:
        return pmap
    for n in names:
        if not n.lower().startswith("projects"):
            continue
        p = os.path.join(folder, n)
        try:
            if n.lower().endswith(".zip"):
                with zipfile.ZipFile(p) as z:
                    for m in z.namelist():
                        if os.path.basename(m) == "projects.json":
                            data = json.loads(z.read(m).decode("utf-8"))
                            break
                    else:
                        continue
            elif n.lower().endswith(".json"):
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                continue
        except Exception:
            continue
        if isinstance(data, list):
            for pr in data:
                if isinstance(pr, dict) and pr.get("uuid"):
                    pmap[pr["uuid"]] = pr.get("name") or ""
    return pmap


def read_export(path):
    pmap = projects_near(path)
    if os.path.isdir(path):
        f = open(os.path.join(path, "conversations.json"), encoding="utf-8")
    elif path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        names = {os.path.basename(n): n for n in z.namelist()}
        if "conversations.json" not in names:
            sys.exit("conversations.json not found in the zip. Files inside: " + ", ".join(list(names)[:20]))
        f = io.TextIOWrapper(z.open(names["conversations.json"]), encoding="utf-8")
    else:
        f = open(path, encoding="utf-8")
    return iter_json_array(f), pmap


def project_and_session(c, pmap):
    name = (c.get("name") or "").strip()
    if not name:
        name = "Untitled " + stamp(c.get("created_at"))[:10]
    if " | " in name:
        return name.split(" | ", 1)[0].strip(), name
    pu = c.get("project_uuid")
    if not pu and isinstance(c.get("project"), dict):
        pu = c["project"].get("uuid")
    return (pmap.get(pu) or "_Unsorted"), name


def convert_export(path):
    convs, pmap = read_export(path)
    state = load_state()
    con = db_connect()
    new = changed = skipped = 0
    newest = ""
    for c in convs:
        msgs = []
        for m in c.get("chat_messages") or []:
            t = msg_text(m)
            if t.strip():
                msgs.append({"sender": m.get("sender", "assistant"), "ts": m.get("created_at") or "", "text": t})
        if not msgs:
            continue
        uid = c.get("uuid") or c.get("name")
        upd = c.get("updated_at") or msgs[-1]["ts"]
        newest = max(newest, upd)
        old = state["convs"].get(uid)
        if old and old["updated"] == upd and old["msgs"] == len(msgs):
            skipped += 1
            continue
        project, session = project_and_session(c, pmap)
        if old:
            folder_rel = old["folder"]
            changed += 1
        else:
            folder_rel = safe(project) + "/" + safe(session)
            if state["folders"].get(folder_rel, uid) != uid:
                folder_rel += "_" + str(uid)[:6]
            new += 1
        state["folders"][folder_rel] = uid
        write_session(con, state, folder_rel, project, session, msgs)
        state["convs"][uid] = {"updated": upd, "msgs": len(msgs), "folder": folder_rel}
    con.commit()
    con.close()
    save_state(state)
    write_master(state, "Export file: %s. Newest chat in it: %s UTC." % (os.path.basename(path), stamp(newest)))
    print("Done. New sessions: %d, changed: %d, unchanged: %d. Archive: %s" % (new, changed, skipped, ROOT))


def add_markdown(path, project, session):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = scrub(f.read())
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    state = load_state()
    con = db_connect()
    folder_rel = safe(project) + "/" + safe(session)
    msgs = [{"sender": "note", "ts": now, "text": text}]
    n = write_session(con, state, folder_rel, project, session, msgs)
    con.commit()
    con.close()
    save_state(state)
    write_master(state, "Note filed: %s." % os.path.basename(path))
    print("Filed %s as %s/%s (%d parts)." % (os.path.basename(path), project, session, n))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", nargs="?", help="export zip, folder or conversations.json (default: newest in _incoming)")
    ap.add_argument("--md", help="markdown file to file as a note")
    ap.add_argument("--project", default="_Unsorted")
    ap.add_argument("--session", default="Notes")
    a = ap.parse_args()
    if a.md:
        add_markdown(a.md, a.project, a.session)
    else:
        convert_export(a.export or newest_export())


if __name__ == "__main__":
    main()

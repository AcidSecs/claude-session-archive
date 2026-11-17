#!/usr/bin/env python3
"""Search the Session Archive without filling your context window.

  python search_archive.py "key words" [-n 5] [--project NAME]   -> at most n short hits, each with a path
  python search_archive.py --sessions word                       -> sessions whose name/project match (max 10 lines)
  python search_archive.py --show "Project/Session/part_003.md" [--offset 0] [--max 8000]
                                                                 -> prints ONE part, capped (default 8000 characters)
"""
import argparse, json, os, re, sqlite3, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
ROOT = default_root(None)


def search(q, n, project):
    db = os.environ.get("SESSION_ARCHIVE_DB") or os.path.join(ROOT, "archive.db")
    if not os.path.exists(db):
        sys.exit("No archive yet. Run convert_export.py first.")
    words = re.findall(r"[A-Za-z0-9_]+", q)
    if not words:
        sys.exit("Give at least one word.")
    con = sqlite3.connect(db)
    sql = ("SELECT project, session, part, path, dates, snippet(parts, 6, '[', ']', ' ... ', 22) "
           "FROM parts WHERE parts MATCH ?" + (" AND project = ?" if project else "") + " ORDER BY bm25(parts) LIMIT ?")
    rows = []
    for joiner in (" ", " OR "):
        mq = joiner.join('"%s"' % w for w in words)
        args = [mq] + ([project] if project else []) + [n]
        try:
            rows = con.execute(sql, args).fetchall()
        except sqlite3.OperationalError as e:
            sys.exit("Search error: %s" % e)
        if rows:
            break
    if not rows:
        print("No hits. Try other words, fewer words, or --sessions word.")
        return
    for i, (pr, se, part, path, dates, snip) in enumerate(rows, 1):
        snip = re.sub(r"\s+", " ", snip)[:240]
        print("%d. %s | %s | %s | %s\n   path: %s\n   %s" % (i, pr, se, part, dates[:10], path, snip))
    print("Next: python search_archive.py --show \"<path of the best hit>\"")


def sessions(word):
    p = os.path.join(ROOT, "INDEX.md")
    if not os.path.exists(p):
        sys.exit("No INDEX.md yet.")
    hits = [l.rstrip() for l in open(p, encoding="utf-8") if l.startswith("- ") and word.lower() in l.lower()]
    for l in hits[:10]:
        print(l)
    if not hits:
        print("No session matches.")
    elif len(hits) > 10:
        print("(%d more; use a longer word)" % (len(hits) - 10))


def show(rel, offset, mx):
    full = os.path.realpath(os.path.join(ROOT, *rel.replace("\\", "/").split("/")))
    if not full.startswith(os.path.realpath(ROOT)) or not os.path.isfile(full):
        sys.exit("Path not found inside the archive: " + rel)
    text = open(full, encoding="utf-8").read()
    chunk = text[offset:offset + mx]
    print(chunk)
    end = offset + len(chunk)
    if end < len(text):
        print("\n[showing characters %d-%d of %d; next: --offset %d]" % (offset, end, len(text), end))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--project")
    ap.add_argument("--sessions")
    ap.add_argument("--show")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--max", type=int, default=8000)
    a = ap.parse_args()
    if a.show:
        show(a.show, a.offset, a.max)
    elif a.sessions:
        sessions(a.sessions)
    elif a.query:
        search(a.query, min(max(a.n, 1), 10), a.project)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

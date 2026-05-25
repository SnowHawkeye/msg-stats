#!/usr/bin/env python3
"""
generate-stats.py — Obsidian vault stats generator
Usage:  python3 generate-stats.py [vault_path] [output_json]

Defaults:
  vault_path  = current directory
  output_json = <script_dir>/vault-stats.json

Reads vault-stats-template.html, injects stats, writes vault-stats.html, and opens it.
Run this script (or add it to a git post-commit hook) then open vault-stats.html.
"""

import subprocess, json, sys, os, tarfile, io, re, webbrowser
from datetime import datetime, date
from pathlib import Path
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────────────
VAULT      = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('.').resolve()
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT     = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else SCRIPT_DIR / 'vault-stats.json'
WORDS_PER_PAGE      = 250  # manuscript page estimate

# ── Helpers ───────────────────────────────────────────────────────────────────
def git(*args, **kw):
    return subprocess.run(['git'] + list(args), capture_output=True, text=True, **kw)

def git_bytes(*args):
    return subprocess.run(['git'] + list(args), capture_output=True)

def words_in(text: str) -> int:
    return len(text.split())

# ── Sanity check ──────────────────────────────────────────────────────────────
os.chdir(VAULT)
if not (VAULT / '.git').exists():
    print(f"❌  {VAULT} is not a git repository.")
    sys.exit(1)

print(f"📖  Vault : {VAULT}")
print(f"📄  Output: {OUTPUT}")

# ── 1. Current stats ──────────────────────────────────────────────────────────
print("\n① Current stats …")

md_files = [
    f for f in VAULT.rglob('*.md')
    if '.git' not in f.parts and '.trash' not in f.parts
]
folders = [
    d for d in VAULT.rglob('*')
    if d.is_dir()
    and '.git' not in d.parts
    and '.trash' not in d.parts
    and not any(part.startswith('.') for part in d.parts[len(VAULT.parts):])
]

total_words = total_lines = total_chars = 0
file_words = {}   # relative path str → word count
for f in md_files:
    try:
        text = f.read_text(encoding='utf-8', errors='ignore')
        wc = words_in(text)
        total_words += wc
        total_lines += text.count('\n') + 1
        total_chars += len(text)
        rel = str(f.relative_to(VAULT))
        file_words[rel] = wc
    except Exception:
        pass

def build_tree(node_path: Path, rel_parts: tuple) -> dict:
    """Recursively build a tree node for a directory."""
    children = []
    total = 0
    # subdirectories (non-dot)
    try:
        subdirs = sorted(
            d for d in node_path.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        )
    except PermissionError:
        subdirs = []
    for subdir in subdirs:
        child = build_tree(subdir, rel_parts + (subdir.name,))
        total += child['words']
        children.append(child)
    # markdown files in this directory
    try:
        files = sorted(
            f for f in node_path.iterdir()
            if f.is_file() and f.suffix == '.md'
        )
    except PermissionError:
        files = []
    for f in files:
        rel = str(f.relative_to(VAULT))
        wc = file_words.get(rel, 0)
        total += wc
        children.append({'name': f.stem, 'type': 'file', 'words': wc})
    return {
        'name':     node_path.name or str(node_path),
        'type':     'folder',
        'words':    total,
        'children': children,
    }

file_tree = build_tree(VAULT, ())

current = {
    'words':            total_words,
    'lines':            total_lines,
    'chars':            total_chars,
    'files':            len(md_files),
    'folders':          len(folders),
    'manuscript_pages': total_words // WORDS_PER_PAGE,
}
print(f"   {total_words:,} words  ·  {len(md_files)} notes  ·  {len(folders)} folders")

# ── 2. File event history ─────────────────────────────────────────────────────
print("\n② File event history …")

log = git('log',
          '--diff-filter=ADRM',
          '--name-status',
          '--format=COMMIT|%ai|%s',
          '--', '*.md')

def is_dot_path(path_str):
    return any(part.startswith('.') for part in Path(path_str).parts)

file_events = []
cur_date = cur_msg = ''
for line in log.stdout.splitlines():
    if line.startswith('COMMIT|'):
        parts = line.split('|', 2)
        cur_date = parts[1][:10]
        cur_msg  = parts[2].strip() if len(parts) > 2 else ''
    elif not line.strip():
        continue
    elif line[0] in 'ADM' and '\t' in line:
        status, path = line.split('\t', 1)
        path = path.strip()
        if path.endswith('.md') and not is_dot_path(path):
            file_events.append({
                'date':    cur_date,
                'type':    status.strip(),     # A=added, D=deleted, M=modified
                'file':    path,
                'message': cur_msg,
            })
    elif line[0] == 'R' and '\t' in line:
        parts = line.split('\t')
        if len(parts) >= 3 and parts[2].strip().endswith('.md') and not is_dot_path(parts[2].strip()):
            file_events.append({
                'date':     cur_date,
                'type':     'R',               # renamed/moved
                'file':     parts[2].strip(),
                'old_file': parts[1].strip(),
                'message':  cur_msg,
            })

# Deduplicate (same file + date + type)
seen = set()
unique_events = []
for e in file_events:
    key = (e['date'], e['type'], e['file'])
    if key not in seen:
        seen.add(key)
        unique_events.append(e)

file_events = unique_events
print(f"   {len(file_events)} events (added / modified / renamed / deleted)")

# ── 3. Word-count history ─────────────────────────────────────────────────────
print(f"\n③ Word-count history (all days with commits) …")

log2 = git('log', '--format=%ai|%H')
commits = []
for line in log2.stdout.strip().splitlines():
    if '|' in line:
        d, h = line.split('|', 1)
        commits.append((d[:10], h.strip()))

# One commit per calendar day (most recent of that day)
by_day = {}
for d, h in commits:
    if d not in by_day:
        by_day[d] = h
days_sorted = sorted(by_day.items())   # oldest → newest

word_history = []
for idx, (d, h) in enumerate(days_sorted):
    print(f"   [{idx+1:>3}/{len(days_sorted)}] {d}", end='\r', flush=True)
    try:
        ls   = git('ls-tree', '-r', '--name-only', h)
        mds  = [f for f in ls.stdout.strip().splitlines() if f.endswith('.md')]
        if not mds:
            word_history.append({'date': d, 'words': 0})
            continue

        arch = git_bytes('archive', h, *mds)
        total = 0
        with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
            for member in tf.getmembers():
                fobj = tf.extractfile(member)
                if fobj:
                    total += words_in(fobj.read().decode('utf-8', errors='ignore'))
        word_history.append({'date': d, 'words': total})
    except Exception:
        pass

print(f"\n   {len(word_history)} data points collected")

# ── 4. Writing-streak & productivity ─────────────────────────────────────────
print("\n④ Streak & productivity …")

commit_dates = sorted({d for d, _ in commits})   # unique calendar days

def compute_streak(dates_asc):
    if not dates_asc:
        return 0, 0
    from datetime import timedelta
    dates = [date.fromisoformat(d) for d in dates_asc]
    today  = date.today()
    # Current streak
    cur = 0
    check = today
    for d in reversed(dates):
        if d == check or d == check - __import__('datetime').timedelta(days=1 if cur > 0 else 0):
            if d <= check:
                cur += 1
                check = d - __import__('datetime').timedelta(days=1)
        else:
            break
    # Longest streak
    best = streak = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            streak += 1
            best = max(best, streak)
        else:
            streak = 1
    return cur, best

current_streak, best_streak = compute_streak(commit_dates)

# Weekday distribution — total word delta per weekday
weekday_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
weekday_words = Counter()
for i in range(1, len(word_history)):
    delta = word_history[i]['words'] - word_history[i-1]['words']
    if delta > 0:
        wd_name = date.fromisoformat(word_history[i]['date']).strftime('%A')
        weekday_words[wd_name] += delta
weekday_data  = [{'day': d, 'words': weekday_words.get(d, 0)} for d in weekday_order]

# Daily word deltas (difference between consecutive history points)
daily_deltas = []
for i in range(1, len(word_history)):
    delta = word_history[i]['words'] - word_history[i-1]['words']
    if delta > 0:
        daily_deltas.append(delta)

def median(lst):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    return int((s[n // 2] + s[(n - 1) // 2]) / 2)

median_words_per_session = median(daily_deltas)
total_commits = len(commits)

productivity = {
    'current_streak':           current_streak,
    'best_streak':              best_streak,
    'total_writing_days':       len(commit_dates),
    'total_commits':            total_commits,
    'median_words_per_session': median_words_per_session,
    'weekday_activity':         weekday_data,
}
print(f"   Streak: {current_streak} days  ·  Best: {best_streak} days")

# ── 5. Assemble & write ───────────────────────────────────────────────────────
data = {
    'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    'vault_path':   str(VAULT),
    'current':      current,
    'file_events':  file_events,
    'word_history': word_history,
    'productivity': productivity,
    'file_tree':    file_tree,
}

OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(f"\n✅  Stats written to {OUTPUT}")

# ── 6. Inject into HTML and open ──────────────────────────────────────────────
HTML_TEMPLATE = SCRIPT_DIR / 'vault-stats-template.html'
HTML_OUTPUT   = SCRIPT_DIR / 'vault-stats.html'
if HTML_TEMPLATE.exists():
    html = HTML_TEMPLATE.read_text(encoding='utf-8')
    html = re.sub(
        r'const __STATS__ = .*?/\* STATS_INJECT \*/',
        f'const __STATS__ = {json.dumps(data, ensure_ascii=False)}; /* STATS_INJECT */',
        html, flags=re.DOTALL
    )
    HTML_OUTPUT.write_text(html, encoding='utf-8')
    print(f"💉  Data injected into {HTML_OUTPUT}")
    webbrowser.open(HTML_OUTPUT.as_uri())
    print("🌐  Opening vault-stats.html …")
else:
    print(f"⚠️   {HTML_TEMPLATE} not found — open it manually alongside vault-stats.json")

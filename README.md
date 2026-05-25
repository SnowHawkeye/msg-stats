# msg-stats

Word count and writing activity dashboard for a git-tracked Obsidian vault.

## Features

- Total words, pages, notes, folders, lines, characters
- Median words per writing session
- Word count over time (filterable: All / 6M / 3M / 1M / 1W)
- Writing streak (current & best), days writing, total commits
- Words written per weekday — synced to the same time filter as the chart
- File history (Added / Modified / Moved / Deleted) with per-type filtering

## Requirements

- Python 3 (stdlib only — no installs needed)
- An Obsidian vault tracked with git

## Usage

```bash
python3 generate-stats.py /path/to/your/vault
```

This will:
1. Scan the vault and compute stats from git history
2. Inject the data into `vault-stats.html` (generated from the template)
3. Open the dashboard in your default browser

The HTML is self-contained — no server needed.  
`vault-stats.json` is also written alongside the script as a plain-text backup.

### zshrc shortcut

```zsh
msg-stats() {
    python3 "/path/to/msg-stats/generate-stats.py" \
        "$HOME/path/to/your/vault"
}
```

## Files

| File | Purpose |
|------|---------|
| `generate-stats.py` | Generates stats and produces the dashboard |
| `vault-stats-template.html` | Dashboard template (no data — safe to commit) |
| `vault-stats.html` | Generated dashboard with injected data (gitignored) |
| `vault-stats.json` | Last-generated data snapshot (gitignored) |

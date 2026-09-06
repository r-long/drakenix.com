#!/usr/bin/env python3
"""
update_projects.py

Refreshes data/projects.json with live GitHub metadata, then regenerates
the projects section of index.html from the JSON source of truth.

Usage:
    python scripts/update_projects.py [--dry-run]

Env:
    GH_TOKEN  GitHub personal access token (needs repo scope for private repos)
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_JSON = REPO_ROOT / "data" / "projects.json"
INDEX_HTML = REPO_ROOT / "index.html"

GH_TOKEN = os.environ.get("GH_TOKEN", "")
DRY_RUN = "--dry-run" in sys.argv

# ── GitHub API helpers ────────────────────────────────────────────────────────

def gh_get(path: str) -> dict | None:
    url = f"https://api.github.com/{path.lstrip('/')}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if GH_TOKEN:
        req.add_header("Authorization", f"Bearer {GH_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  GitHub API {e.code} for {path}: {e.reason}")
        return None
    except Exception as e:
        print(f"  GitHub API error for {path}: {e}")
        return None


def fetch_repo_meta(repo_full_name: str) -> dict | None:
    return gh_get(f"repos/{repo_full_name}")


def fetch_account_repos(username: str) -> list[str]:
    """Return list of repo full names for the account (public + private with token)."""
    repos = []
    page = 1
    while True:
        data = gh_get(f"users/{username}/repos?per_page=100&page={page}&sort=pushed")
        if not data:
            break
        repos.extend(r["full_name"] for r in data)
        if len(data) < 100:
            break
        page += 1
    return repos

# ── HTML generation ───────────────────────────────────────────────────────────

COLOR_TO_CSS = {
    "orange": "var(--orange-dim)",
    "accent": "var(--accent-dim)",
    "green": "var(--green-dim)",
    "blue": "var(--blue-dim)",
    "red": "var(--red-dim)",
}

def fmt_relative_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = (now - dt).days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        years = months // 12
        return f"{years}y ago"
    except Exception:
        return None


def render_project(p: dict) -> str:
    color = COLOR_TO_CSS.get(p.get("icon_color", "accent"), "var(--accent-dim)")
    tags_html = "\n            ".join(
        f'<span class="project-tag {style}">{tag}</span>'
        for tag, style in zip(p.get("tags", []), p.get("tag_styles", []))
    )
    stack_html = "\n            ".join(
        f'<span class="stack-pill">{item}</span>'
        for item in p.get("stack", [])
    )

    last_active = fmt_relative_date(p.get("last_pushed_at"))
    active_badge = (
        f'\n          <div class="project-active">Active {last_active}</div>'
        if last_active else ""
    )

    article_link = ""
    if p.get("article_url"):
        article_link = f'''
          <a href="{p["article_url"]}" class="project-link">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            Read article
          </a>'''

    github_link = ""
    if p.get("github_public") and p.get("github_url"):
        github_link = f'''
          <a href="{p["github_url"]}" target="_blank" rel="noopener" class="project-link">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            View on GitHub
          </a>'''

    return f'''        <div class="project">
          <div class="project-header">
            <div class="project-icon" style="background: {color};">{p.get("icon", "")}</div>
            <div class="project-name">{p["name"]}</div>
            <div class="project-tags">
            {tags_html}
            </div>
          </div>
          <p class="project-desc">{p["description"]}</p>
          <div class="project-stack">
            {stack_html}
          </div>{active_badge}{article_link}{github_link}
        </div>'''


def render_projects_section(data: dict) -> str:
    parts = []
    for cat in data["categories"]:
        parts.append(
            f'      <div class="category-label">{cat["label"]}</div>\n'
            f'      <div class="projects">'
        )
        for p in cat["projects"]:
            parts.append(render_project(p))
        parts.append("      </div>")
    return "\n\n".join(parts)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading projects.json…")
    data = json.loads(PROJECTS_JSON.read_text())

    known_repos = set()
    changed = False

    print("Fetching GitHub metadata…")
    for cat in data["categories"]:
        for project in cat["projects"]:
            repo = project.get("github_repo")
            if not repo:
                continue
            known_repos.add(repo)
            print(f"  {repo}…", end=" ", flush=True)
            meta = fetch_repo_meta(repo)
            if meta:
                new_pushed = meta.get("pushed_at")
                if new_pushed != project.get("last_pushed_at"):
                    project["last_pushed_at"] = new_pushed
                    changed = True
                    print(f"updated ({new_pushed[:10] if new_pushed else 'null'})")
                else:
                    print("unchanged")
            else:
                print("skipped (no access or not found)")

    # Check for new repos not yet in the portfolio
    print("\nChecking for new repos…")
    account_repos = fetch_account_repos("r-long")
    IGNORE_REPOS = {
        "r-long/r-long.github.io", "r-long/node-todo",
        "r-long/SecretaryOfLabor", "r-long/autocomplete-netsuite",
        "r-long/NRA-DEV",  # private, unrelated
    }
    new_repos = [
        r for r in account_repos
        if r not in known_repos and r not in IGNORE_REPOS
        and not r.startswith("r-long/drakenix")
    ]
    if new_repos:
        print(f"  ⚠️  New repos detected (not yet in portfolio): {new_repos}")
        data["meta"]["new_repos_detected"] = new_repos
        changed = True
    else:
        print("  No new repos detected.")
        data["meta"]["new_repos_detected"] = []

    data["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()

    if not changed:
        print("\nNo changes — nothing to commit.")
        return

    if DRY_RUN:
        print("\n[dry-run] Would write projects.json and regenerate index.html")
        return

    # Write updated JSON
    print("\nWriting projects.json…")
    PROJECTS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    # Regenerate the projects section in index.html
    print("Regenerating projects section in index.html…")
    html = INDEX_HTML.read_text()
    new_projects_html = render_projects_section(data)

    # Replace everything between the START/END markers
    pattern = re.compile(
        r"(<!-- PROJECTS:START -->).*?(<!-- PROJECTS:END -->)",
        re.DOTALL,
    )
    replacement = f"<!-- PROJECTS:START -->\n{new_projects_html}\n      <!-- PROJECTS:END -->"
    if pattern.search(html):
        new_html = pattern.sub(replacement, html)
        INDEX_HTML.write_text(new_html)
        print("  Projects section updated via markers.")
    else:
        print("  ⚠️  PROJECTS:START/END markers not found in index.html — skipping HTML update.")
        print("       Add <!-- PROJECTS:START --> and <!-- PROJECTS:END --> around the projects section.")

    print("\nDone.")
    if new_repos:
        print(f"\n⚠️  ACTION NEEDED: {len(new_repos)} new repo(s) detected that aren't in the portfolio:")
        for r in new_repos:
            print(f"   - {r}")
        print("   Review them and add to data/projects.json if they belong on the site.")


if __name__ == "__main__":
    main()

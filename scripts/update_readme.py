"""Regenerate the dynamic parts of the profile README.

Fills the blocks between <!-- NAME:START --> and <!-- NAME:END --> markers
and writes assets/languages.svg. Standard library only.

Env:
  GH_USER          GitHub login (default: Bastien-Gaffet)
  GH_TOKEN         token for the API (GITHUB_TOKEN is enough for public data)
  INCLUDE_PRIVATE  "1" to count private repos in the language chart; needs a
                   personal token with read access. Only aggregated byte
                   counts are published, never private repo names.
"""

import datetime as dt
import html
import json
import os
import re
import urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER", "Bastien-Gaffet")
TOKEN = os.environ.get("GH_TOKEN", "")
INCLUDE_PRIVATE = os.environ.get("INCLUDE_PRIVATE") == "1"
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SVG = ROOT / "assets" / "languages.svg"

# Repos left out of every list (the profile repo itself, school notes...).
EXCLUDE = {USER.lower()}

# GitHub linguist colours for the languages likely to show up.
COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Java": "#b07219", "HTML": "#e34c26", "CSS": "#663399",
    "Shell": "#89e051", "TeX": "#3D6117", "C": "#555555", "C++": "#f34b7d",
    "Go": "#00ADD8", "Kotlin": "#A97BFF", "Vue": "#41b883",
    "Svelte": "#ff3e00", "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384d54",
    "PowerShell": "#012456", "Lua": "#000080", "C#": "#178600",
}
# Generated or vendored code that would skew the chart.
IGNORED_LANGS = {"Jupyter Notebook"}

MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
          "sept.", "oct.", "nov.", "déc."]


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_date(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fr_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def relative(d, now):
    days = (now - d).days
    if days <= 0:
        return "aujourd'hui"
    if days == 1:
        return "hier"
    if days < 30:
        return f"il y a {days} jours"
    if days < 365:
        return f"il y a {days // 30} mois"
    return f"il y a {days // 365} an{'s' if days >= 730 else ''}"


def public_repos():
    repos = api(f"/users/{USER}/repos?per_page=100&type=owner&sort=pushed")
    return [r for r in repos
            if not r["fork"] and not r["archived"]
            and r["name"].lower() not in EXCLUDE]


def language_repos(public):
    if not INCLUDE_PRIVATE:
        return public
    repos = api("/user/repos?per_page=100&affiliation=owner")
    return [r for r in repos
            if not r["fork"] and r["name"].lower() not in EXCLUDE]


def language_totals(repos):
    totals = {}
    for r in repos:
        for lang, size in api(f"/repos/{r['full_name']}/languages").items():
            if lang not in IGNORED_LANGS:
                totals[lang] = totals.get(lang, 0) + size
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def render_svg(langs, top=8):
    total = sum(size for _, size in langs) or 1
    shown = langs[:top]
    rest = total - sum(size for _, size in shown)
    if rest > 0:
        shown.append(("Autres", rest))

    width, bar_y, bar_h = 480, 34, 10
    parts, x = [], 0.0
    for lang, size in shown:
        w = width * size / total
        color = COLORS.get(lang, "#8b949e")
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" '
                     f'height="{bar_h}" fill="{color}"/>')
        x += w

    legend, cols, row_h = [], 2, 22
    for i, (lang, size) in enumerate(shown):
        cx = (i % cols) * (width / cols)
        cy = bar_y + bar_h + 26 + (i // cols) * row_h
        color = COLORS.get(lang, "#8b949e")
        pct = 100 * size / total
        legend.append(
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
            f'<text x="{cx + 16}" y="{cy}" class="l">{lang}</text>'
            f'<text x="{cx + width / cols - 16}" y="{cy}" class="p" '
            f'text-anchor="end">{pct:.1f} %</text>')

    height = bar_y + bar_h + 26 + ((len(shown) + 1) // cols) * row_h
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Répartition des langages">
<style>
  text {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #1f2328; }}
  .t {{ font-size: 14px; font-weight: 600; }}
  .p {{ fill: #59636e; font-variant-numeric: tabular-nums; }}
  @media (prefers-color-scheme: dark) {{
    text {{ fill: #f0f6fc; }}
    .p {{ fill: #9198a1; }}
  }}
</style>
<text x="0" y="16" class="t">Langages</text>
<clipPath id="r"><rect x="0" y="{bar_y}" width="{width}" height="{bar_h}" rx="5"/></clipPath>
<g clip-path="url(#r)">{''.join(parts)}</g>
{''.join(legend)}
</svg>
"""


def render_activity(repos, now, limit=5):
    lines = []
    for r in repos[:limit]:
        when = relative(parse_date(r["pushed_at"]), now)
        try:
            commit = api(f"/repos/{r['full_name']}/commits?per_page=1")[0]
            msg = commit["commit"]["message"].splitlines()[0].strip()
            msg = msg if len(msg) <= 72 else msg[:69].rstrip() + "..."
            detail = f'<a href="{commit["html_url"]}"><code>{html.escape(msg)}</code></a>'
        except Exception:
            detail = html.escape(r["description"] or "")
        lines.append(f'- <a href="{r["html_url"]}"><b>{r["name"]}</b></a> '
                     f'&middot; {when} &middot; {detail}')
    return "\n".join(lines)


def render_stats(repos, now):
    stars = sum(r["stargazers_count"] for r in repos)
    return (f"<sub>{len(repos)} dépôts publics &middot; {stars} étoiles "
            f"&middot; mis à jour automatiquement le {fr_date(now)}</sub>")


def replace_block(text, name, content):
    pattern = re.compile(
        rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"marker {name} missing from README.md")
    return pattern.sub(lambda m: f"{m[1]}\n{content}\n{m[3]}", text)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    repos = public_repos()

    SVG.parent.mkdir(exist_ok=True)
    SVG.write_text(render_svg(language_totals(language_repos(repos))),
                   encoding="utf-8")

    text = README.read_text(encoding="utf-8")
    text = replace_block(text, "ACTIVITY", render_activity(repos, now))
    text = replace_block(text, "STATS", render_stats(repos, now))
    README.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

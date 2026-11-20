"""Build both profile cards from GitHub's public language-byte counts. No dependencies."""
import html
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'rs-an'
COLORS = {
    'Swift': ('#F05138', '#F05138'),
    'JavaScript': ('#f1e05a', '#f1e05a'),
    'Python': ('#3572A5', '#3572A5'),
    'CSS': ('#663399', '#663399'),
    'Shell': ('#89e051', '#89e051'),
    'HTML': ('#e34c26', '#e34c26'),
    'Other': ('#a1a9bc', '#8796b2'),
}


def api(path):
    headers = {'User-Agent': 'rs-an-profile', 'Accept': 'application/vnd.github+json'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    for attempt in range(3):
        try:
            with urlopen(Request('https://api.github.com/' + path, headers=headers), timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def collect():
    totals = Counter()
    repositories = []
    page = 1
    while True:
        batch = api(f'users/{OWNER}/repos?type=owner&per_page=100&page={page}')
        for repo in batch:
            if repo['fork'] or repo['private']:
                continue
            languages = api(f'repos/{repo["full_name"]}/languages')
            totals.update(languages)
            repositories.append({'repo': repo['full_name'], 'languages': languages})
        if len(batch) < 100:
            break
        page += 1
    total = sum(totals.values())
    if not total:
        raise RuntimeError('No language data returned; existing cards are preserved.')
    return {
        'updated_on': datetime.now(timezone.utc).date().isoformat(),
        'total_bytes': total,
        'repositories': sorted(repositories, key=lambda r: r['repo']),
        'languages': [{'name': name, 'bytes': count, 'percent': 100 * count / total}
                      for name, count in sorted(totals.items(), key=lambda p: (-p[1], p[0]))],
    }


def render(data, theme):
    dark = theme == 'dark'
    bg, fg, muted, accent = ('#0d1117', '#e6e5f0', '#969cb0', '#bba8e7') if dark else ('#ffffff', '#303348', '#72758a', '#7860b5')
    items = list(data['languages'][:5])
    others = data['languages'][5:]
    if others:
        items.append({'name': 'Other', 'percent': sum(item['percent'] for item in others)})
    bars, legend = [], []
    x = 32.0
    for i, item in enumerate(items):
        color = COLORS.get(item['name'], COLORS['Other'])[int(dark)]
        width = 616 * item['percent'] / 100
        bars.append(f'<rect x="{x:.5f}" y="76" width="{width:.5f}" height="14" fill="{color}"/>')
        x += width
        col, row = divmod(i, 3)
        left, y = 32 + col * 326, 125 + row * 38
        percent = f"{item['percent']:.2f}%" if item['percent'] >= .01 else '<0.01%'
        legend.append(f'<circle cx="{left+5}" cy="{y-5}" r="5" fill="{color}"/><text x="{left+22}" y="{y}" fill="{fg}" font-size="16">{html.escape(item["name"])}</text><text x="{left+290}" y="{y}" text-anchor="end" fill="{muted}" font-size="15" class="number">{html.escape(percent)}</text>')
    summary = '; '.join(f'{item["name"]}: {item["percent"]:.2f}%' for item in items)
    other_names = ', '.join(item['name'] for item in others) or 'none'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="232" viewBox="0 0 680 232" role="img" aria-labelledby="title desc">
<title id="title">Most used languages — rs-an</title>
<desc id="desc">{html.escape(summary)}. Share of code bytes in public repositories, excluding forks, fetched {data['updated_on']}. Other includes {html.escape(other_names)}. Percentages rounded.</desc>
<style>text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}}.number{{font-variant-numeric:tabular-nums}}</style>
<defs><clipPath id="bar"><rect x="32" y="76" width="616" height="14" rx="7"/></clipPath></defs>
<rect width="680" height="232" fill="{bg}"/>
<text x="32" y="48" fill="{accent}" font-size="25" font-weight="650">Most used languages</text>
<g clip-path="url(#bar)">{''.join(bars)}</g>
{''.join(legend)}
</svg>'''


def main():
    data = collect()
    outputs = {f'languages-compact-{theme}.svg': render(data, theme) for theme in ('light', 'dark')}
    outputs['languages-data.json'] = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    folder = ROOT / 'assets'
    folder.mkdir(exist_ok=True)
    for name, content in outputs.items():
        (folder / name).write_text(content, encoding='utf-8')
    print(f'Updated cards from {len(data["repositories"])} public non-fork repositories.')


if __name__ == '__main__':
    main()

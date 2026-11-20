"""Build both profile cards from GitHub's public language-byte counts. No dependencies."""
import html
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'rs-an'
REPOSITORIES_QUERY = '''query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 100, after: $after, ownerAffiliations: [OWNER],
                 isFork: false, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id nameWithOwner
        languages(first: 100) {
          pageInfo { hasNextPage endCursor }
          edges { size node { name color } }
        }
      }
    }
  }
}'''
LANGUAGES_QUERY = '''query($id: ID!, $after: String) {
  node(id: $id) {
    ... on Repository {
      languages(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges { size node { name color } }
      }
    }
  }
}'''


def graphql(query, variables):
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise RuntimeError('GH_TOKEN is required; Actions supplies github.token automatically.')
    headers = {'User-Agent': 'rs-an-profile', 'Content-Type': 'application/json',
               'Authorization': 'Bearer ' + token}
    payload = json.dumps({'query': query, 'variables': variables}).encode()
    for attempt in range(3):
        try:
            with urlopen(Request('https://api.github.com/graphql', data=payload,
                                 headers=headers), timeout=30) as response:
                result = json.load(response)
            if result.get('errors'):
                raise RuntimeError('GitHub GraphQL failed: ' + '; '.join(
                    error.get('message', 'Unknown error') for error in result['errors']))
            if not result.get('data'):
                raise RuntimeError('GitHub returned no data; existing cards are preserved.')
            return result['data']
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def collect():
    totals, colors, repositories = Counter(), {}, []
    cursor = None
    while True:
        result = graphql(REPOSITORIES_QUERY, {'login': OWNER, 'after': cursor})
        if not result.get('user'):
            raise RuntimeError('GitHub user not found; existing cards are preserved.')
        batch = result['user']['repositories']
        for repo in batch['nodes']:
            languages = {}
            connection = repo['languages']
            while True:
                for edge in connection['edges']:
                    language = edge['node']
                    name, color = language['name'], language['color']
                    if color is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                        raise RuntimeError(f'Invalid GitHub color for {name}')
                    languages[name] = edge['size']
                    colors[name] = color
                if not connection['pageInfo']['hasNextPage']:
                    break
                connection = graphql(LANGUAGES_QUERY, {
                    'id': repo['id'], 'after': connection['pageInfo']['endCursor']
                })['node']['languages']
            totals.update(languages)
            repositories.append({'repo': repo['nameWithOwner'], 'languages': languages})
        if not batch['pageInfo']['hasNextPage']:
            break
        cursor = batch['pageInfo']['endCursor']
    total = sum(totals.values())
    if not total:
        raise RuntimeError('No language data returned; existing cards are preserved.')
    return {
        'updated_on': datetime.now(timezone.utc).date().isoformat(),
        'total_bytes': total,
        'repositories': sorted(repositories, key=lambda r: r['repo']),
        'languages': [{'name': name, 'bytes': count, 'percent': 100 * count / total,
                       'color': colors[name]}
                      for name, count in sorted(totals.items(), key=lambda p: (-p[1], p[0]))],
    }


def render(data, theme=None):
    fg = muted = '#808080'
    accent = '#9476C4'
    items = list(data['languages'][:5])
    others = data['languages'][5:]
    if others:
        items.append({'name': 'Other', 'percent': sum(item['percent'] for item in others)})
    bars, legend = [], []
    x = 32.0
    for i, item in enumerate(items):
        color = item.get('color') or '#a1a9bc'
        outline = '#1f2328'
        width = 616 * item['percent'] / 100
        bars.append(f'<rect x="{x:.5f}" y="76" width="{width:.5f}" height="14" fill="{color}"/>')
        x += width
        col, row = divmod(i, 3)
        left, y = 32 + col * 326, 125 + row * 38
        percent = f"{item['percent']:.2f}%" if item['percent'] >= .01 else '<0.01%'
        legend.append(f'<circle cx="{left+6}" cy="{y-5}" r="5.5" fill="{color}" stroke="{outline}" stroke-opacity="0.15" stroke-width="1"/><text x="{left+22}" y="{y}" fill="{fg}" font-size="16">{html.escape(item["name"])}</text><text x="{left+290}" y="{y}" text-anchor="end" fill="{muted}" font-size="15" class="number">{html.escape(percent)}</text>')
    summary = '; '.join(f'{item["name"]}: {item["percent"]:.2f}%' for item in items)
    other_names = ', '.join(item['name'] for item in others) or 'none'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="704" height="256" viewBox="0 0 704 256" role="img" aria-labelledby="title desc">
<title id="title">Most used languages — rs-an</title>
<desc id="desc">{html.escape(summary)}. Share of code bytes in public repositories, excluding forks, fetched {data['updated_on']}. Other includes {html.escape(other_names)}. Percentages rounded.</desc>
<style>text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}}.number{{font-variant-numeric:tabular-nums}}</style>
<defs>
<linearGradient id="holo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8B45FF"/><stop offset=".32" stop-color="#26B8F5"/><stop offset=".62" stop-color="#25D7B3"/><stop offset="1" stop-color="#F16ABA"/></linearGradient>
<filter id="glow" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="2.5"/></filter>
<clipPath id="bar"><rect x="32" y="76" width="616" height="14" rx="7"/></clipPath></defs>
<rect x="8" y="8" width="688" height="240" rx="18" fill="none" stroke="url(#holo)" stroke-width="3" opacity=".35" filter="url(#glow)"/>
<rect x="8" y="8" width="688" height="240" rx="18" fill="none" stroke="url(#holo)" stroke-width="1.8"/>
<g transform="translate(12 12)">
<text x="32" y="48" fill="{accent}" font-size="25" font-weight="650">Most used languages</text>
<g clip-path="url(#bar)">{''.join(bars)}</g>
{''.join(legend)}
</g></svg>'''


def main():
    data = collect()
    outputs = {f'languages-compact-{theme}.svg': render(data, theme) for theme in ('light', 'dark')}
    outputs['languages-compact.svg'] = render(data)
    outputs['languages-data.json'] = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    folder = ROOT / 'assets'
    folder.mkdir(exist_ok=True)
    for name, content in outputs.items():
        (folder / name).write_text(content, encoding='utf-8')
    print(f'Updated cards from {len(data["repositories"])} public non-fork repositories.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""把指定飞书 wiki 子树导出为 Markdown（含图片），落到源目录供知识流水线采集。

边界：只导出 --node 指定节点的子树；不动任何人工放置的文件。
幂等：按 token + 内容哈希判断是否需要重导；未变化的文档不重写文件（保留 mtime）。
停用：文档被移出子树时不删本地导出，只在报告里列出待人工确认。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_NODE = 'EcJYwv76NisdK1kY1W0czzBbnoN'   # wiki「TS」
DEFAULT_SPACE = '7527996824649564162'
DEFAULT_OUT = Path('/root/feishu-export-staging')
CLI = os.environ.get('LARK_CLI', 'lark-cli')
CLI_PREFIX = json.loads(os.environ['LARK_CLI_PREFIX']) if os.environ.get('LARK_CLI_PREFIX') else [CLI]
ASSET_RE = re.compile(r'\((https://[A-Za-z0-9.-]*feishu\.cn/file/([A-Za-z0-9]+))\)')


def cli_json(args: list[str], timeout: int = 300) -> dict:
    result = subprocess.run([*CLI_PREFIX, *args, '--as', 'user', '--format', 'json'],
                            capture_output=True, timeout=timeout)
    raw = (result.stdout or result.stderr or b'').decode('utf-8', 'replace')
    start = raw.find('{')
    if start < 0:
        return {'ok': False, 'error': {'message': raw[:200]}}
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError:
        return {'ok': False, 'error': {'message': raw[start:start + 200]}}


def fetch_markdown(obj_token: str) -> tuple[str, str]:
    """返回 (markdown, 错误信息)。用 --format json 的 data.document.content。"""
    payload = cli_json(['docs', '+fetch', '--doc', obj_token, '--doc-format', 'markdown'])
    if not payload.get('ok'):
        return '', str((payload.get('error') or {}).get('message'))[:200]
    content = ((payload.get('data') or {}).get('document') or {}).get('content') or ''
    return content, '' if content else 'empty-content'


LAST_ERROR: list = []
EXPORT_TRACE: list = []
EXT_BY_TYPE = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif',
               'image/webp': '.webp', 'image/svg+xml': '.svg', 'application/pdf': '.pdf'}


def download_image(file_token: str, target_dir: Path, stem: str) -> str:
    """用 drive +preview 取媒体（drive +download 对图片会 403）；返回写好的文件名，失败返回空串。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_dir = Path(tempfile.gettempdir()) / 'feishu-export-assets'
    safe_dir.mkdir(parents=True, exist_ok=True)
    probe = safe_dir / f'{stem}.bin'   # CLI 拒绝含中文/空格的输出路径，先落安全路径再搬运
    result = subprocess.run([*CLI_PREFIX, 'drive', '+preview', '--file-token', file_token, '--type', 'source_file',
                             '--output', str(probe), '--as', 'user', '--format', 'json'],
                            capture_output=True, timeout=300)
    raw = (result.stdout or result.stderr or b'').decode('utf-8', 'replace')
    start = raw.find('{')
    payload = json.loads(raw[start:]) if start >= 0 else {}
    data = payload.get('data') or {}
    if not payload.get('ok') or data.get('status') != 'READY':
        LAST_ERROR.append({'token': file_token, 'out': str(probe),
                           'ok': payload.get('ok'), 'status': data.get('status'),
                           'err': json.dumps(payload.get('error') or {}, ensure_ascii=False)[:200]})
        return ''
    written = Path(data.get('output_path') or probe)
    if not written.is_file() or written.stat().st_size == 0:
        return ''
    suffix = EXT_BY_TYPE.get(str(data.get('content_type') or '').lower(), '.bin')
    final = target_dir / f'{stem}{suffix}'
    if written != final:
        shutil.move(str(written), str(final))
    return final.name


def walk_tree(space: str, root: str, limit: int = 500) -> list[dict]:
    """枚举子树。**布局为两级**：一级分类（根的直接子节点标题）+ 文档标题。

    只保留一级分类是为了避免深路径/文件与目录同名等一连串问题（实测枚举更稳）。
    """
    items: list[dict] = []
    stack: list[tuple[str, str]] = [(root, '')]
    while stack and len(items) < limit:
        node_token, top = stack.pop()
        payload = cli_json(['wiki', '+node-list', '--space-id', space,
                            '--parent-node-token', node_token, '--page-all'])
        nodes = ((payload.get('data') or {}).get('nodes') or []) if payload.get('ok') else []
        for node in nodes:
            title = (node.get('title') or '未命名').strip()
            safe = re.sub(r'[\\/:*?"<>|]', '_', title)
            top_segment = top or safe          # 一级分类：根的直接子节点
            items.append({
                'title': title,
                'obj_type': node.get('obj_type'),
                'obj_token': node.get('obj_token'),
                'node_token': node.get('node_token'),
                'rel_dir': top_segment,
                'has_child': bool(node.get('has_child')),
            })
            if node.get('has_child'):
                stack.append((node.get('node_token'), top_segment))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description='导出飞书 wiki 子树为 Markdown')
    parser.add_argument('--node', default=DEFAULT_NODE)
    parser.add_argument('--space', default=DEFAULT_SPACE)
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--only', default='', help='只导这一个文档（obj_token 或标题包含）')
    parser.add_argument('--apply', action='store_true', help='真正写文件（默认 dry-run）')
    args = parser.parse_args()

    out_root = Path(args.out)
    manifest_path = out_root / '.manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}

    nodes = walk_tree(args.space, args.node)
    docx_nodes = [n for n in nodes if n['obj_type'] == 'docx']
    other_nodes = [n for n in nodes if n['obj_type'] != 'docx']
    if args.only:
        needle = args.only.lower()
        docx_nodes = [n for n in docx_nodes
                      if needle in (n['obj_token'] or '').lower() or needle in n['title'].lower()]

    report = {'asset_errors': LAST_ERROR, 'scanned': len(nodes), 'docx': len(docx_nodes), 'skipped_types': sorted({n['obj_type'] for n in other_nodes}),
              'new': [], 'updated': [], 'unchanged': 0, 'failed': [], 'images': 0, 'apply': args.apply}

    for node in docx_nodes:
        rel = node['rel_dir']
        md, err = fetch_markdown(node['obj_token'])
        if err:
            report['failed'].append({'title': node['title'], 'error': err})
            EXPORT_TRACE.append({'title': node['title'], 'rel': rel, 'action': 'fetch-failed', 'error': err})
            continue
        digest = hashlib.sha256(md.encode('utf-8')).hexdigest()
        record = manifest.get(node['obj_token']) or {}
        # 每篇文档一律放进自己的目录：避免"同名路径既是文件又是目录"的冲突
        used = globals().setdefault('_USED', set())
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', node['title'])
        unique_title = safe_title
        if f'{rel}/{unique_title}' in used:
            unique_title = f"{safe_title}-{(node['obj_token'] or '')[:6]}"
        used.add(f'{rel}/{unique_title}')
        md_path = out_root / f'{rel}/{unique_title}/{unique_title}.md'
        asset_dir = md_path.parent / f'{unique_title}.assets'

        if record.get('hash') == digest and md_path.is_file():
            report['unchanged'] += 1
            EXPORT_TRACE.append({'title': node['title'], 'rel': rel, 'md_path': str(md_path), 'action': 'unchanged'})
            continue

        body = md
        if args.apply:
            md_path.parent.mkdir(parents=True, exist_ok=True)
            counter = 0
            for full_url, file_token in ASSET_RE.findall(md):
                counter += 1
                try:
                    name = download_image(file_token, asset_dir, f'asset-{counter:02d}')
                except Exception as exc:
                    report['asset_errors'].append({'token': file_token, 'err': f'{type(exc).__name__}: {exc}'[:200]})
                    continue
                if name:
                    body = body.replace(f'({full_url})', f'({unique_title}.assets/{name})')
                    report['images'] += 1
            header = (f'<!-- 来源：飞书 wiki｜{node["title"]}｜node_token={node["node_token"]}'
                      f'｜obj_token={node["obj_token"]}｜导出时间={datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")} -->\n\n')
            try:
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(header + body, encoding='utf-8')
                EXPORT_TRACE.append({'title': node['title'], 'rel': rel, 'md_path': str(md_path),
                                     'action': 'written', 'assets': counter, 'bytes': md_path.stat().st_size})
            except Exception as exc:
                report['failed'].append({'title': node['title'], 'error': f'{type(exc).__name__}: {exc}'[:180]})
                EXPORT_TRACE.append({'title': node['title'], 'rel': rel, 'md_path': str(md_path),
                                     'action': 'write-failed', 'error': f'{type(exc).__name__}: {exc}'[:180]})
            manifest[node['obj_token']] = {'title': node['title'], 'hash': digest, 'rel': str(md_path),
                                           'images': counter, 'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}

        bucket = 'updated' if record else 'new'
        report[bucket].append({'title': node['title'], 'rel': rel, 'images': len(ASSET_RE.findall(md))})

    if args.apply:
        out_root.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')

    actions: dict = {}
    for item in EXPORT_TRACE:
        actions[item['action']] = actions.get(item['action'], 0) + 1
    report['trace_actions'] = actions
    report['trace'] = EXPORT_TRACE[:8] if args.only else []
    if args.apply:
        trace_path = out_root / '.export-trace.jsonl'
        out_root.mkdir(parents=True, exist_ok=True)
        with trace_path.open('w', encoding='utf-8') as handle:
            for item in EXPORT_TRACE:
                handle.write(json.dumps(item, ensure_ascii=False) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

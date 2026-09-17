"""把发布产物上传到 GitHub Release（默认 dry-run，--apply 才真正发布）。

凭据只从环境变量或 .env 读取，绝不打印。上传后回读 Release 资产做校验。
用法：
    python scripts/publish-release.py --tag v0.1.0-preview1            # dry-run
    python scripts/publish-release.py --tag v0.1.0-preview1 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_token(env_file: Path | None) -> str:
    """从环境变量读取 GitHub token；缺失时尝试从 .env 读取（不打印内容）。"""

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if env_file and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("GITHUB_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("未找到 GITHUB_TOKEN：请设置环境变量或提供 --env-file")


def repo_slug() -> str:
    result = subprocess.run(["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
                            capture_output=True, text=True)
    url = result.stdout.strip()
    if url.startswith("git@"):
        return url.split(":", 1)[1].removesuffix(".git")
    return url.rstrip("/").removesuffix(".git").split("github.com/", 1)[-1]


def request(url: str, token: str, *, method: str = "GET", payload: dict | None = None,
            upload: tuple[Path, str] | None = None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ts-team-kb-release"}
    body = None
    if upload is not None:
        path, content_type = upload
        body = path.read_bytes()
        headers["Content-Type"] = content_type
    elif payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw})
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return error.code, {"error": detail[:400]}


def find_asset(release: dict, name: str) -> int | None:
    """在同名资产已存在时取出其 id（用于先删后传，避免 422）。"""

    for item in release.get("assets", []):
        if item.get("name") == name:
            return int(item["id"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--notes", default="免安装 Windows 包（exe）与 wheel")
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--env-file", default=str(Path.home() / "AppData" / "Local" / "hermes" / ".env"))
    parser.add_argument("--prerelease", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    slug = repo_slug()
    token = read_token(Path(args.env_file))
    assets = [Path(item) for item in args.asset] or sorted((PROJECT_ROOT / "dist-release").glob("*.zip")) \
        + sorted((PROJECT_ROOT / "dist-release").glob("*.whl"))
    assets = [item for item in assets if item.is_file()]

    print(f"repo={slug} tag={args.tag} assets={[f'{a.name} ({a.stat().st_size}B)' for a in assets]}")
    status, payload = request(f"https://api.github.com/repos/{slug}/releases/tags/{args.tag}", token)
    existing = payload.get("id") if status == 200 else None
    print(f"release_lookup={status} existing_id={existing}")
    if status not in (200, 404):
        print(json.dumps(payload, ensure_ascii=False)[:400])
        return 1

    if not args.apply:
        print("dry-run：未创建 Release、未上传资产（加 --apply 才执行）")
        return 0

    if existing is None:
        status, payload = request(
            f"https://api.github.com/repos/{slug}/releases", token, method="POST",
            payload={"tag_name": args.tag, "name": args.name or args.tag, "body": args.notes,
                     "draft": False, "prerelease": args.prerelease, "target_commitish": "dev"})
        print(f"release_create={status}")
        if status not in (200, 201):
            print(json.dumps(payload, ensure_ascii=False)[:400])
            return 1
        existing = payload["id"]

    upload_url = f"https://uploads.github.com/repos/{slug}/releases/{existing}/assets"
    status, current = request(f"https://api.github.com/repos/{slug}/releases/{existing}", token)
    for asset in assets:
        stale = find_asset(current, asset.name)
        if stale is not None:
            code, _ = request(f"https://api.github.com/repos/{slug}/releases/assets/{stale}", token, method="DELETE")
            print(f"replace: 删除同名旧资产 {asset.name} -> {code}")
        content_type = "application/zip" if asset.suffix == ".zip" else "application/octet-stream"
        status, payload = request(f"{upload_url}?name={asset.name}", token, method="POST",
                                  upload=(asset, content_type))
        print(f"upload {asset.name} -> {status} size={(payload.get('size') if isinstance(payload, dict) else None)}")
        if status not in (200, 201):
            print(json.dumps(payload, ensure_ascii=False)[:400])

    status, payload = request(f"https://api.github.com/repos/{slug}/releases/{existing}", token)
    listing = [(item["name"], item["size"], item["state"]) for item in payload.get("assets", [])]
    print(f"verify_status={status} assets={listing}")
    return 0 if status == 200 and all(item[1] > 0 for item in listing) else 1


if __name__ == "__main__":
    raise SystemExit(main())

import random
import string
from pathlib import Path

import pytest

from ts_knowledge_agent.services.secret_scan import quarantine_document, scan_text


def test_detects_api_key_and_bearer_token():
    text = '# doc\n\n"apiKey": "sk-live1234567890"\nAuthorization: Bearer abcdefghijklmnop\n'
    result = scan_text(text)
    assert not result.ok
    assert "openai_key" in result.kinds()
    assert "credential_field" in result.kinds()
    assert "bearer_token" in result.kinds()


def test_placeholder_and_redacted_values_are_allowed():
    text = (
        "# doc\n\n"
        '"apiKey": "[REDACTED]"\n'
        "Authorization: Bearer <token>\n"
        "Use the header `Authorization: Bearer <token>` in your request.\n"
    )
    result = scan_text(text)
    assert result.ok, result.summary()


def test_plain_prose_is_allowed():
    text = "# doc\n\nThis document explains password validation rules in a form component.\n"
    assert scan_text(text).ok


def test_quarantine_moves_document_outside_repository(tmp_path):
    repository = tmp_path / "repo"
    document = repository / "members" / "whm" / "doc"
    document.mkdir(parents=True)
    (document / "doc.md").write_text("# secret\n", encoding="utf-8")
    working = tmp_path / "work"
    working.mkdir()

    target = quarantine_document(working, repository, document)

    assert target == working / "quarantine" / "members" / "whm" / "doc"
    assert (target / "doc.md").is_file()
    assert not document.exists()
    assert not (repository / "members" / "whm" / "doc").exists()


# ── 占位符判定：压住「文档写 API 示例就被隔离」的误报 ──────────────────────
# 回归意图有两面：
#   ① 明确的占位符/示例值必须放行（否则文档会莫名消失）
#   ② 高熵真凭据必须仍被拦截（放松门禁的目的不是放过凭据）
# 真凭据样本运行时随机生成，不写死，避免把「像凭据」的字面量提交进仓库。

def _rand(n, pool=None):
    pool = pool or (string.ascii_letters + string.digits)
    return "".join(random.choice(pool) for _ in range(n))


@pytest.mark.parametrize(
    "value",
    [
        "[REDACTED]",
        "<YOUR_API_KEY>",
        "${YOUR_API_KEY}",
        "[YOUR_API_KEY]",
        "YOUR_API_KEY",
        "sk-xxxxxxxxxxxx",
        "sk-0000000000",
        "sk-ababababab",
        "test-key-1234567890",
        "demo-secret-value-123",
        "example-token-abcdefg",
        "placeholder_key_here",
        "changeme-please-12345",
        "待填",
        "foo-bar-baz-qux-quux",
    ],
)
def test_placeholder_values_are_allowed(value):
    """明确的占位符/示例值必须放行 —— 否则整篇文档会被静默隔离。"""
    assert scan_text(f'"apiKey": "{value}"').ok


def test_high_entropy_credentials_are_still_blocked():
    """高熵真凭据必须仍被拦截：放行占位符不等于放松门禁。"""
    assert not scan_text(f'"apiKey": "sk-{_rand(40)}"').ok
    assert not scan_text(f'"apiKey": "{_rand(32)}"').ok
    assert not scan_text(f'"client_secret": "{_rand(43)}"').ok
    assert not scan_text(f"Authorization: Bearer {_rand(40)}").ok
    assert not scan_text(f"x-api-key: {_rand(32)}").ok


def test_substring_placeholder_does_not_weaken_real_detection():
    """含占位子串的写法放行后，紧邻的真凭据仍要被认出。"""
    text = f'"apiKey": "<YOUR_API_KEY>"\n"client_secret": "{_rand(36)}"\n'
    result = scan_text(text)
    assert not result.ok
    assert "credential_field" in result.kinds()
    assert result.findings[0].line == 2 or any(f.line == 2 for f in result.findings)

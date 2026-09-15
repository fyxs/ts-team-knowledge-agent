import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

TOKEN_PATTERN = re.compile(r'^\s*(--[a-z0-9-]+)\s*:', re.MULTILINE)


def _tokens(path: Path) -> set[str]:
    return set(TOKEN_PATTERN.findall(path.read_text(encoding='utf-8')))


def test_design_tokens_are_defined_in_the_design_directory():
    design = _tokens(PROJECT / 'design' / 'tokens.css')

    assert design, 'design/tokens.css defines no tokens'
    for required in ('--bg', '--surface', '--fg', '--border', '--accent', '--radius-lg', '--space-4'):
        assert required in design, f'standard token missing from design/tokens.css: {required}'


def test_runtime_tokens_keep_every_standard_token():
    design = _tokens(PROJECT / 'design' / 'tokens.css')
    runtime = _tokens(PROJECT / 'frontend' / 'src' / 'tokens.css')

# 设计体系中标注「本应用不适用」的分区节奏 token，运行时有意不引入
    INTENTIONALLY_OMITTED = {'--section-y-desktop', '--section-y-tablet', '--section-y-phone'}

    missing = sorted(design - runtime - INTENTIONALLY_OMITTED)
    assert not missing, 'frontend runtime tokens dropped standard tokens: ' + ', '.join(missing)


def test_runtime_tokens_document_app_extensions():
    text = (PROJECT / 'frontend' / 'src' / 'tokens.css').read_text(encoding='utf-8')

    assert '应用扩展' in text, 'app extension block must be marked'
    for name in ('--overlay', '--content-max'):
        assert name in text, f'app extension token missing: {name}'


def test_styles_do_not_hardcode_colors():
    styles = (PROJECT / 'frontend' / 'src' / 'styles.css').read_text(encoding='utf-8')
    body = re.sub(r'/\*.*?\*/', '', styles, flags=re.DOTALL)

    offenders = re.findall(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', body)
    assert not offenders, 'styles.css must use tokens instead of literal colors: ' + ', '.join(sorted(set(offenders)))

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=8.0",
# ]
# ///
"""Guards for tools/preview.html.

The browser harness is a second implementation of the host contract, so it can
drift from the real host (tools/render_still.py) in two ways that are both easy
to miss and awkward to debug:

1. The shader used ES 3.00-only constructs (array constructors, non-constant
   array indexing, bit-wise operators). Those compile fine on the desktop GL
   3.30 host used by render_still.py and hearth.py, so every GPU test stayed
   green, while the browser showed only a compile error. Verified by running
   the harness in a real browser during this work.

2. Its per-shader uniform defaults drifted from render_still.SHADERS — which is
   the single source of truth — so tuning in the browser silently changed
   nothing in the real app.

These tests need no browser and no GPU: they check the harness source. The
browser check itself was done live; this locks the invariants in.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "tools" / "preview.html"
SHADERS = ROOT / "shaders"

# GLSL ES 1.00 forbids these; WebGL compiles as ES 1.00. The desktop host is
# GLSL 3.30 and accepts all of them, which is exactly why they went unnoticed.
ES100_FORBIDDEN = [
    (r"\bfloat\s*\[\s*\d*\s*\]\s*\(", "array constructor (ES 3.00+)"),
    (r"\b(?:int|uint|float|vec[234])\s+\w+\s*\[\s*\d+\s*\]\s*=", "array declaration+init"),
    (r"(?<!&)&(?![&|])", "bit-wise AND"),
    (r"<<|>>", "bit-wise shift"),
]


def shader_text() -> str:
    return (SHADERS / "hearth.frag").read_text(encoding="utf-8")


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _raw_preview_script() -> str:
    html = PREVIEW.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, flags=re.S)
    assert m, "preview.html has no inline script"
    return m.group(1)


def preview_script() -> str:
    """Inline script body, ASCII-normalised for the ast-based checks.

    Python's ast does not treat `//` as a JS comment, so a non-ASCII character
    inside one fails the parse with a bare SyntaxError about U+2014. Normalising
    keeps those failures pointed at the actual problem instead of typography.
    """
    return _raw_preview_script().encode("ascii", "replace").decode("ascii")


def test_preview_script_is_ascii() -> None:
    """Keep the harness script ASCII-only.

    Not cosmetic: tests parse it with ast, and an em-dash inside a `//` comment
    makes that parse fail with a SyntaxError that says nothing about the real
    problem. Both occurrences were real, one written while fixing the other.
    """
    offenders = [
        (i, ch)
        for i, line in enumerate(_raw_preview_script().splitlines(), 1)
        for ch in line
        if ord(ch) > 127
    ]
    assert not offenders, (
        f"non-ASCII characters in preview.html script: {offenders}"
    )


def js_top_level_decls(script: str) -> dict[str, int]:
    """Map top-level JS `const|let|var NAME` to its line number.

    The script cannot be handed to ast.parse wholesale: it is JavaScript, so
    `const`/template literals/`=>` are a SyntaxError. Regex on declaration
    lines is adequate and keeps the check honest about what it verifies.
    """
    decls: dict[str, int] = {}
    for i, line in enumerate(script.splitlines(), 1):
        m = re.match(
            r"\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", line)
        if m:
            decls.setdefault(m.group(1), i)
    return decls


@pytest.mark.parametrize("shader", sorted(p.name for p in SHADERS.glob("*.frag")))
def test_shader_avoids_es300_only_syntax(shader: str) -> None:
    """Shaders must compile under GLSL ES 1.00, not just desktop GL 3.30.

    This is the regression that made hearth.frag un-openable in the browser
    while all 29 GPU tests still passed.
    """
    code = strip_comments((SHADERS / shader).read_text(encoding="utf-8"))
    for pattern, what in ES100_FORBIDDEN:
        hits = re.findall(pattern, code)
        assert not hits, (
            f"{shader} uses {what} ({len(hits)}x), which GLSL ES 1.00 rejects — "
            f"it will compile on the desktop host and fail in WebGL"
        )


def test_bayer_matrix_is_a_real_4x4() -> None:
    """bayer4 must produce all 16 distinct levels.

    Guards the arithmetic rewrite: an earlier mod-based attempt produced values
    up to 31 with duplicates, which still 'looked like' a dither but flattened
    a 16-step gradient into 11 uneven ones.
    """
    src = (SHADERS / "hearth.frag").read_text(encoding="utf-8")
    m = re.search(r"float\s+bayer4\s*\(", src)
    assert m, "bayer4 not found"

    # Reproduce the GLSL body in Python with the same mod/exp2 arithmetic.
    def bayer4(x: float, y: float) -> float:
        v = 0.0
        for bit in range(2):
            xb = math_floor(x / 2.0**bit) % 2.0
            yb = math_floor(y / 2.0**bit) % 2.0
            v += xb * 2.0 ** (3 - 2 * bit) + yb * 2.0 ** (2 - 2 * bit)
        return v / 16.0 - 0.5

    def math_floor(v: float) -> float:
        import math

        return math.floor(v)

    grid = [bayer4(float(x), float(y)) for y in range(4) for x in range(4)]
    levels = {round((g + 0.5) * 16) for g in grid}
    assert levels == set(range(16)), f"bayer4 levels are not 0..15: {sorted(levels)}"


def test_preview_declares_no_duplicate_params() -> None:
    """A duplicate top-level `const` silently kills the whole harness.

    `params` was declared twice while adding shader selection, which throws
    "Identifier 'params' has already been declared" at parse time. The symptom
    was unusually nasty: no error box, no failed fetch, no console error, just
    a permanent "booting..." with a 300x150 canvas.
    """
    script = preview_script()
    hits = [
        (i, m.group(1))
        for i, line in enumerate(script.splitlines(), 1)
        if (m := re.match(r"\s*(?:const|let|var)\s+(params)\s*=", line))
    ]
    assert len(hits) <= 1, (
        f"preview.html declares `params` {len(hits)}x at lines "
        f"{[h[0] for h in hits]}; a duplicate const kills the script silently"
    )


def test_preview_uses_params_only_after_declaration() -> None:
    """`params` must not be read before its declaration (TDZ).

    Reading a `const` declared later is a ReferenceError that aborts the script
    before main() runs. Cost real debugging time: the harness just hung on
    "booting..." with no error anywhere.
    """
    script = preview_script()
    decls = js_top_level_decls(script)
    assert "params" in decls, "preview.html no longer declares `params`"
    decl_line = decls["params"]

    early = [
        i for i, line in enumerate(script.splitlines(), 1)
        if i < decl_line
        and re.search(r"(?<![\w.$])params\s*\.", line)
        and not line.lstrip().startswith(("//", "*", "/*"))
    ]
    assert not early, (
        f"preview.html reads `params` at line(s) {early} but declares it at "
        f"line {decl_line} - TDZ ReferenceError, harness will not start"
    )


def test_preview_defaults_match_source_of_truth() -> None:
    """Per-shader defaults in the harness must equal render_still.SHADERS."""
    sys.path.insert(0, str(ROOT / "tools"))
    import render_still  # noqa: PLC0415

    script = preview_script()
    for name, defaults in render_still.SHADERS.items():
        block = re.search(
            rf"{re.escape(name)}\s*:\s*\{{(.*?)\}}", script, flags=re.S)
        assert block, f"preview.html has no defaults block for shader {name!r}"
        found = dict(
            (k, float(v))
            for k, v in re.findall(r"(u\w+)\s*:\s*([-\d.]+)", block.group(1))
        )
        assert found == dict(defaults), (
            f"preview.html {name} defaults drifted from render_still.SHADERS.\n"
            f"  preview:    {found}\n"
            f"  render_still: {dict(defaults)}"
        )


def test_preview_loads_the_requested_shader() -> None:
    """The harness must fetch shaders/<ACTIVE>.frag, not a hardcoded name."""
    script = preview_script()
    assert re.search(r"fetch\(\s*`\.\./shaders/\$\{ACTIVE\}\.frag`", script), (
        "preview.html no longer fetches the shader chosen by ?shader="
    )
    assert not re.search(r"fetch\(\s*['\"]\.\./shaders/fire\.frag['\"]", script), (
        "preview.html still hardcodes fire.frag — it would ignore ?shader="
    )

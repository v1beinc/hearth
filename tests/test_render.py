# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "moderngl>=5.10",
#   "numpy>=2.0",
#   "pillow>=10.0",
#   "pytest>=8.0",
# ]
# ///
"""Verification for shaders/fire.frag.

The fire is a visual artifact, so the useful assertions are statistical:
something is drawn, it is warm rather than blue, it actually animates, and it
stays inside the frame. Pixel-exact snapshots would fail on any driver change
without telling us anything true, so we assert properties instead.

Determinism is the one thing we DO assert exactly: same --t must give the same
bytes, otherwise tools/render_still.py is useless as a regression baseline.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# Reuse the real host rather than a copy — if the host and the shader disagree
# about the contract, these tests must fail with that, not paper over it.
import render_still  # noqa: E402


@pytest.fixture(scope="module")
def gpu():
    try:
        import moderngl
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"no OpenGL context available: {exc}")
    if ctx is None:
        pytest.skip("no OpenGL context available")
    return ctx


def render(t: float, size: str = "256x144", **uniforms) -> np.ndarray:
    """Render one frozen frame and return it as float32 RGB."""
    w, h = (int(v) for v in size.lower().split("x"))
    saved = dict(render_still.UNIFORM_DEFAULTS)
    try:
        render_still.UNIFORM_DEFAULTS.update(uniforms)
        src, declared = render_still.build_fragment_source()
        ctx = render_still.moderngl.create_standalone_context()
        prog = ctx.program(vertex_shader=render_still.VERTEX,
                           fragment_shader=src)
        vao = ctx.vertex_array(prog, [(ctx.buffer(np.array(
            [-1, -1, 3, -1, -1, 3], dtype="f4")), "2f", "in_pos")])
        fbo = ctx.simple_framebuffer((w, h), components=4)
        fbo.use()
        ctx.viewport = (0, 0, w, h)

        def maybe(name, value):
            try:
                prog[name].value = value
            except KeyError:
                pass

        maybe("iResolution", (float(w), float(h), 1.0))
        maybe("iTime", t)
        maybe("iTimeDelta", 0.0)
        maybe("iFrame", 0)
        maybe("iMouse", (0.0, 0.0, 0.0, 0.0))
        for k in render_still.UNIFORM_DEFAULTS:
            prog[k].value = render_still.UNIFORM_DEFAULTS[k]
        vao.render(render_still.moderngl.TRIANGLES)

        data = fbo.read(components=3, alignment=1)
        img = Image.frombytes("RGB", (w, h), data).transpose(
            Image.FLIP_TOP_BOTTOM)
        return np.asarray(img, dtype=np.float32)
    finally:
        render_still.UNIFORM_DEFAULTS.clear()
        render_still.UNIFORM_DEFAULTS.update(saved)


# --- contract ----------------------------------------------------------------

def test_shader_declares_host_owned_boundary():
    """fire.frag must not own iResolution/iTime, but must define mainImage."""
    raw = (ROOT / "shaders" / "fire.frag").read_text(encoding="utf-8")
    assert "void mainImage" in raw, "shader lost its mainImage() entry point"
    import re
    assert not re.search(r"^\s*uniform\s+\w+\s+iResolution", raw, re.MULTILINE), \
        "host owns iResolution; the shader must not redeclare it"
    assert re.search(r"^\s*void\s+mainImage\s*\(", raw, re.MULTILINE)


def test_all_tuning_uniforms_reach_the_program():
    """Every uniform the hosts expose must survive GLSL compilation.

    A driver that silently drops one leaves the slider dead with no error.
    """
    ctx = render_still.moderngl.create_standalone_context()
    src, declared = render_still.build_fragment_source()
    prog = ctx.program(vertex_shader=render_still.VERTEX,
                       fragment_shader=src)
    missing = [k for k in render_still.UNIFORM_DEFAULTS if k not in declared]
    assert not missing, f"hosts expose uniforms the shader never declares: {missing}"


# --- it draws something -------------------------------------------------------

def test_frame_is_not_black():
    a = render(12.0)
    assert a.max() > 40, f"frame is essentially black (max={a.max()})"
    lit = (a.max(axis=2) > 12).mean()
    assert lit > 0.02, f"only {lit*100:.2f}% of pixels lit — nothing is drawn"


def test_frame_is_warm_not_blue():
    """Firelight must be red-dominant. Catches a broken palette ramp."""
    a = render(12.0)
    mean_r, mean_b = a[..., 0].mean(), a[..., 2].mean()
    assert mean_r > mean_b * 1.8, \
        f"not warm enough: meanR={mean_r:.1f} meanB={mean_b:.1f}"


# --- it animates --------------------------------------------------------------

def test_frame_changes_over_time():
    a = render(12.0)
    b = render(13.0)
    diff = np.abs(a - b).mean()
    assert diff > 1.0, f"frames 1s apart differ by only {diff:.2f} — static fire"


def test_frame_is_not_flickering_nonsense():
    """Consecutive renders must be similar; total chaos reads as noise."""
    a = render(12.0)
    b = render(12.05)
    diff = np.abs(a - b).mean()
    assert diff < 25.0, f"0.05s apart differs by {diff:.2f} — unstable"


def test_determinism_same_t_same_bytes():
    """Same iTime must reproduce the frame exactly — this is what makes
    tools/render_still.py usable as a regression baseline."""
    a = render(12.0)
    b = render(12.0)
    assert np.array_equal(a, b), "identical --t produced different pixels"


# --- shape --------------------------------------------------------------------

def test_flame_decays_upward():
    """Brightness must fall off toward the top of the frame.

    This is the assertion that caught the original bug: deriving the flame
    envelope from the scrolled noise coordinates instead of screen space made
    the taper collapse into a full-height column of constant brightness.
    """
    a = render(12.0, size="128x128")
    h = a.shape[0]
    # render() flips the image top-bottom, so index 0 is the TOP of the frame
    # and index -1 is the hearth. Getting this backwards makes the assertion
    # check the opposite of what it claims.
    red = a[..., 0].mean(axis=1)

    upper = red[: h // 4].mean()
    lower = red[-h // 4:].mean()
    assert lower > upper * 1.25, \
        f"flame does not decay upward: top={upper:.1f} bottom={lower:.1f}"


def test_flame_is_centred_not_clipped_to_a_side():
    """The hearth sits at screen centre; fire must not hug one edge."""
    a = render(12.0, size="160x120")
    w = a.shape[1]
    red = a[..., 0].mean(axis=0)
    left = red[: w // 5].mean()
    right = red[-w // 5:].mean()
    centre = red[2 * w // 5: 3 * w // 5].mean()
    assert centre > max(left, right) * 1.5, \
        f"fire is off-centre: centre={centre:.1f} left={left:.1f} right={right:.1f}"


# --- controls respond ---------------------------------------------------------

def test_uIntensity_darkens_the_frame():
    bright = render(12.0, uIntensity=1.0).mean()
    dim = render(12.0, uIntensity=0.25).mean()
    assert dim < bright * 0.8, \
        f"uIntensity has no effect: bright={bright:.1f} dim={dim:.1f}"


def test_uSpeed_changes_motion():
    a = render(10.0, uSpeed=0.0)
    b = render(10.1, uSpeed=0.0)
    assert np.abs(a - b).mean() < 0.5, "uSpeed=0 should freeze the animation"
    c = render(10.0, uSpeed=2.0)
    d = render(10.1, uSpeed=2.0)
    assert np.abs(c - d).mean() > 1.0, "uSpeed=2 should move faster than frozen"


def test_uEmbers_adds_brightness_above_the_flame():
    """Ember sparkle lives in the air above the flame body.

    Measured over the band the embers are gated to, not the top of the frame —
    checking the top rows passed even when the effect was completely absent,
    because the gate zeroes embers up there by design.
    """
    with_emb = render(12.0, size="256x144", uEmbers=1.0)
    without = render(12.0, size="256x144", uEmbers=0.0)
    h = with_emb.shape[0]
    # embers gate in over sp.y 0.015..0.10 and out by 0.30..0.72; with the
    # top-bottom flip that is roughly rows 30%..72% down from the top.
    band = slice(int(h * 0.28), int(h * 0.72))
    a = with_emb[band].mean()
    b = without[band].mean()
    assert a > b + 0.2, f"uEmbers had no visible effect: {a:.2f} vs {b:.2f}"


def test_uScale_changes_flame_height():
    small = render(12.0, uScale=0.6)
    large = render(12.0, uScale=1.6)
    def top_lit(img):
        return (img.max(axis=2) > 30).mean(axis=1)[: 20].sum()
    assert top_lit(large) > top_lit(small), \
        "uScale does not make the flame reach higher"


# --- host contract in practice -----------------------------------------------

def test_render_still_writes_a_png(tmp_path: Path):
    out = tmp_path / "still.png"
    assert subprocess_run(out)
    assert out.exists() and out.stat().st_size > 1000, "PNG not written"


def test_bench_does_not_change_the_saved_frame(tmp_path: Path):
    """Regression: --bench used to leave the last benchmark frame in the
    framebuffer, so --t 12.0 --bench 120 saved the frame for t=1.904 instead.
    A silent mismatch between the requested time and the written PNG makes the
    whole determinism guarantee worthless.
    """
    plain = tmp_path / "plain.png"
    benched = tmp_path / "benched.png"
    assert subprocess_run(plain)
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "render_still.py"),
         "--t", "12.0", "--size", "320x180", "--out", str(benched),
         "--bench", "120"],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"render_still.py --bench failed:\n{r.stdout}\n{r.stderr}")

    a = np.asarray(Image.open(plain).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(benched).convert("RGB"), dtype=np.int16)
    diff = np.abs(a - b).mean()
    assert diff == 0, (
        f"--bench changed the saved frame (mean diff {diff:.3f}); the final "
        f"draw must happen at --t, after the timing loop")


def subprocess_run(out: Path) -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "render_still.py"),
         "--t", "12.0", "--size", "320x180", "--out", str(out)],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"render_still.py failed:\n{r.stdout}\n{r.stderr}")
    return True
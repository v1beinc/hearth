"""Smoke tests for hearth.py — the launcher, not the shader.

These assert the wiring that render_still.py cannot cover: that the app opens
a window, picks the requested monitor, renders, saves a PNG, honours --set,
and that its DEFAULTS agree with tools/render_still.py SHADERS (two files
listing the same uniforms will drift otherwise).

Each run opens a real window briefly in --windowed mode.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "hearth.py"
STILL = ROOT / "tools" / "render_still.py"

sys.path.insert(0, str(ROOT / "tools"))
import render_still  # noqa: E402


def _load_app():
    """Import hearth.py as a module without running main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_app_module", APP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_app_module = _load_app()


def run(args, timeout=300):
    """Invoke hearth.py through uv so its PEP 723 deps resolve."""
    cmd = ["uv", "run", "--no-project", str(APP), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=str(ROOT))


EVENT_LOOP_CHECK = r'''
# /// script
# requires-python = ">=3.11"
# dependencies = ["moderngl>=5.12", "pyglet>=2.0", "numpy>=1.26", "pillow>=10.0"]
# ///
"""Run the app's REAL main() through a real event loop, then read the pixels.

The user hit a black screen from `uv run hearth.py --monitor 1`. Root cause:
the interactive path never registered an on_draw handler, so pyglet.app.run()
had nothing to paint with.

This must exercise main() itself. An earlier version of this test built its
own window and registered its own handler, which meant it rendered fine even
with the bug present — a test that passes on broken code is worse than no
test. So: run main(), install a watchdog, and inspect what the app drew.
"""
import sys, time
from pathlib import Path
import moderngl
import numpy as np
import pyglet
from PIL import Image

ROOT = Path(r"C:\it\Terminal Fireplace")
sys.path.insert(0, str(ROOT))
import hearth

OUT = ROOT / "out" / "_eventloop_check.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

sys.argv = ["hearth.py", "--windowed", "480x270"]

capture = {"done": False, "error": None}

Original = hearth.Hearth
class Observed(Original):
    def on_draw(self, draw_overlay=True):
        super().on_draw(draw_overlay)
        if self.sound.hidden:
            return
        # Capture what the registered handler painted BEFORE presentation.
        # A swapped back buffer is undefined, especially in resizable windows.
        w, h = self.window.get_framebuffer_size()
        gl = pyglet.gl
        gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, 0)
        gl.glReadBuffer(gl.GL_BACK)
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)
        data = (gl.GLubyte * (w * h * 3))()
        gl.glReadPixels(0, 0, w, h, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, data)
        capture['image'] = Image.frombytes('RGB', (w, h), bytes(data))

hearth.Hearth = Observed


def watchdog(dt):
    """Scheduled INSIDE main()'s event loop, so the window is alive and its
    context current. A separate thread cannot do this: it races main(), and by
    the time it runs the window may already be gone.

    This registers no draw handler. If main() forgot to push on_draw, the
    buffer stays black and the assertion below fails — which is the point.
    """
    wins = [w for w in pyglet.app.windows if w.width == 480]
    if not wins:
        capture["error"] = "main() opened no 480px-wide window"
        pyglet.app.exit()
        return
    w = wins[0]
    try:
        assert 'image' in capture, 'registered on_draw handler never painted'
        img = capture['image']
        img.transpose(Image.FLIP_TOP_BOTTOM).save(OUT)
        capture["done"] = True
    except Exception as e:
        capture["error"] = f"readback failed: {e}"
    finally:
        for window in list(pyglet.app.windows):
            window.close()
        pyglet.app.exit()


pyglet.clock.schedule_once(watchdog, 1.5)

rc = 0
try:
    rc = hearth.main() or 0
except SystemExit as e:
    rc = e.code if isinstance(e.code, int) else 0

if capture["error"]:
    raise SystemExit(f"FAIL: {capture['error']}")
if not capture["done"]:
    raise SystemExit("FAIL: watchdog never captured a frame")

a = np.asarray(Image.open(OUT).convert("RGB"), dtype=np.int32)
print(f"mean RGB : R={a[...,0].mean():.1f} G={a[...,1].mean():.1f} "
      f"B={a[...,2].mean():.1f}")
print(f"lit      : {100*(a.max(axis=2)>12).mean():.1f}% of pixels above 12")
if a.max() == 0:
    raise SystemExit("FAIL: front buffer entirely black — main() painted nothing")
print("OK: real main() renders non-black output")
'''


def test_event_loop_actually_paints():
    """Run the REAL interactive loop and assert the buffer is not black.

    This is the test that was missing when the user got a black screen. It
    cannot be faked with --frames, because --frames draws in a plain loop and
    bypasses the event dispatch entirely.
    """
    script = ROOT / "out" / "_evtloop_check.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(EVENT_LOOP_CHECK, encoding="utf-8")
    r = subprocess.run(["uv", "run", "--no-project", str(script)],
                       capture_output=True, text=True, timeout=300,
                       cwd=str(ROOT))
    assert r.returncode == 0, (
        f"the real main() did not render correctly:\n{r.stdout}\n{r.stderr}")
    assert "OK: real main() renders non-black output" in r.stdout, r.stdout
    script.unlink(missing_ok=True)
    (ROOT / "out" / "_eventloop_check.png").unlink(missing_ok=True)


def test_interactive_run_registers_a_draw_handler():
    """Regression: the interactive app opened a BLACK window.

    The event loop only draws through registered handlers. on_draw() used to be
    called solely from the --frames smoke path, so `uv run hearth.py
    --monitor 1` created a fullscreen window that nothing ever painted.
    """
    import ast
    src = APP.read_text(encoding="utf-8")
    assert "push_handlers(app.on_draw)" in src, (
        "interactive mode never registers on_draw; pyglet.app.run() will idle "
        "and the window stays black")

    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "Hearth")
    names = {f.name for f in cls.body if isinstance(f, ast.FunctionDef)}
    assert "on_draw" in names, (
        "Hearth must define on_draw: pyglet derives the event name from the "
        "attribute name, so a method called draw registers the event 'draw' "
        "and raises EventException: Unknown event \"draw\"")

    # And on_draw must not present the buffer itself — the event loop flips.
    # Checked on the AST: a comment mentioning flip() is fine, a real call
    # to self.window.flip() is not.
    draw_fn = next(f for f in cls.body
                   if isinstance(f, ast.FunctionDef) and f.name == "on_draw")
    calls = [n for n in ast.walk(draw_fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "flip"]
    assert not calls, (
        "on_draw must not call window.flip(); pyglet does it after on_draw")


def test_key_handler_imports_at_module_scope():
    """Regression: every keypress raised ImportError.

    Key constants were imported *inside* the handler with names that do not
    exist in pyglet 2.x (LEFT_BRACKET, EQUALS, KEY_1...). Because the handler
    runs inside a ctypes callback, the exception was swallowed by pyglet: the
    app looked alive, printed nothing useful, and no key did anything.
    """
    import inspect
    src = APP.read_text(encoding="utf-8")
    assert "LEFT_BRACKET" not in src, "left an invalid pyglet key name behind"
    assert "EQUALS" not in src, "left an invalid pyglet key name behind"
    assert "KEY_1" not in src, "left an invalid pyglet key name behind"

    handler = src[src.index("def on_key_press"):]
    body = handler[:handler.index("app.window.push_handlers")]
    assert "import" not in body, (
        "on_key_press must not import; a failing import inside a ctypes callback "
        "is silently ignored by pyglet")

    # Every name the handler uses must actually exist in pyglet.window.key.
    from pyglet.window import key as K
    for name in set(re.findall(r"\bK\.(\w+)\b", body)):
        assert hasattr(K, name), f"pyglet.window.key has no {name}"


def test_all_key_names_used_exist_in_pyglet():
    from pyglet.window import key as K
    src = APP.read_text(encoding="utf-8")
    used = set(re.findall(r"\bK\.(\w+)\b", src))
    missing = [n for n in sorted(used) if not hasattr(K, n)]
    assert not missing, (
        f"hearth.py references non-existent pyglet key constants: {missing}")


def test_windowed_run_reports_fps():
    r = run(["--windowed", "640x360", "--frames", "30"])
    assert r.returncode == 0, f"launcher failed:\n{r.stdout}\n{r.stderr}"
    assert "fps" in r.stdout, f"no fps report:\n{r.stdout}\n{r.stderr}"
    assert "ms/frame" in r.stdout


def test_fire_shader_also_launches():
    r = run(["--shader", "fire", "--windowed", "320x240", "--frames", "10"])
    assert r.returncode == 0, f"fire shader failed:\n{r.stdout}\n{r.stderr}"


def test_monitor_index_validation_rejects_impossible_values():
    """The guard that tells the user their real monitors.

    Tested directly instead of through the CLI: exercising it via --monitor
    would open a borderless fullscreen window on the real desktop during a test
    run, which is unacceptable side effect for a test.
    """
    import inspect
    src = APP.read_text(encoding="utf-8")
    body = inspect.getsource(_app_module.Hearth.__init__)
    assert "does not exist" in body, "monitor guard message was removed"
    assert "0 <= monitor" in body, (
        "monitor guard must reject negative indices too, not just too-large")
    assert "this machine has" in body, "error must report how many monitors exist"


def test_config_pixel_knobs_do_not_break_the_fire_shader():
    """One hearth.toml serves every shader, so keys for the pixel-art shader
    must not look like typos when running the plain flame.

    Regression: --shader fire died with "unknown keys: uDither, uFps, uPixel,
    uSteps, uWall" because validation compared the config against the running
    shader instead of against the union of all shaders.
    """
    r = run(["--shader", "fire", "--windowed", "320x240", "--frames", "5"])
    assert r.returncode == 0, f"fire rejected the shared config:\n{r.stdout}\n{r.stderr}"


def test_genuine_typo_in_config_is_still_rejected(tmp_path):
    """Loosening the check must not turn typos into silence.

    A key that is no uniform of ANY shader is a mistake and must still fail
    loudly, otherwise a misspelt knob just quietly does nothing.
    """
    bad = tmp_path / "bad.toml"
    bad.write_text("[hearth]\nuIntensitee = 1.0\n", encoding="utf-8")
    r = run(["--config", str(bad), "--windowed", "320x240", "--frames", "1"])
    assert r.returncode != 0, "a misspelt uniform was silently ignored"
    assert "unknown keys" in (r.stdout + r.stderr)
    assert "uIntensitee" in (r.stdout + r.stderr), (
        "error should name the offending key")


def test_config_values_actually_reach_the_shader(tmp_path):
    """A uniform set in hearth.toml must change the render, not just parse."""
    import numpy as np
    outs = []
    for px in ("3", "16"):
        cfg = tmp_path / f"px{px}.toml"
        cfg.write_text(f"[hearth]\nuPixel = {px}\n", encoding="utf-8")
        out = ROOT / "out" / f"_cfg_px{px}.png"
        r = run(["--config", str(cfg), "--windowed", "480x270",
                 "--frames", "5", "--save", str(out)])
        assert r.returncode == 0, r.stdout + r.stderr
        assert out.exists()
        outs.append(out)
    a = np.asarray(Image.open(outs[0]).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(outs[1]).convert("RGB"), dtype=np.int16)
    assert np.abs(a - b).mean() > 1.0, "config uPixel had no effect on output"
    for p in outs:
        p.unlink(missing_ok=True)


def test_unknown_uniform_is_rejected():
    r = run(["--windowed", "320x240", "--frames", "1", "--set", "uNope=1"])
    assert r.returncode != 0
    assert "unknown uniform" in (r.stdout + r.stderr)


def test_set_override_changes_output():
    """uPixel=1 vs uPixel=20 must differ, proving CLI overrides reach GL."""
    import numpy as np
    outs = []
    for px in ("1", "20"):
        out = ROOT / "out" / f"_smoke_px{px}.png"
        # launch, draw a few frames, save via the same readback path as the
        # S key — proving CLI overrides reach the GPU in the real app
        r = run(["--windowed", "480x270", "--frames", "5",
                 "--set", f"uPixel={px}", "--save", str(out)])
        assert r.returncode == 0, f"run failed for uPixel={px}:\n{r.stderr}"
        assert out.exists(), f"no PNG written for uPixel={px}"
        outs.append(out)
    a = np.asarray(Image.open(outs[0]).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(outs[1]).convert("RGB"), dtype=np.int16)
    assert np.abs(a - b).mean() > 1.0, "uPixel override had no effect"
    for p in outs:
        p.unlink(missing_ok=True)


def test_hearth_app_imports_the_same_defaults_as_render_still():
    """hearth.py must not keep its own copy of the uniform defaults.

    It imports SHADERS from tools/render_still.py. A hand-maintained second
    copy is how a slider silently stops doing anything (it already happened
    once: uWarmth drifted 0.50 vs 0.55 between the two files).
    """
    for name in ("hearth", "fire"):
        assert _app_module.SHADERS[name] == render_still.SHADERS[name], (
            f"{name} defaults differ between hearth.py and render_still.py")


def test_hearth_shader_uniforms_all_have_defaults():
    """Every uniform the shader declares must be settable by the app."""
    import re
    src = (ROOT / "shaders" / "hearth.frag").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s*uniform\s+\w+\s+(u[A-Z]\w*)\s*;", src, re.M))
    have = set(render_still.SHADERS["hearth"])
    assert declared <= have, (
        f"hearth.frag declares uniforms with no default: "
        f"{sorted(declared - have)}")


@pytest.mark.parametrize("configured, override, expected", [
    ("fire", None, "fire"),
    ("hearth2", None, "hearth2"),
    ("fire", "hearth", "hearth"),
])
def test_config_selects_shader_and_cli_takes_precedence(tmp_path, monkeypatch,
                                                       configured, override, expected):
    """Exercise actual main() parsing without opening a fullscreen test window.

    Previously the argparse default always shadowed the shader in TOML.
    """
    from types import SimpleNamespace

    config = tmp_path / "hearth.toml"
    config.write_text(f'[hearth]\nshader = "{configured}"\n', encoding="utf-8")
    selected = []

    class WindowStub:
        def __init__(self, shader, values, *args):
            selected.append(shader)
            self.window = SimpleNamespace(width=320, height=180)

        def draw_once(self):
            pass

        def close(self):
            pass

    argv = ["hearth.py", "--config", str(config), "--windowed", "320x180", "--frames", "1"]
    if override:
        argv += ["--shader", override]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(_app_module, "Hearth", WindowStub)
    assert _app_module.main() == 0
    assert selected == [expected]

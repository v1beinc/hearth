# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "moderngl>=5.10",
#   "numpy>=2.0",
#   "pillow>=10.0",
# ]
# ///
"""Deterministic offscreen render of any Hearth shader to a PNG.

Uses the same mainImage contract as the desktop app and browser preview.

Because every random value in the shader derives from hashes of the pixel
coordinate, a fixed --t always produces a byte-identical PNG. That is what
tests/test_render.py asserts on.

Usage:
    uv run tools/render_still.py --t 12.0 --out out/fire_t12.png
    uv run tools/render_still.py --t 12.0 --size 1920x1080 --u uWarmth 0.9
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image

if __package__:
    from .scene_clock import SNAPSHOT_CLOCK, parse_clock
else:
    from scene_clock import SNAPSHOT_CLOCK, parse_clock

ROOT = Path(__file__).resolve().parent.parent

# Every shader under shaders/ is a first-class host target. Defaults are
# declared per shader so a new one cannot silently inherit the wrong knobs.
SHADERS: dict[str, dict[str, float]] = {
    "fire": {
        "uIntensity": 1.00,
        "uSpeed": 1.00,
        "uWarmth": 0.55,
        "uScale": 1.00,
        "uDetail": 0.70,
        "uEmbers": 0.60,
        "uRoom": 0.75,
    },
    "hearth": {
        "uIntensity": 1.05,
        "uSpeed": 1.00,
        "uWarmth": 0.50,
        "uScale": 1.00,
        "uDetail": 0.70,
        "uEmbers": 0.60,
        "uRoom": 0.85,
        "uPixel": 6.00,
        "uFps": 12.00,
        "uDither": 0.20,
        "uSteps": 12.00,
        "uWall": 1.00,
        "uSteam": 0.85,
        "uWeather": 0.00,
        "uShowcase": 0.00,
        "uLife": 1.00,
    },
    # Rewritten scene: dark room with a firebox cut into it, palette-ramp
    # colour. Kept alongside `hearth` so the two can be compared side by side
    # before deciding which one ships.
    "hearth2": {
        "uIntensity": 1.05,
        "uSpeed": 1.00,
        "uWarmth": 0.50,
        "uScale": 1.00,
        "uDetail": 0.70,
        "uEmbers": 0.60,
        "uRoom": 0.75,
        "uPixel": 6.00,
        "uFps": 12.00,
        "uDither": 1.00,
        "uSteps": 6.00,
        "uWall": 1.00,
    },
}

VERTEX = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

PREAMBLE = """
#version 330
uniform vec3 iResolution;
uniform float iTime;
uniform float iTimeDelta;
uniform int iFrame;
uniform vec4 iMouse;
uniform vec4 iDate;
"""

# Appended AFTER the shader body, because GLSL resolves calls in source order
# and main() calls mainImage(). The forward declaration in fire.frag covers
# hosts that instead inject their entry point ahead of the body.
EPILOGUE = """
out vec4 outColor;
void main() {
    vec4 c = vec4(0.0, 0.0, 0.0, 1.0);
    mainImage(c, gl_FragCoord.xy);
    outColor = vec4(clamp(c.rgb, 0.0, 1.0), 1.0);
}
"""

# Tunable uniforms are declared per shader in SHADERS above; the live set is
# rebound in main() from the --shader flag.
#
# The host owns exactly two things: the Shadertoy uniforms, and the main()
# entry point that calls mainImage(). The shader keeps its own u* declarations,
# so adding a tunable means editing the shader alone — a host that forgot to
# mirror a uniform list cannot silently break the build.
UNIFORM_DECL = re.compile(r"^\s*uniform\s+\w+\s+(u[A-Z]\w*)\s*;", re.MULTILINE)

# Populated by main(); kept module-level because the tests import these names.
FRAG = ROOT / "shaders" / "fire.frag"
UNIFORM_DEFAULTS: dict[str, float] = dict(SHADERS["fire"])


def build_fragment_source(shader: str = "fire") -> tuple[str, list[str]]:
    """Prepend the host-owned uniforms and return (source, uniform_names)."""
    frag = ROOT / "shaders" / f"{shader}.frag"
    if not frag.exists():
        raise SystemExit(f"no such shader: {frag} (have: "
                         f"{', '.join(sorted(SHADERS))})")
    raw = frag.read_text(encoding="utf-8")

    if "void mainImage" not in raw:
        raise SystemExit(f"{frag.name} lost its mainImage() contract")
    if re.search(r"^\s*uniform\s+\w+\s+iResolution", raw, re.MULTILINE):
        raise SystemExit(
            f"{frag.name} declares iResolution/iTime itself; the host owns those")

    return PREAMBLE + raw + EPILOGUE, UNIFORM_DECL.findall(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shader", default="hearth", choices=sorted(SHADERS),
                    help="which shader under shaders/ to render")
    ap.add_argument("--t", type=float, default=12.0, help="frozen iTime, seconds")
    ap.add_argument("--clock", type=parse_clock, default=SNAPSHOT_CLOCK,
                    help="fixed Moscow clock HH:MM[:SS] (default: 21:15)")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--out", default=None)
    ap.add_argument("--u", action="append", default=[], metavar="NAME=VALUE",
                    help="override a tuning uniform, repeatable")
    ap.add_argument("--bench", type=int, default=0,
                    help="also time N frames and report ms/frame")
    args = ap.parse_args()

    global UNIFORM_DEFAULTS, FRAG
    UNIFORM_DEFAULTS = dict(SHADERS[args.shader])
    FRAG = ROOT / "shaders" / f"{args.shader}.frag"
    if args.out is None:
        args.out = f"out/{args.shader}.png"

    for item in args.u:
        name, _, val = item.partition("=")
        if name not in UNIFORM_DEFAULTS:
            raise SystemExit(f"unknown uniform {name!r} for shader "
                             f"{args.shader!r}; known: "
                             f"{', '.join(sorted(UNIFORM_DEFAULTS))}")
        UNIFORM_DEFAULTS[name] = float(val)

    try:
        w, h = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        raise SystemExit(f"bad --size {args.size!r}, expected WxH")

    src, declared = build_fragment_source(args.shader)
    missing = set(UNIFORM_DEFAULTS) - set(declared)
    if missing:
        raise SystemExit(f"{args.shader}.frag does not declare: "
                         f"{', '.join(sorted(missing))}")

    ctx = moderngl.create_standalone_context()
    info = ctx.info.get("GL_RENDERER", "unknown")
    print(f"renderer : {info}")
    print(f"glsl     : {ctx.info.get('GL_SHADING_LANGUAGE_VERSION', '?')}")
    print(f"target   : {w}x{h} @ t={args.t}")

    prog = ctx.program(vertex_shader=VERTEX, fragment_shader=src)
    uniforms = {k: prog[k] for k in UNIFORM_DEFAULTS}

    vao = ctx.vertex_array(prog, [(ctx.buffer(np.array(
        [-1, -1, 3, -1, -1, 3], dtype="f4")), "2f", "in_pos")])

    fbo = ctx.simple_framebuffer((w, h), components=4)
    fbo.use()
    ctx.viewport = (0, 0, w, h)

    def maybe_set(name: str, value) -> None:
        """Set a uniform if the linker kept it.

        GLSL compilers drop uniforms the shader never reads, and moderngl then
        raises KeyError. fire.frag does not currently consume iTimeDelta,
        iFrame or iMouse — so absence is normal, not a bug. iTime and
        iResolution are required, because without them nothing would animate.
        """
        try:
            prog[name].value = value
        except KeyError:
            if name in ("iTime", "iResolution"):
                raise SystemExit(
                    f"fire.frag never reads {name}; the host cannot drive it")

    def draw(t: float, flush: bool = True) -> None:
        maybe_set("iResolution", (float(w), float(h), 1.0))
        maybe_set("iTime", t)
        maybe_set("iTimeDelta", 0.0)
        maybe_set("iFrame", 0)
        maybe_set("iMouse", (0.0, 0.0, 0.0, 0.0))
        maybe_set("iDate", (2026.0, 1.0, 1.0, args.clock))
        for k, loc in uniforms.items():
            loc.value = UNIFORM_DEFAULTS[k]
        vao.render(moderngl.TRIANGLES)
        if flush:
            fbo.read(components=3, alignment=1)  # forces completion

    # Warm up once so shader JIT / first-use costs do not pollute the timing.
    draw(args.t)
    if args.bench:
        n = args.bench
        t0 = time.perf_counter()
        for i in range(n):
            draw(i * 0.016, flush=False)
        data = fbo.read(components=3, alignment=1)  # sync
        ms = (time.perf_counter() - t0) * 1000.0 / n
        print(f"bench    : {ms:.3f} ms/frame  ({1000.0/ms:.0f} fps) "
              f"over {n} frames @ {w}x{h}")
        # Re-draw at the requested time. Without this the framebuffer still
        # holds the last benchmark frame (t = (n-1)*0.016), so the saved PNG
        # would not match --t and "deterministic output" would be a lie.
        draw(args.t)

    data = fbo.read(components=3, alignment=1)
    img = Image.frombytes("RGB", (w, h), data).transpose(Image.FLIP_TOP_BOTTOM)

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

    arr = np.asarray(img, dtype=np.float32)
    lum = arr.max(axis=2)
    print(f"wrote    : {out}")
    print(f"meanRGB  : R={arr[...,0].mean():.1f} "
          f"G={arr[...,1].mean():.1f} B={arr[...,2].mean():.1f}")
    print(f"lit      : {(lum > 12).mean()*100:.1f}% of pixels above 12")
    return 0


if __name__ == "__main__":
    sys.exit(main())

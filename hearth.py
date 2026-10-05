# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "moderngl>=5.12",
#   "pyglet>=2.0",
#   "numpy>=1.26",
#   "pillow>=10.0",
# ]
# ///
"""Hearth — fullscreen pixel-art fireplace for a second monitor.

Runs the same shaders/hearth.frag the tools and tests use. Nothing here knows
how a fireplace looks; it only knows how to put frames on a screen.

    uv run hearth.py                      # fullscreen on the configured monitor
    uv run hearth.py --monitor 1          # fullscreen on the second monitor
    uv run hearth.py --windowed 1280x720  # test mode, no fullscreen
    uv run hearth.py --frames 120         # render N frames then exit

Controls (fullscreen is borderless, so there is no title bar to click):
    F              toggle fullscreen / windowed
    Q or Esc       quit
    [ and ]        flame speed down / up
    - and =        flame intensity down / up
    , and .        pixel size down / up
    1..4           presets
    S              save a PNG of the current frame
    C              print the current settings
    Space          pause / resume
    R              restore startup settings
    H / F1         show / hide help
    W              cycle weather (including automatic)
    E              toggle event showcase

Settings come from hearth.toml next to this file; CLI flags override it.
"""
from __future__ import annotations

import argparse
import sys
import time
import tomllib
from pathlib import Path

import moderngl
import numpy as np
import pyglet
from PIL import Image
from pyglet.gl import GL_TRIANGLES

# pyglet 2.x moved the display/canvas API under `pyglet.display`; there is no
# importable `pyglet.canvas` module any more. Enumerating monitors is:
#     pyglet.display.get_display().get_screens()

ROOT = Path(__file__).resolve().parent
SHADER_DIR = ROOT / "shaders"
CONFIG = ROOT / "hearth.toml"

# --- host: identical contract to tools/render_still.py -----------------------
# The host owns the Shadertoy uniforms and the main() entry point; the shader
# owns its own u* uniforms. Both are generated the same way as in render_still
# so a change to the contract lands in one place.

VERTEX = """
#version 330 core
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

PREAMBLE = """
#version 330 core
uniform vec3 iResolution;
uniform float iTime;
uniform float iTimeDelta;
uniform int iFrame;
uniform vec4 iMouse;
uniform vec4 iDate;
"""

EPILOGUE = """
out vec4 outColor;
void main() {
    vec4 c = vec4(0.0, 0.0, 0.0, 1.0);
    mainImage(c, gl_FragCoord.xy);
    outColor = vec4(clamp(c.rgb, 0.0, 1.0), 1.0);
}
"""

# Keys that describe the launcher, not the art. Every shader accepts these.
LAUNCHER_KEYS = {"shader", "monitor", "vsync"}

# Uniform defaults have one source of truth. The launcher is distributed with
# its tools and shader directory, so a missing file should be reported clearly.
from tools.render_still import SHADERS
from tools.scene_clock import moscow_i_date

WEATHER_NAMES = ("Авто", "Ясно", "Снег", "Метель", "Облачно")
PRESET_NAMES = {1: "Вечер", 2: "Тихая ночь", 3: "Жаркий огонь", 4: "Ретро"}

# Which knobs the arrow-style keys move, and by how much per press.
STEPPED = {
    "uSpeed": 0.10, "uIntensity": 0.10, "uPixel": 1.0, "uSteps": 1.0,
    "uWarmth": 0.05, "uDetail": 0.05, "uEmbers": 0.10, "uRoom": 0.10,
    "uDither": 0.10, "uScale": 0.10, "uFps": 1.0, "uWall": 0.10,
}

PRESETS = {
    1: {"uIntensity": 1.05, "uWarmth": 0.50, "uPixel": 6.0, "uSpeed": 1.00,
        "uRoom": 0.85, "uSteps": 12.0, "uDither": 0.20},
    2: {"uIntensity": 0.75, "uWarmth": 0.30, "uPixel": 6.0, "uSpeed": 0.70,
        "uRoom": 0.65, "uSteps": 12.0, "uDither": 0.15},
    3: {"uIntensity": 1.45, "uWarmth": 0.75, "uPixel": 6.0, "uSpeed": 1.20,
        "uRoom": 0.90, "uSteps": 12.0, "uDither": 0.20},
    4: {"uIntensity": 1.05, "uWarmth": 0.50, "uPixel": 6.0, "uSpeed": 1.00,
        "uRoom": 0.85, "uSteps": 6.0, "uDither": 0.35},
}


def load_config(path: Path, shader: str) -> dict[str, float]:
    """Defaults for `shader`, overlaid with [hearth] from hearth.toml."""
    import re
    frag = SHADER_DIR / f"{shader}.frag"
    if not frag.exists():
        raise SystemExit(f"no such shader: {frag}")
    src = frag.read_text(encoding="utf-8")
    declared = re.findall(r"^\s*uniform\s+\w+\s+(u[A-Z]\w*)\s*;", src, re.M)
    values = {k: SHADERS[shader][k] for k in declared if k in SHADERS[shader]}

    if path.exists():
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
        section = cfg.get("hearth", {})
        # One hearth.toml serves every shader, so a pixel-art knob (uPixel,
        # uSteps...) is legitimately absent from `fire`. Treat anything that is
        # a real uniform of SOME shader as "not for this one" and ignore it;
        # only a key that is no uniform anywhere is a typo worth reporting.
        every_uniform = {k for v in SHADERS.values() for k in v}
        unknown = set(section) - set(values) - LAUNCHER_KEYS - every_uniform
        if unknown:
            raise SystemExit(f"hearth.toml has unknown keys: {sorted(unknown)}")
        for k, v in section.items():
            if k in values:
                values[k] = float(v)
    return values


class Hearth:
    def __init__(self, shader: str, values: dict[str, float],
                 windowed: str | None, monitor: int, vsync: bool):
        screens = pyglet.display.get_display().get_screens()
        if not windowed:
            if not 0 <= monitor < len(screens):
                raise SystemExit(
                    f"monitor {monitor} does not exist; this machine has "
                    f"{len(screens)}: " +
                    ", ".join(f"{i}:{s.width}x{s.height}"
                              for i, s in enumerate(screens)))
            screen = screens[monitor]
            self.window = pyglet.window.Window(screen.width, screen.height,
                                               caption="hearth",
                                               vsync=vsync, fullscreen=True,
                                               screen=screen)
        else:
            w, h = (int(v) for v in windowed.lower().split("x"))
            self.window = pyglet.window.Window(w, h, caption="hearth",
                                               vsync=vsync)

        # moderngl 5.12 changed create_context() to take everything except
        # `require` as keyword settings; passing the window positionally now
        # lands it in `require` and raises a TypeError. Try the modern form
        # first and fall back for 5.10/5.11.
        try:
            self.ctx = moderngl.create_context(window=self.window)
        except TypeError:
            self.ctx = moderngl.create_context(self.window)
        self.program = self.ctx.program(
            vertex_shader=VERTEX,
            fragment_shader=PREAMBLE + (SHADER_DIR / f"{shader}.frag")
                                 .read_text(encoding="utf-8") + EPILOGUE)
        self.vbo = self.ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4"))
        self.vao = self.ctx.vertex_array(self.program, [(self.vbo, "2f", "in_pos")])

        self.values = dict(values)
        self.initial_values = dict(values)
        self.loc = {}
        for k in self.values:
            # Uniforms the linker dropped (unused knobs) are normal; only
            # iTime/iResolution matter, and we set those separately.
            self.loc[k] = self.program.get(k, None)
        self.start = time.perf_counter()
        self.frame = 0
        self._last = self.start
        self.elapsed = 0.0
        self.paused = False
        self._closed = False
        self.shader = shader
        self.shots = 0
        self.help_visible = False
        self.last_activity = self.start
        self.cursor_visible = True
        self.preset_name = "Вечер" if all(values.get(k) == v for k, v in PRESETS[1].items()) else "Свои настройки"
        self.initial_preset_name = self.preset_name
        self.last_caption = ""
        self.notice_until = self.start + 5.0
        self.notice = pyglet.text.Label("H — помощь   ·   Space — пауза   ·   E — события",
                                       font_name="Segoe UI", font_size=12,
                                       color=(239, 210, 173, 255), anchor_x="center", y=22)
        self.help_background = pyglet.shapes.Rectangle(12, 12, 425, 240, color=(27, 20, 22))
        self.help_background.opacity = 230
        self.help_label = pyglet.text.Label(
            "Тихий вечер\n\n1–4   Настроение\nSpace   Пауза / продолжить\nW   Погода\nE   Редкие события: просмотр\n[ / ]   Скорость     - / =   Свет\nF   Полный экран     S   Снимок\nR   Сброс     H   Скрыть помощь\nEsc / Q   Выход",
            font_name="Segoe UI", font_size=12, color=(239, 210, 173, 255),
            x=26, y=235, anchor_y="top", multiline=True, width=395)

    def notify(self, text: str) -> None:
        self.notice.text = text
        self.notice_until = time.perf_counter() + 2.6
        self.last_activity = time.perf_counter()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.notify("Пауза · часы продолжают идти" if self.paused else "Продолжаем")

    def cycle_weather(self) -> None:
        if "uWeather" in self.values:
            weather = (int(self.values["uWeather"]) + 1) % 5
            self.values["uWeather"] = float(weather)
            self.notify("Погода: " + WEATHER_NAMES[weather])

    def toggle_showcase(self) -> None:
        if "uShowcase" in self.values:
            self.values["uShowcase"] = float(self.values["uShowcase"] < 0.5)
            self.notify("Просмотр событий: " + ("включён" if self.values["uShowcase"] else "выключен"))

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self.last_activity = time.perf_counter()

    def set_uniform(self, name: str, value: float) -> None:
        self.values[name] = max(0.0, value)

    def nudge(self, name: str, delta: float) -> None:
        self.set_uniform(name, self.values[name] + delta)
        self.notify(f"{'Скорость' if name == 'uSpeed' else 'Свет' if name == 'uIntensity' else 'Пиксели'}: {self.values[name]:.1f}")

    def on_draw(self, draw_overlay: bool = True) -> None:
        """Render one frame. This IS the on_draw handler.

        The name is not cosmetic: pyglet's push_handlers derives the event name
        from the attribute name, so a method called `draw` would be registered
        under the event "draw" and raise EventException: Unknown event "draw".
        Registering is therefore just `push_handlers(app.on_draw)`.

        It used to be called only from the --frames smoke path, which is why
        the interactive app opened a black window: the event loop had no
        handler and never painted anything.

        No window.flip() here — pyglet's event loop does that automatically
        after on_draw returns. Flipping manually as well leaves the buffer
        undefined at the wrong moment.
        """
        now = time.perf_counter()
        elapsed = now - self._last
        dt = min(elapsed, 0.1)
        self._last = now
        if not self.paused:
            self.elapsed += elapsed
        t = self.elapsed
        date = moscow_i_date()
        caption = f"Hearth — {self.preset_name} · {int(date[3]) // 3600:02}:{int(date[3]) // 60 % 60:02} МСК"
        if caption != self.last_caption:
            self.window.set_caption(caption)
            self.last_caption = caption
        visible = not self.window.fullscreen or self.help_visible or now - self.last_activity < 3.0
        if visible != self.cursor_visible:
            self.window.set_mouse_visible(visible)
            self.cursor_visible = visible

        w, h = self.window.get_framebuffer_size()
        self.ctx.viewport = (0, 0, w, h)
        for name, val in (("iResolution", (float(w), float(h), 1.0)),
                          ("iTime", t), ("iTimeDelta", dt),
                          ("iFrame", self.frame), ("iDate", date)):
            try:
                self.program[name].value = val
            except KeyError:
                pass
        for k, loc in self.loc.items():
            if loc is not None:
                loc.value = self.values[k]
        self.vao.render(GL_TRIANGLES)
        if draw_overlay:
            if self.help_visible:
                self.help_background.draw()
                self.help_label.draw()
            elif now < self.notice_until:
                self.notice.x = self.window.width / 2
                self.notice.draw()
        self.frame += 1

    def draw_once(self) -> None:
        """Render and present immediately, for the non-event-loop --frames path.

        on_draw does the same minus the flip, because the event loop presents
        the buffer itself and this path has no loop to do it.
        """
        self.on_draw()
        self.window.flip()

    def save_png(self) -> Path:
        """Draw and read the back buffer before presentation, then save a PNG.

        Reads ctx.screen (the default framebuffer) before a buffer swap,
        flipped back because GL's origin is
        bottom-left and PNG's is top-left.
        """
        self.on_draw(draw_overlay=False)
        w, h = self.window.get_framebuffer_size()
        # ModernGL caches the default framebuffer's initial dimensions.
        # Read the current extent explicitly after a resize/fullscreen change.
        data = self.ctx.screen.read(viewport=(0, 0, w, h), components=3, alignment=1)
        img = Image.frombytes("RGB", (w, h), data).transpose(
            Image.FLIP_TOP_BOTTOM)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = ROOT / "out" / f"hearth_{stamp}_{time.time_ns() % 1000000:06d}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        self.shots += 1
        return out

    def apply_preset(self, n: int) -> None:
        for k, v in PRESETS[n].items():
            if k in self.values:
                self.values[k] = v
        self.preset_name = PRESET_NAMES[n]
        self.notify(self.preset_name)

    def close(self) -> None:
        """Release GL objects, then the window, while the context is alive.

        Order matters. Without this, Python's exit-time garbage collection
        runs pyglet's ShaderProgram.__del__ against a context that has already
        been torn down, and pyglet raises
        "GLException(0x1282): Invalid operation" — after a perfectly
        successful run. Everything (program, VAO, buffer, context, window) has
        to go in reverse creation order, explicitly, before the process ends.
        """
        import gc
        if self._closed:
            return
        self._closed = True
        for overlay in (self.notice, self.help_label, self.help_background):
            overlay.delete()
        for obj in (self.vao, self.vbo, self.program):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        gc.collect()  # let those __del__s run now, with GL still valid
        try:
            self.ctx.release()
        except Exception:
            pass
        try:
            self.window.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shader", default=None, choices=sorted(SHADERS))
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--monitor", type=int, default=None,
                    help="display index for fullscreen (0 = primary)")
    ap.add_argument("--windowed", default=None, metavar="WxH")
    ap.add_argument("--frames", type=int, default=0,
                    help="render N frames then exit (for smoke tests)")
    ap.add_argument("--save", type=Path, default=None, metavar="PATH",
                    help="after --frames, write one PNG (same path as the S key)")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="override a uniform, repeatable")
    ap.add_argument("--vsync", action="store_true", default=None)
    ap.add_argument("--no-vsync", dest="vsync", action="store_false")
    args = ap.parse_args()

    cfg = tomllib.loads(args.config.read_text(encoding="utf-8")) \
        if args.config.exists() else {}
    section = cfg.get("hearth", {})
    monitor = args.monitor if args.monitor is not None \
        else int(section.get("monitor", 0))
    vsync = args.vsync if args.vsync is not None else bool(section.get("vsync", True))
    shader = args.shader or section.get("shader", "hearth")
    if shader not in SHADERS:
        raise SystemExit(f"unknown shader {shader!r}; available: {', '.join(sorted(SHADERS))}")
    if not args.windowed and args.monitor is None:
        screens = pyglet.display.get_display().get_screens()
        if not 0 <= monitor < len(screens):
            print(f"configured monitor {monitor} unavailable; opening on monitor 0")
            monitor = 0

    values = load_config(args.config, shader)
    for item in args.set:
        name, _, val = item.partition("=")
        if name not in values:
            raise SystemExit(f"unknown uniform {name!r}; known: "
                             f"{', '.join(sorted(values))}")
        values[name] = float(val)

    app = Hearth(shader, values, args.windowed, monitor, vsync)

    if args.frames:
        t0 = time.perf_counter()
        for _ in range(args.frames):
            app.draw_once()
        el = time.perf_counter() - t0
        print(f"rendered {args.frames} frames @ "
              f"{app.window.width}x{app.window.height} in {el:.2f}s "
              f"({args.frames/el:.1f} fps, {el/args.frames*1000:.2f} ms/frame)")
        if args.save:
            out = Path(args.save)
            out.parent.mkdir(parents=True, exist_ok=True)
            app.on_draw(draw_overlay=False)
            w, h = app.window.get_framebuffer_size()
            data = app.ctx.screen.read(viewport=(0, 0, w, h), components=3, alignment=1)
            Image.frombytes("RGB", (w, h), data).transpose(
                Image.FLIP_TOP_BOTTOM).save(out)
            print(f"saved {out}")
        app.close()
        return 0

    # Key constants are imported at module level on purpose. Doing this inside
    # the handler meant a wrong name raised ImportError on *every* keypress,
    # from inside a ctypes callback where the exception is swallowed — the app
    # looked alive but no key did anything.
    from pyglet.window import key as K

    def on_key_press(symbol, modifiers):
        app.last_activity = time.perf_counter()
        if symbol == K.ESCAPE and app.help_visible:
            app.help_visible = False
        elif symbol in (K.Q, K.ESCAPE):
            app.window.close()
        elif symbol == K.F:
            app.window.set_fullscreen(not app.window.fullscreen)
        elif symbol == K.SPACE:
            app.toggle_pause()
        elif symbol in (K.H, K.F1):
            app.help_visible = not app.help_visible
        elif symbol == K.W:
            app.cycle_weather()
        elif symbol == K.E:
            app.toggle_showcase()
        elif symbol == K.R:
            app.values.update(app.initial_values)
            app.preset_name = app.initial_preset_name
            app.notify("Настройки восстановлены")
        elif symbol == K.S:
            saved = app.save_png()
            print("saved", saved)
            app.notify("Снимок сохранён в out/")
        elif symbol == K.C:
            for name in sorted(app.values):
                print(f"  {name} = {app.values[name]:.2f}")
        elif symbol in (K.BRACKETLEFT, K.LEFT):
            app.nudge("uSpeed", -STEPPED["uSpeed"])
        elif symbol in (K.BRACKETRIGHT, K.RIGHT):
            app.nudge("uSpeed", +STEPPED["uSpeed"])
        elif symbol == K.MINUS:
            app.nudge("uIntensity", -STEPPED["uIntensity"])
        elif symbol == K.EQUAL:
            app.nudge("uIntensity", +STEPPED["uIntensity"])
        elif symbol == K.COMMA and "uPixel" in app.values:
            app.nudge("uPixel", -STEPPED["uPixel"])
        elif symbol == K.PERIOD and "uPixel" in app.values:
            app.nudge("uPixel", +STEPPED["uPixel"])
        elif K.NUM_1 <= symbol <= K.NUM_4:
            app.apply_preset(symbol - K.NUM_1 + 1)
            print(f"preset {symbol - K.NUM_1 + 1}")

    app.window.push_handlers(on_key_press)

    print(f"shader   : {shader}")
    print(f"display  : {app.window.width}x{app.window.height} "
          f"(index {monitor})")
    print("F fullscreen | Q/Esc quit | [ ] speed | - = intensity | , . pixel "
          "| 1-4 presets | Space pause | W weather | E events | H help | R reset | S save")
    print(f"settings : {args.config if args.config.exists() else '(defaults)'}")

    # pyglet derives the event name from the attribute name, so this must be
    # push_handlers(app.on_draw). Registering app.draw raises
    # EventException: Unknown event "draw" and the window stays black.
    app.window.push_handlers(app.on_draw)
    app.window.push_handlers(app.on_mouse_motion)

    def on_close():
        app.close()

    app.window.push_handlers(on_close=on_close)
    # The art advances at 12 fps. A 30 Hz UI avoids wasting GPU on identical
    # frames on high-refresh monitors, while keeping controls responsive.
    pyglet.app.run(interval=1 / 30)
    return 0


if __name__ == "__main__":
    sys.exit(main())

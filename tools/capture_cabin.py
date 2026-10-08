# /// script
# requires-python = ">=3.11"
# dependencies = ["moderngl>=5.12", "numpy>=1.26", "pillow>=10.0"]
# ///
"""Record the actual cabin shader to a PNG and short animated preview.

    uv run tools/capture_cabin.py

FrameRenderer is also used by the scene regression tests. No browser capture,
external assets, or second implementation of the art.
"""
from pathlib import Path
import argparse

import moderngl
import numpy as np
from PIL import Image

from render_still import SHADERS, VERTEX, build_fragment_source
from scene_clock import SNAPSHOT_CLOCK

ROOT = Path(__file__).resolve().parents[1]


class FrameRenderer:
    def __init__(self, size=(320, 180)):
        self.size = size
        self.ctx = moderngl.create_standalone_context()
        source, _ = build_fragment_source("hearth")
        self.program = self.ctx.program(vertex_shader=VERTEX, fragment_shader=source)
        self.buffer = self.ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4"))
        self.vao = self.ctx.vertex_array(self.program, [(self.buffer, "2f", "in_pos")])
        self.fbo = self.ctx.simple_framebuffer(size, components=3)

    def draw(self, t, clock_seconds=SNAPSHOT_CLOCK, **overrides):
        self.fbo.use()
        w, h = self.size
        self.ctx.viewport = (0, 0, w, h)
        self.program["iResolution"].value = (float(w), float(h), 1.0)
        self.program["iTime"].value = t
        self.program["iDate"].value = (2026.0, 1.0, 1.0, float(clock_seconds))
        for name, value in (SHADERS["hearth"] | overrides).items():
            self.program[name].value = value
        self.vao.render(moderngl.TRIANGLES)
        return Image.frombytes("RGB", (w, h), self.fbo.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def close(self):
        for resource in (self.fbo, self.vao, self.buffer, self.program, self.ctx):
            resource.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=float, default=55.0)
    parser.add_argument("--showcase", action="store_true")
    parser.add_argument("--name", default="cabin", help="output filename stem under out/")
    args = parser.parse_args()
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    renderer = FrameRenderer()
    try:
        values = {"uShowcase": float(args.showcase)}
        renderer.draw(args.start, **values).resize((1920, 1080), Image.Resampling.NEAREST).save(out / f"{args.name}.png")
        frames = [renderer.draw(args.start + i / 12.0, clock_seconds=SNAPSHOT_CLOCK + i / 12.0, **values) for i in range(60)]
        # A shared palette avoids GIF palette shimmer on the stationary furniture.
        samples = Image.new("RGB", (320, 180 * 5))
        for k, frame in enumerate(frames[::12]):
            samples.paste(frame, (0, k * 180))
        palette = samples.quantize(colors=256)
        frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE).resize((960, 540), Image.Resampling.NEAREST) for frame in frames]
        frames[0].save(out / f"{args.name}.gif", save_all=True, append_images=frames[1:],
                       duration=[80, 80, 90] * 20, loop=0, optimize=False, disposal=1)
        print(f"Saved {args.name}.png and {args.name}.gif under {out} (60 frames / 5 seconds)")
        # A real render contact sheet for reviewing event silhouettes and weather.
        cases = [
            ("COFFEE / CAT", 55.0, {"uWeather": 2}),
            ("CREEPER", 11.125, {"uShowcase": 1, "uWeather": 1}),
            ("SKELETON", 31.5, {"uShowcase": 1, "uWeather": 1}),
            ("ZOMBIE", 56.5, {"uShowcase": 1, "uWeather": 1}),
            ("BLIZZARD", 60.0, {"uWeather": 3}),
            ("CLOUDS", 60.0, {"uWeather": 4}),
            ("FULL MOON / SLEIGH", 4.8, {"uShowcase": 1, "uWeather": 1}),
            ("SLEEPY CAT", 56.3, {"uWeather": 1}),
        ]
        sheet = Image.new("RGB", (960, 4 * 292), (20, 16, 20))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(sheet)
        for k, (name, t, knobs) in enumerate(cases):
            frame = renderer.draw(t, **knobs).resize((480, 270), Image.Resampling.NEAREST)
            x, y = k % 2 * 480, k // 2 * 292
            sheet.paste(frame, (x, y + 22))
            draw.text((x + 8, y + 5), name, fill=(220, 197, 158))
        sheet.save(out / "living-cabin-sheet.png")
        day_sheet = Image.new("RGB", (960, 584), (20, 16, 20))
        draw = ImageDraw.Draw(day_sheet)
        for k, (name, mode, hour) in enumerate([
            ("NIGHT", 1, 21.25), ("DAWN", 2, 7.5),
            ("DAY", 3, 12), ("SUNSET", 4, 18.5),
        ]):
            frame = renderer.draw(55, clock_seconds=hour * 3600, uDayMode=mode,
                                  uWeather=1).resize((480, 270), Image.Resampling.NEAREST)
            x, y = k % 2 * 480, k // 2 * 292
            day_sheet.paste(frame, (x, y + 22))
            draw.text((x + 8, y + 5), name, fill=(220, 197, 158))
        day_sheet.save(out / "daylight.png")
    finally:
        renderer.close()


if __name__ == "__main__":
    main()

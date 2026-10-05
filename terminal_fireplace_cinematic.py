import os
import sys
import time
import math
import random
import shutil

# ============================================================
# TERMINAL FIREPLACE — CINEMATIC
#
# Full-screen ambient fire rendered with Unicode half-blocks.
# Each terminal row represents TWO vertical fire pixels.
#
# Controls:
#   Q / ESC / Ctrl+C  exit
#   + / -              flame intensity
#   [ / ]              flame height
#   S                  sparks on/off
#   L                  logs on/off
#   R                  reset settings
#
# No external packages required.
# ============================================================

ESC = "\x1b"
CSI = ESC + "["

ALT_ON = CSI + "?1049h"
ALT_OFF = CSI + "?1049l"
HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
HOME = CSI + "H"
CLEAR = CSI + "2J"
RESET = CSI + "0m"

FPS = 22

# Quantized cinematic palette: black -> ember -> deep red -> orange -> gold -> pale yellow.
# Truecolor output is intentionally quantized to reduce terminal traffic.
PALETTE = [
    (7,   7,   7),
    (18,  8,   5),
    (31,  9,   4),
    (48,  10,  3),
    (68,  12,  3),
    (91,  15,  2),
    (118, 21,  2),
    (148, 29,  1),
    (177, 39,  1),
    (202, 53,  2),
    (222, 72,  4),
    (236, 94,  7),
    (246, 120, 11),
    (252, 149, 20),
    (255, 179, 36),
    (255, 207, 72),
    (255, 228, 118),
    (255, 242, 168),
    (255, 249, 207),
    (255, 255, 238),
]

BG = PALETTE[0]


def enable_ansi():
    if os.name == "nt":
        os.system("")


def term_size():
    s = shutil.get_terminal_size((120, 38))
    # Width/height are exact terminal cells. We render exactly this area.
    return max(40, s.columns), max(14, s.lines)


def set_title(text):
    print(f"{ESC}]0;{text}\x07", end="", flush=True)


def fg(rgb):
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m"


def bg(rgb):
    r, g, b = rgb
    return f"\x1b[48;2;{r};{g};{b}m"


def get_key_nonblocking():
    if os.name == "nt":
        try:
            import msvcrt
            if not msvcrt.kbhit():
                return None

            ch = msvcrt.getwch()

            # Ignore Windows extended-key prefix.
            if ch in ("\x00", "\xe0"):
                if msvcrt.kbhit():
                    msvcrt.getwch()
                return None

            if ch == "\x1b":
                return "ESC"
            return ch
        except Exception:
            return None

    try:
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            return "ESC" if ch == "\x1b" else ch
    except Exception:
        pass

    return None


class RawTerminal:
    def __init__(self):
        self.old = None

    def __enter__(self):
        enable_ansi()

        if os.name != "nt":
            try:
                import termios
                import tty
                self.old = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                self.old = None

        print(ALT_ON + HIDE_CURSOR + CLEAR + HOME, end="", flush=True)
        set_title("Fireplace")
        return self

    def __exit__(self, *args):
        if os.name != "nt" and self.old is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old)
            except Exception:
                pass

        print(RESET + SHOW_CURSOR + ALT_OFF, end="", flush=True)
        set_title("Terminal")


class Fireplace:
    def __init__(self, cols, rows):
        self.intensity = 1.0
        self.height_scale = 1.0
        self.sparks_enabled = True
        self.logs_enabled = True

        self.phase = 0.0
        self.sparks = []

        self.resize(cols, rows)

    def resize(self, cols, rows):
        self.cols = cols
        self.rows = rows

        # Two vertical simulation pixels per terminal row.
        self.pw = cols
        self.ph = rows * 2

        self.heat = [[0.0] * self.pw for _ in range(self.ph)]

        # Precomputed normalized coordinates.
        half = max(1.0, (self.pw - 1) / 2.0)
        self.xnorm = [(x - half) / half for x in range(self.pw)]

    def reset_controls(self):
        self.intensity = 1.0
        self.height_scale = 1.0
        self.sparks_enabled = True
        self.logs_enabled = True

    def palette_color(self, heat):
        if heat <= 0.003:
            return BG

        # Gamma curve: keeps deep reds visible while making hot cores bright.
        t = min(1.0, max(0.0, heat))
        t = t ** 0.72
        idx = min(len(PALETTE) - 1, int(t * (len(PALETTE) - 1)))
        return PALETTE[idx]

    def seed_fire(self):
        w, h = self.pw, self.ph
        base_y = h - 1
        center = (w - 1) / 2.0

        # Main bed spans almost the whole monitor, but edges taper naturally.
        for x in range(w):
            nx = abs(self.xnorm[x])

            # Soft edge falloff, not a hard rectangle.
            envelope = 1.0
            if nx > 0.82:
                envelope = max(0.0, 1.0 - (nx - 0.82) / 0.18)

            large_wave = (
                0.73
                + 0.08 * math.sin(x * 0.095 + self.phase * 1.25)
                + 0.06 * math.sin(x * 0.031 - self.phase * 0.72)
            )

            noise = random.uniform(-0.10, 0.21)
            value = (large_wave + noise) * envelope * self.intensity
            self.heat[base_y][x] = min(1.0, max(0.0, value))

        # Hot pockets: these become distinct flame tongues.
        pockets = max(5, w // 20)
        for _ in range(pockets):
            cx = random.randrange(max(1, int(w * 0.05)), max(2, int(w * 0.95)))
            radius = random.randint(2, max(3, w // 22))
            power = random.uniform(0.90, 1.08) * self.intensity

            for dx in range(-radius, radius + 1):
                x = cx + dx
                if 0 <= x < w:
                    u = abs(dx) / (radius + 1)
                    bell = (1.0 - u * u) ** 1.8
                    self.heat[base_y][x] = max(
                        self.heat[base_y][x],
                        min(1.0, power * bell)
                    )

        # Feed a few rows above base too, preventing a one-line source.
        for yoff in range(1, min(5, h)):
            y = h - 1 - yoff
            decay = 1.0 - yoff * 0.06
            below = self.heat[min(h - 1, y + 1)]
            row = self.heat[y]
            for x in range(w):
                row[x] = max(row[x], below[x] * decay * random.uniform(0.91, 1.02))

    def propagate(self):
        w, h = self.pw, self.ph
        src = self.heat
        dst = [[0.0] * w for _ in range(h)]

        # Preserve the fuel bed.
        dst[-1] = src[-1][:]
        if h > 1:
            dst[-2] = src[-2][:]

        # Fire height control works mostly through cooling.
        height_factor = max(0.65, min(1.45, self.height_scale))

        # Upward propagation.
        for y in range(h - 3, -1, -1):
            altitude = (h - 1 - y) / max(1, h - 1)

            # More meandering higher in the flame.
            wind = math.sin(self.phase * 0.68 + y * 0.105) * (0.7 + altitude * 1.7)

            # Height scale reduces/increases cooling.
            base_cooling = (0.0065 + altitude * 0.0145) / height_factor

            sy1 = y + 1
            sy2 = min(h - 1, y + 2)
            sy3 = min(h - 1, y + 3)

            row1 = src[sy1]
            row2 = src[sy2]
            row3 = src[sy3]
            out = dst[y]

            for x in range(w):
                jitter = random.choice((-1, 0, 0, 0, 1))
                drift = int(round(wind)) + jitter

                xd = max(0, min(w - 1, x + drift))
                xm1 = max(0, xd - 1)
                xp1 = min(w - 1, xd + 1)
                xm2 = max(0, xd - 2)
                xp2 = min(w - 1, xd + 2)

                # Weighted blur upward produces soft, connected tongues.
                v = (
                    row1[xd] * 0.34
                    + row1[xm1] * 0.12
                    + row1[xp1] * 0.12
                    + row2[xd] * 0.18
                    + row2[xm2] * 0.06
                    + row2[xp2] * 0.06
                    + row3[xd] * 0.12
                )

                # Ragged tips and holes.
                cooling = base_cooling + random.uniform(0.001, 0.013 + altitude * 0.010)

                if random.random() < 0.0025 + altitude * 0.009:
                    cooling += random.uniform(0.015, 0.055)

                v -= cooling

                # Mild suppression near far edges.
                nx = abs(self.xnorm[x])
                if nx > 0.90:
                    v *= max(0.0, 1.0 - (nx - 0.90) * 5.5)

                out[x] = max(0.0, min(1.0, v))

        self.heat = dst

    def add_logs_and_embers(self):
        if not self.logs_enabled:
            return

        w, h = self.pw, self.ph
        # Keep logs in the lowest ~8 simulation pixels.
        y0 = max(0, h - 8)

        # Two overlapping log silhouettes, embedded into heat.
        logs = [
            (int(w * 0.20), int(w * 0.76), -0.035),
            (int(w * 0.30), int(w * 0.84),  0.030),
        ]

        for x0, x1, slope in logs:
            length = max(1, x1 - x0)
            for x in range(x0, x1):
                center_y = h - 4 + int((x - (x0 + x1) / 2) * slope)
                for dy in (-1, 0, 1):
                    y = center_y + dy
                    if 0 <= y < h:
                        # Logs are dark, with hot cracks.
                        if random.random() < 0.06:
                            self.heat[y][x] = max(self.heat[y][x], random.uniform(0.62, 0.90))
                        else:
                            self.heat[y][x] *= random.uniform(0.22, 0.48)

        # Ember bed along the bottom: organic hot spots.
        for y in range(y0, h):
            depth = (y - y0) / max(1, h - 1 - y0)
            for x in range(w):
                if random.random() < 0.12 + depth * 0.20:
                    self.heat[y][x] = max(
                        self.heat[y][x],
                        random.uniform(0.28, 0.80) * self.intensity
                    )

    def spawn_sparks(self):
        if not self.sparks_enabled:
            return

        # Spark source sits around upper flame region, not the very bottom.
        chance = 0.24 * self.intensity
        if random.random() < chance:
            count = 1 if random.random() < 0.86 else random.randint(2, 3)

            for _ in range(count):
                x = random.uniform(self.pw * 0.16, self.pw * 0.84)
                y = random.uniform(self.ph * 0.52, self.ph * 0.80)

                self.sparks.append({
                    "x": x,
                    "y": y,
                    "vx": random.uniform(-0.12, 0.12),
                    "vy": random.uniform(-0.78, -0.34),
                    "life": random.uniform(0.50, 1.0),
                    "heat": random.uniform(0.76, 1.0),
                })

    def update_sparks(self):
        wind = math.sin(self.phase * 0.55) * 0.035
        alive = []

        for s in self.sparks:
            s["x"] += s["vx"] + wind
            s["y"] += s["vy"]

            s["vx"] *= 0.994
            s["vy"] -= 0.002
            s["life"] -= random.uniform(0.010, 0.024)

            if (
                s["life"] > 0
                and 0 <= s["x"] < self.pw
                and 0 <= s["y"] < self.ph
            ):
                alive.append(s)

        self.sparks = alive[-100:]

    def update(self):
        self.phase += 0.095
        self.seed_fire()
        self.propagate()
        self.add_logs_and_embers()
        self.spawn_sparks()
        self.update_sparks()

    def apply_sparks_to_frame(self, frame):
        for s in self.sparks:
            x = int(s["x"])
            y = int(s["y"])

            if 0 <= x < self.pw and 0 <= y < self.ph:
                value = max(0.45, min(1.0, s["heat"] * s["life"]))
                frame[y][x] = max(frame[y][x], value)

                # Tiny bloom below the brightest sparks.
                if value > 0.72:
                    for dx in (-1, 1):
                        xx = x + dx
                        if 0 <= xx < self.pw:
                            frame[y][xx] = max(frame[y][xx], value * 0.28)

    def render(self):
        # Copy refs because spark drawing should not alter simulation.
        frame = [row[:] for row in self.heat]
        self.apply_sparks_to_frame(frame)

        # IMPORTANT:
        # exactly self.rows visual terminal rows are generated.
        # No trailing newline -> no scrolling -> no blank area at bottom.
        output = [HOME]

        last_fg = None
        last_bg = None

        for row in range(self.rows):
            top_y = row * 2
            bot_y = min(self.ph - 1, top_y + 1)

            top = frame[top_y]
            bottom = frame[bot_y]

            for x in range(self.cols):
                tc = self.palette_color(top[x])
                bc = self.palette_color(bottom[x])

                # Unicode upper half block:
                # foreground = upper pixel
                # background = lower pixel
                if tc != last_fg:
                    output.append(fg(tc))
                    last_fg = tc

                if bc != last_bg:
                    output.append(bg(bc))
                    last_bg = bc

                output.append("▀")

            # Explicit cursor move via newline except after final row.
            # CR avoids terminals preserving horizontal position weirdly.
            if row != self.rows - 1:
                output.append(RESET)
                output.append("\r\n")
                last_fg = None
                last_bg = None

        output.append(RESET)
        return "".join(output)


def main():
    fireplace = None
    last_size = None
    next_frame = time.perf_counter()

    with RawTerminal():
        try:
            while True:
                cols, rows = term_size()

                if last_size != (cols, rows):
                    old_settings = None

                    if fireplace is not None:
                        old_settings = (
                            fireplace.intensity,
                            fireplace.height_scale,
                            fireplace.sparks_enabled,
                            fireplace.logs_enabled,
                        )

                    fireplace = Fireplace(cols, rows)

                    if old_settings:
                        (
                            fireplace.intensity,
                            fireplace.height_scale,
                            fireplace.sparks_enabled,
                            fireplace.logs_enabled,
                        ) = old_settings

                    last_size = (cols, rows)
                    print(CLEAR + HOME, end="", flush=True)

                key = get_key_nonblocking()

                if key:
                    lower = key.lower()

                    if key == "ESC" or lower == "q":
                        break
                    elif key in ("+", "="):
                        fireplace.intensity = min(1.35, fireplace.intensity + 0.07)
                    elif key == "-":
                        fireplace.intensity = max(0.58, fireplace.intensity - 0.07)
                    elif key == "]":
                        fireplace.height_scale = min(1.45, fireplace.height_scale + 0.07)
                    elif key == "[":
                        fireplace.height_scale = max(0.65, fireplace.height_scale - 0.07)
                    elif lower == "s":
                        fireplace.sparks_enabled = not fireplace.sparks_enabled
                    elif lower == "l":
                        fireplace.logs_enabled = not fireplace.logs_enabled
                    elif lower == "r":
                        fireplace.reset_controls()

                fireplace.update()
                sys.stdout.write(fireplace.render())
                sys.stdout.flush()

                next_frame += 1.0 / FPS
                delay = next_frame - time.perf_counter()

                if delay > 0:
                    time.sleep(delay)
                else:
                    # If terminal rendering stalls, don't accumulate lag.
                    next_frame = time.perf_counter()

        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

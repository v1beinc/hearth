"""Compact native controls in logical window coordinates, including HiDPI."""
import pyglet
from pyglet.window import mouse


def timestamp(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02}"


class ControlPanel:
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.tab = "music"
        self.items = []
        self.hits = {}
        self.labels = {}
        self.bars = {}
        self.size = None
        self.dragging = None
        self.error = ""

    def toggle(self, tab="music"):
        self.visible = not self.visible or self.tab != tab
        self.tab = tab
        self.dragging = None
        self.size = None
        if self.visible:
            self.app.help_visible = False

    def close(self):
        for item in self.items:
            item.delete()
        self.items.clear()
        self.size = None

    def layout(self):
        size = (self.app.window.width, self.app.window.height, self.tab)
        if size == self.size:
            return
        self.close()
        self.size = size
        self.batch = pyglet.graphics.Batch()
        self.hits, self.labels, self.bars = {}, {}, {}
        self.scale = min(1.0, (size[0] - 24) / 400, (size[1] - 24) / 310)
        self.scale = max(0.25, self.scale)
        self.x = size[0] - 12 - 400 * self.scale
        self.y = 12

        def rect(x, y, width, height, color, layer=1):
            item = pyglet.shapes.Rectangle(self.x + x * self.scale, self.y + y * self.scale,
                                           width * self.scale, height * self.scale, color=color,
                                           batch=self.batch, group=pyglet.graphics.Group(order=layer))
            self.items.append(item)
            return item

        def label(name, text, x, y, font=11, color=(239, 215, 184, 255)):
            item = pyglet.text.Label(text, font_name="Segoe UI", font_size=font * self.scale,
                                     x=self.x + x * self.scale, y=self.y + y * self.scale,
                                     color=color, anchor_y="center", batch=self.batch,
                                     group=pyglet.graphics.Group(order=3))
            self.labels[name] = item
            self.items.append(item)

        def button(name, text, x, y, width):
            rect(x, y, width, 32, (101, 65, 43) if name == self.tab else (68, 49, 43))
            self.hits[name] = (x, y, width, 32)
            label(name, text, x + 10, y + 16)

        def slider(name, y):
            rect(20, y, 360, 5, (89, 70, 62))
            self.bars[name] = rect(20, y, 1, 5, (222, 165, 100), 2)
            self.hits[name] = (20, y - 9, 360, 23)

        background = rect(0, 0, 400, 310, (30, 24, 25), 0)
        background.opacity = 246
        rect(0, 307, 400, 3, (182, 119, 70))
        label("header", "Тихий вечер", 20, 281, 15)
        button("close", "×", 352, 265, 30)
        button("music", "Музыка", 20, 222, 172)
        button("scene", "Сцена", 202, 222, 178)
        if self.tab == "music":
            label("track", "", 20, 197, 10)
            slider("seek", 170)
            label("time", "", 20, 151, 10)
            button("back", "−30 с", 20, 103, 74)
            button("play", "Слушать", 104, 103, 112)
            button("forward", "+30 с", 226, 103, 74)
            button("repeat", "", 310, 103, 70)
            label("volume", "", 20, 87, 10)
            slider("volume", 68)
            button("open", "Открыть трек", 20, 16, 155)
            label("status", "", 188, 32, 9)
        else:
            for name, text, y in (("uSpeed", "Скорость анимации", 199),
                                  ("uPixel", "Размер пикселя", 148),
                                  ("uScale", "Размер пламени", 97)):
                if name in self.app.values:
                    label(name, text, 20, y, 10)
                    slider(name, y - 23)
            button("ambient", "", 20, 17, 165)
            label("ambient_volume", "9 / 0 — громкость камина", 195, 33, 9)

    def draw(self):
        self.layout()
        music = self.app.music
        if self.tab == "music":
            title = music.title
            self.labels["track"].text = title if len(title) <= 43 else title[:40] + "…"
            self.labels["time"].text = f"{timestamp(music.position)} / {timestamp(music.duration)}"
            self.labels["play"].text = "Пауза" if music.playing else "Слушать"
            self.labels["repeat"].text = "↻ Вкл" if music.repeat else "↻ Выкл"
            self.labels["volume"].text = f"Громкость музыки · {round(music.volume * 100)}%"
            self.labels["status"].text = self.error or ("Играет в фоне" if music.playing else "Локальный аудиофайл")
            for name, fraction in (("seek", music.position / music.duration if music.duration else 0),
                                   ("volume", music.volume)):
                self.bars[name].width = 360 * self.scale * fraction
        else:
            for name, (low, high) in self.app.CONTROL_LIMITS.items():
                if name not in self.bars:
                    continue
                value = self.app.values[name]
                caption = {"uSpeed": "Скорость анимации", "uPixel": "Размер пикселя", "uScale": "Размер пламени"}[name]
                self.labels[name].text = f"{caption} · {value:.2f}" + ("×" if name != "uPixel" else "")
                self.bars[name].width = 360 * self.scale * max(0, min(1, (value - low) / (high - low)))
            self.labels["ambient"].text = "Камин: вкл" if self.app.sound.mode else "Камин: выкл"
        self.batch.draw()

    def press(self, x, y, button):
        if not self.visible or button != mouse.LEFT:
            return False
        self.layout()
        local_x, local_y = (x - self.x) / self.scale, (y - self.y) / self.scale
        for name, (left, bottom, width, height) in self.hits.items():
            if left <= local_x <= left + width and bottom <= local_y <= bottom + height:
                if name in self.bars:
                    self.dragging = name
                    self.drag(x)
                else:
                    self.app.panel_action(name)
                return True
        return 0 <= local_x <= 400 and 0 <= local_y <= 310

    def drag(self, x):
        if not self.visible or not self.dragging:
            return
        fraction = max(0, min(1, ((x - self.x) / self.scale - 20) / 360))
        self.app.panel_slider(self.dragging, fraction)

    def release(self):
        self.dragging = None

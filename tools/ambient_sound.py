"""Lazy native playback of Hearth's original loops; no audio until requested."""
from pathlib import Path


class AmbientSound:
    def __init__(self, directory: Path):
        self.directory = directory
        self.mode = 0  # 0 silent, 1 fireplace + weather, 2 ambience + original lofi
        self.volume = 0.35
        self.paused = False
        self.hidden = False
        self.players = {}
        self._last = None

    def set_mode(self, mode):
        mode = int(mode) % 3
        if mode and not self.players:
            import pyglet
            try:
                for name in ("fire", "wind", "lofi"):
                    source = pyglet.media.load(str(self.directory / f"{name}.wav"), streaming=False)
                    player = pyglet.media.Player()
                    player.loop = True
                    player.volume = 0
                    player.queue(source)
                    self.players[name] = player
            except Exception:
                self.close()
                raise
        self.mode = mode
        self._last = None

    def update(self, weather=0):
        state = (self.mode, self.volume, self.paused, self.hidden, weather)
        if state == self._last:
            return
        self._last = state
        enabled = self.mode > 0 and not self.paused and not self.hidden and self.volume > 0
        wind = {0: 0.22, 1: 0.08, 2: 0.22, 3: 0.65, 4: 0.15}.get(int(weather), 0.22)
        gains = {"fire": 0.55, "wind": wind, "lofi": 0.75 if self.mode == 2 else 0}
        for name, player in self.players.items():
            gain = gains[name] * self.volume if enabled else 0
            player.volume = gain
            if gain:
                if not player.playing:
                    player.play()
            elif player.playing:
                player.pause()

    def close(self):
        for player in self.players.values():
            player.delete()
        self.players.clear()
        self.mode = 0
        self._last = None

"""Streaming local audio, independent of the scene and its overlays."""
from pathlib import Path


class NativeMusic:
    def __init__(self, path: Path):
        self.path = path
        self.player = None
        self.duration = 0.0
        self.volume = 0.35
        self.repeat = True
        self.ended = False

    @property
    def playing(self):
        return self.player is not None and self.player.playing

    @property
    def position(self):
        if self.ended:
            return self.duration
        return min(self.duration, self.player.time) if self.player else 0.0

    @property
    def title(self):
        if self.path.name == "lofi.wav":
            return "Hearth · original lofi"
        if self.path.name == "lofi-mix.mp3":
            return "Lofi Hip Hop Mix"
        return self.path.stem

    def load(self, path: Path):
        import pyglet
        # Decode on demand; a long mix must not be loaded entirely into RAM.
        source = pyglet.media.load(str(path), streaming=True)
        if source.audio_format is None:
            raise ValueError("В файле нет аудио")
        player = pyglet.media.Player()
        try:
            player.volume = self.volume
            player.loop = self.repeat
            player.queue(source)
        except Exception:
            player.delete()
            raise
        resume = self.playing
        self.close()
        self.path = Path(path)
        self.duration = float(source.duration or 0)
        self.player = player
        self.ended = False
        player.push_handlers(on_player_eos=self._on_end)
        if resume:
            player.play()

    def _on_end(self):
        self.ended = True

    def toggle(self):
        if self.player is None or self.ended:
            self.load(self.path)
        if self.playing:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds):
        if self.player is None or self.ended:
            self.load(self.path)
        self.player.seek(max(0.0, min(float(seconds), max(0, self.duration - 0.05))))
        self.ended = False

    def set_volume(self, value):
        self.volume = max(0.0, min(1.0, float(value)))
        if self.player:
            self.player.volume = self.volume

    def toggle_repeat(self):
        self.repeat = not self.repeat
        if self.player:
            self.player.loop = self.repeat

    def close(self):
        if self.player:
            self.player.delete()
            self.player = None


def choose_audio_file(owner=None, *, settings=False, save=False):
    """Native open/save dialog, also used for portable JSON settings."""
    import sys
    if sys.platform == "win32":
        import ctypes as c
        from ctypes import wintypes as w

        class OpenFileName(c.Structure):
            _fields_ = [
                ("lStructSize", w.DWORD), ("hwndOwner", w.HWND), ("hInstance", w.HINSTANCE),
                ("lpstrFilter", w.LPCWSTR), ("lpstrCustomFilter", w.LPWSTR),
                ("nMaxCustFilter", w.DWORD), ("nFilterIndex", w.DWORD),
                ("lpstrFile", w.LPWSTR), ("nMaxFile", w.DWORD),
                ("lpstrFileTitle", w.LPWSTR), ("nMaxFileTitle", w.DWORD),
                ("lpstrInitialDir", w.LPCWSTR), ("lpstrTitle", w.LPCWSTR),
                ("Flags", w.DWORD), ("nFileOffset", w.WORD), ("nFileExtension", w.WORD),
                ("lpstrDefExt", w.LPCWSTR), ("lCustData", c.c_ssize_t),
                ("lpfnHook", c.c_void_p), ("lpTemplateName", w.LPCWSTR),
                ("pvReserved", c.c_void_p), ("dwReserved", w.DWORD), ("FlagsEx", w.DWORD),
            ]

        buffer = c.create_unicode_buffer(32768)
        if save:
            buffer.value = "hearth-settings.json"
        dialog = OpenFileName()
        dialog.lStructSize = c.sizeof(dialog)
        dialog.hwndOwner = owner
        dialog.lpstrFile = c.cast(buffer, w.LPWSTR)
        dialog.nMaxFile = len(buffer)
        dialog.nFilterIndex = 1
        dialog.lpstrFilter = "Настройки Hearth\0*.json\0\0" if settings else "Аудио\0*.mp3;*.wav;*.ogg;*.flac;*.m4a\0Все файлы\0*.*\0\0"
        dialog.lpstrTitle = ("Экспорт настроек" if save else "Импорт настроек") if settings else "Музыка для тихого вечера"
        dialog.lpstrDefExt = "json" if settings else None
        # Explorer, existing path/file, preserve cwd, don't add private files to Recents.
        dialog.Flags = 0x80000 | 0x800 | 0x8 | 0x2000000 | (0x2 if save else 0x1000)
        function = c.windll.comdlg32.GetSaveFileNameW if save else c.windll.comdlg32.GetOpenFileNameW
        function.argtypes = [c.POINTER(OpenFileName)]
        function.restype = w.BOOL
        return Path(buffer.value) if function(c.byref(dialog)) else None
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    try:
        if settings:
            function = filedialog.asksaveasfilename if save else filedialog.askopenfilename
            path = function(title="Настройки Hearth", defaultextension=".json", filetypes=[("Hearth", "*.json")])
        else:
            path = filedialog.askopenfilename(title="Музыка для тихого вечера")
        return Path(path) if path else None
    finally:
        root.destroy()

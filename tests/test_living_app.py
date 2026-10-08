"""Actual event-loop check of help, weather keys, and wall time during pause."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECK = r'''
# /// script
# requires-python = ">=3.11"
# dependencies = ["moderngl>=5.12", "pyglet>=2.0", "numpy>=1.26", "pillow>=10.0"]
# ///
import sys
from pathlib import Path
import pyglet
pyglet.options['audio'] = ('silent',)
from pyglet.window import key as K
from PIL import Image

ROOT = Path(r"__ROOT__")
sys.path.insert(0, str(ROOT))
import hearth

wall = [2026.0, 10.0, 5.0, 19 * 3600.0]
hearth.moscow_i_date = lambda: tuple(wall)
app = None
state = {}
errors = []

def guarded(fn):
    def callback(dt):
        try:
            fn()
        except Exception as error:
            errors.append(repr(error))
            pyglet.app.exit()
    return callback

def pause():
    app.window.dispatch_event('on_key_press', K.H, 0)
    app.window.dispatch_event('on_key_press', K.SPACE, 0)
    state['time'] = app.elapsed
    assert app.paused and app.help_visible

def advance_wall():
    assert app.elapsed == state['time']
    wall[3] += 61.0
    app.window.dispatch_event('on_key_press', K.W, 0)
    app.window.dispatch_event('on_key_press', K.E, 0)
    app.window.dispatch_event('on_key_press', K.T, 0)
    app.window.dispatch_event('on_key_press', K.M, 0)
    app.window.dispatch_event('on_key_press', K.M, 0)
    app.window.dispatch_event('on_key_press', K.NUM_0, 0)
    app.window.set_size(1280, 720)

def check_and_finish():
    assert app.elapsed == state['time'], 'animation continued during pause'
    assert app.program['iDate'].value == tuple(wall), 'wall clock stopped during pause'
    assert app.values['uWeather'] == 1
    assert app.values['uShowcase'] == 1
    assert app.values['uDayMode'] == 2
    assert app.sound.mode == 2
    assert round(app.sound.volume, 2) == .4
    assert all(player.loop and not player.playing for player in app.sound.players.values())
    w, h = app.window.get_framebuffer_size()
    assert app.window.get_size() == (1280, 720), 'window did not resize'
    assert app.program['iResolution'].value == (float(w), float(h), 1.0), 'shader kept the old framebuffer size'
    assert app.ctx.viewport == (0, 0, w, h), 'viewport kept the old window size'
    app.framebuffer_image().save(ROOT / 'out' / 'living-help.png')
    snapshot = app.save_png()
    with Image.open(snapshot) as image:
        assert image.size == (w, h), 'snapshot kept the old window size'
    snapshot.unlink()
    assert app.ctx.error == 'GL_NO_ERROR', 'snapshot left an OpenGL error'
    app.on_draw()  # A screenshot must not break the next interactive frame.
    app.window.dispatch_event('on_key_press', K.SPACE, 0)
    assert all(player.playing for player in app.sound.players.values())
    app.on_hide()
    assert all(not player.playing for player in app.sound.players.values())
    app.on_show()
    assert all(player.playing for player in app.sound.players.values())
    app.window.dispatch_event('on_key_press', K.R, 0)
    assert app.sound.mode == 0 and app.values['uDayMode'] == 1
    assert all(not player.playing for player in app.sound.players.values())
    app.window.dispatch_event('on_key_press', K.Q, 0)
    pyglet.app.exit()

Original = hearth.Hearth
class Observed(Original):
    def __init__(self, *args, **kwargs):
        global app
        super().__init__(*args, **kwargs)
        app = self
        assert app.window._resizable
        pyglet.clock.schedule_once(guarded(pause), .25)
        pyglet.clock.schedule_once(guarded(advance_wall), .55)
        pyglet.clock.schedule_once(guarded(check_and_finish), .9)

hearth.Hearth = Observed
sys.argv = ['hearth.py', '--windowed', '960x540']
hearth.main()
if errors: raise SystemExit('; '.join(errors))
assert 'time' in state
print('OK: help, weather, events, and independent live clock during pause')
'''


def test_help_weather_and_clock_in_real_event_loop(tmp_path):
    script = tmp_path / "check_living_app.py"
    script.write_text(CHECK.replace("__ROOT__", str(ROOT)), encoding="utf-8")
    result = subprocess.run(["uv", "run", "--no-project", str(script)],
                            capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: help, weather, events" in result.stdout

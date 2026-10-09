"""Exercise real native widgets, audio transport, and independent scene controls."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

CHECK = r'''
# /// script
# dependencies = ["moderngl>=5.12", "pyglet>=2.0", "numpy>=1.26", "pillow>=10.0"]
# ///
import sys
import webbrowser
import traceback
import wave
from pathlib import Path
import pyglet
pyglet.options['audio'] = ('silent',)
from pyglet.window import key as K, mouse
import numpy as np
ROOT = Path(r"__ROOT__")
sys.path.insert(0, str(ROOT))
import hearth
hearth.moscow_i_date = lambda: (2026., 10., 8., 21 * 3600.)
def no_browser(*args, **kwargs):
    raise AssertionError('native player opened a browser')
webbrowser.open = no_browser
app = None
errors = []
state = {}

def key(symbol):
    app.window.dispatch_event('on_key_press', symbol, 0)

def click(name, fraction=.5):
    app.panel.layout()
    x, y, width, height = app.panel.hits[name]
    x = app.panel.x + (x + width * fraction) * app.panel.scale
    y = app.panel.y + (y + height * .5) * app.panel.scale
    app.window.dispatch_event('on_mouse_press', x, y, mouse.LEFT, 0)
    app.window.dispatch_event('on_mouse_release', x, y, mouse.LEFT, 0)

def guarded(fn):
    def callback(dt):
        try:
            fn()
        except Exception as exc:
            errors.append(traceback.format_exc())
            pyglet.app.exit()
    return callback

def open_player():
    key(K.SPACE)
    key(K.Y)
    assert app.panel.visible and app.panel.tab == 'music'
    assert app.music.duration == 48 and not app.music.playing
    click('play')
    assert app.music.playing
    click('seek', .5)
    assert abs(app.music.position - 24) < .2
    click('volume', .2)
    assert abs(app.music.volume - .2) < .001
    assert abs(app.music.player.volume - .2) < .001
    click('repeat')
    assert not app.music.repeat and not app.music.player.loop
    click('back')
    assert app.music.position < .2
    click('forward')
    assert abs(app.music.position - 30) < .2
    click('play')
    assert not app.music.playing
    click('play')
    app.on_draw()
    app.framebuffer_image().save(ROOT / 'out' / 'native-music.png')
    click('close')
    assert not app.panel.visible and app.music.playing
    app.on_hide()
    assert app.music.playing, 'minimizing stopped background music'
    app.on_show()
    key(K.G)
    assert app.panel.visible and app.panel.tab == 'scene'
    before = dict(app.values)
    app.on_draw(draw_overlay=False)
    state['frame'] = np.asarray(app.framebuffer_image())
    key(K.UP)
    assert app.values['uSpeed'] > before['uSpeed']
    assert all(app.values[k] == before[k] for k in before if k != 'uSpeed')
    click('uSpeed', .8)
    assert abs(app.values['uSpeed'] - 2.4) < .001
    assert app.values['uPixel'] == before['uPixel'] and app.values['uScale'] == before['uScale']
    app.on_draw(draw_overlay=False)
    assert np.array_equal(state['frame'], np.asarray(app.framebuffer_image())), 'speed changed frozen geometry'
    old_speed = app.values['uSpeed']
    click('uPixel', .75)
    assert app.values['uPixel'] != before['uPixel']
    assert app.values['uSpeed'] == old_speed and app.values['uScale'] == before['uScale']
    app.on_draw(draw_overlay=False)
    assert not np.array_equal(state['frame'], np.asarray(app.framebuffer_image())), 'pixel control had no visual effect'
    app.on_draw()
    app.framebuffer_image().save(ROOT / 'out' / 'native-scene.png')
    # Changing speed at a live phase must never rewind or jump the scene.
    key(K.SPACE)
    state['phase'] = app.scene_time
    key(K.DOWN)
    assert 0 <= app.scene_time - state['phase'] < .1
    app.set_uniform('uSpeed', 0)
    state['frozen'] = app.scene_time
    # The native panel must fit a small, portrait and large window.
    for width, height in ((480, 270), (360, 640), (1920, 1080)):
        app.window.set_size(width, height)
        app.on_draw()
        assert app.panel.x >= 0 and app.panel.y >= 0
        assert app.panel.x + 400 * app.panel.scale <= width
        assert app.panel.y + 310 * app.panel.scale <= height
    app.window.set_size(960, 540)
    # Loading an invalid file preserves the current working player.
    player = app.music.player
    try:
        app.music.load(ROOT / 'music' / '_missing.mp3')
    except Exception:
        pass
    else:
        raise AssertionError('invalid audio accepted')
    assert app.music.player is player and app.music.playing

def check_background_and_loop():
    assert app.scene_time == state['frozen'], 'zero speed failed to freeze the current phase'
    assert app.music.playing, 'scene controls stopped music'
    key(K.ESCAPE)
    assert not app.panel.visible and app.music.playing
    # A short source verifies real end-of-stream behavior without a long wait.
    short = Path(__file__).with_suffix('.wav')
    with wave.open(str(short), 'wb') as stream:
        stream.setparams((1, 2, 22050, 4410, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 4410)
    app.music.toggle_repeat()
    assert app.music.repeat
    app.music.load(short)

def stop_repeat():
    assert app.music.playing and not app.music.ended, 'repeat stopped at end-of-stream'
    app.music.toggle_repeat()

def finish():
    assert app.music.ended and not app.music.playing, 'non-repeating track failed to end'
    app.music.toggle()
    assert app.music.playing and not app.music.ended, 'finished track failed to replay'
    key(K.Q)
    assert app.music.player is None, 'exit leaked the player'
    pyglet.app.exit()

Original = hearth.Hearth
class Observed(Original):
    def __init__(self, *args, **kwargs):
        global app
        super().__init__(*args, **kwargs)
        app = self
        self.music.path = ROOT / 'assets' / 'audio' / 'lofi.wav'
        pyglet.clock.schedule_once(guarded(open_player), .25)
        pyglet.clock.schedule_once(guarded(check_background_and_loop), .9)
        pyglet.clock.schedule_once(guarded(stop_repeat), 1.5)
        pyglet.clock.schedule_once(guarded(finish), 1.9)

hearth.Hearth = Observed
sys.argv = ['hearth.py', '--windowed', '960x540', '--no-settings']
try:
    hearth.main()
finally:
    if app: app.close()
if errors: raise SystemExit('; '.join(errors))
assert 'frozen' in state
print('OK: native music, mouse transport, background playback, independent speed/pixels and continuous phase')
'''


def test_native_transport_and_scene_controls(tmp_path):
    script = tmp_path / "native_check.py"
    script.write_text(CHECK.replace("__ROOT__", str(ROOT)), encoding="utf-8")
    result = subprocess.run(["uv", "run", "--no-project", str(script)],
                            capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'OK: native music' in result.stdout

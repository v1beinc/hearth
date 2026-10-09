"""Two real launches: click the cabin, export/import, and restore saved settings."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

CHECK = r'''
# /// script
# dependencies = ["moderngl>=5.12", "pyglet>=2.0", "numpy>=1.26", "pillow>=10.0"]
# ///
import sys
import json
import traceback
from pathlib import Path
import pyglet
pyglet.options['audio'] = ('silent',)
from pyglet.window import key as K, mouse
import numpy as np
ROOT = Path(r"__ROOT__")
sys.path.insert(0, str(ROOT))
import hearth
from tools.settings import read_settings
hearth.moscow_i_date = lambda: (2026., 10., 9., 21 * 3600.)
base = Path(__file__).parent
preferences = base / 'local.json'
export = base / 'export.json'
bad = base / 'bad.json'
app = None
errors = []
phase = int(sys.argv[1])
def key(symbol):
    app.window.dispatch_event('on_key_press', symbol, 0)
def click_room(x, y):
    fit = min(app.window.width / 320, app.window.height / 180)
    app.window.dispatch_event('on_mouse_press', (x - 160) * fit + app.window.width / 2,
                              (y - 90) * fit + app.window.height / 2, mouse.LEFT, 0)
def click_panel(name):
    app.panel.layout()
    x, y, width, height = app.panel.hits[name]
    app.window.dispatch_event('on_mouse_press', app.panel.x + (x + width / 2) * app.panel.scale,
                             app.panel.y + (y + height / 2) * app.panel.scale, mouse.LEFT, 0)
def check(dt):
    try:
        if phase == 1:
            key(K.SPACE)
            app.scene_time = 55
            app.on_draw(draw_overlay=False)
            original = np.asarray(app.framebuffer_image())
            # Logical hit testing must match the shader at any aspect ratio.
            for width, height in ((960, 540), (360, 640), (1440, 540)):
                app.window.set_size(width, height)
                click_room(80, 53)
                assert 'coffee' in app.interactions.triggered
            app.window.set_size(960, 540)
            app.on_draw(draw_overlay=False)
            fresh = np.asarray(app.framebuffer_image())
            assert not np.array_equal(original, fresh), 'coffee click had no visual response'
            app.framebuffer_image().save(ROOT / 'out' / 'fresh-coffee.png')
            click_room(240, 35)
            assert 'wood' in app.interactions.triggered
            click_room(167, 24)
            assert 'cat' in app.interactions.triggered
            app.scene_time += 2
            app.on_draw(draw_overlay=False)
            app.framebuffer_image().save(ROOT / 'out' / 'interactive-cabin.png')
            assert app.program['iInteraction'].value[0] > .5
            assert app.program['iInteraction'].value[2] > 0
            app.set_uniform('uSpeed', 1.7)
            app.set_uniform('uPixel', 8)
            app.music.set_volume(.22)
            app.sound.volume = .41
            app.music.repeat = False
            app.music.load(ROOT / 'assets' / 'audio' / 'lofi.wav')
            app.music.seek(17)
            key(K.K)
            assert app.panel.visible and app.panel.tab == 'settings'
            # Configuration buttons exercise the actual picker callback boundary.
            hearth.choose_audio_file = lambda *args, **kwargs: export
            click_panel('export_settings')
            portable = read_settings(export)
            assert portable['scene']['uSpeed'] == 1.7 and portable['scene']['uPixel'] == 8
            assert portable['audio']['music_volume'] == .22
            assert portable['music'] == {}, 'portable export leaked a local track path'
            app.set_uniform('uSpeed', .4)
            app.music.set_volume(.8)
            click_panel('import_settings')
            assert app.values['uSpeed'] == 1.7 and app.music.volume == .22
            bad.write_text('{"version":1,"scene":{"uSpeed":999}}', encoding='utf-8')
            hearth.choose_audio_file = lambda *args, **kwargs: bad
            before = app.settings_snapshot()
            click_panel('import_settings')
            assert app.settings_snapshot() == before, 'invalid import changed live state'
            click_panel('save_settings')
            app.on_draw()
            app.framebuffer_image().save(ROOT / 'out' / 'native-settings.png')
            # A click on the panel must not reach objects behind it.
            interactions = dict(app.interactions.triggered)
            click_panel('save_settings')
            assert app.interactions.triggered == interactions
        else:
            assert app.values['uSpeed'] == 1.7 and app.values['uPixel'] == 8
            assert abs(app.music.volume - .22) < .001 and app.sound.volume == .41
            assert not app.music.repeat and not app.music.playing
            assert app.window.get_size() == (960, 540)
            assert app.music.player is None, 'restoring settings started music automatically'
            key(K.Y)
            assert abs(app.music.position - 17) < .2 and not app.music.playing
        key(K.Q)
        pyglet.app.exit()
    except Exception:
        errors.append(traceback.format_exc())
        pyglet.app.exit()
Original = hearth.Hearth
class Observed(Original):
    def __init__(self, *args, **kwargs):
        global app
        super().__init__(*args, **kwargs)
        app = self
        pyglet.clock.schedule_once(check, .3)
hearth.Hearth = Observed
sys.argv = ['hearth.py', '--settings', str(preferences)]
if phase == 1: sys.argv += ['--windowed', '960x540']
try: hearth.main()
finally:
    if app: app.close()
if errors: raise SystemExit('; '.join(errors))
assert preferences.exists()
print('OK: settings and interactive objects, phase', phase)
'''


def test_export_import_interactions_and_restart(tmp_path):
    script = tmp_path / 'check_settings.py'
    script.write_text(CHECK.replace('__ROOT__', str(ROOT)), encoding='utf-8')
    for phase in (1, 2):
        result = subprocess.run(['uv', 'run', '--no-project', str(script), str(phase)],
                                capture_output=True, text=True, timeout=120, cwd=ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'OK: settings and interactive objects' in result.stdout

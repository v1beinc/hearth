"""Regression checks for the cabin, rather than the earlier fire-only shader.

These check the actual GPU pixels: animation boundaries, controls, composition,
and integer upscaling. Art direction still needs visual inspection.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from capture_cabin import FrameRenderer
from render_still import SHADERS


@pytest.fixture(scope="module")
def scene():
    renderer = FrameRenderer()
    yield renderer
    renderer.close()


def pixels(scene, time=12.0, **values):
    return np.asarray(scene.draw(time, **values), dtype=np.int16)


def test_every_cabin_control_is_active(scene):
    assert set(SHADERS["hearth"]) <= set(scene.program)


def test_quantized_clock_and_pause(scene):
    assert np.array_equal(pixels(scene, 12.0), pixels(scene, 12.04))
    assert np.array_equal(pixels(scene, 12.0, uSpeed=0), pixels(scene, 34.0, uSpeed=0))
    assert not np.array_equal(pixels(scene, 12.0), pixels(scene, 13.0))


def test_fire_is_warm_and_confined_to_firebox(scene):
    a = pixels(scene)
    flame = (a[..., 0] > 210) & (a[..., 1] > 65) & (a[..., 2] < 175)
    # Remove the separate candle on the mantel from this flame measurement.
    flame[:80] = False
    y, x = np.where(flame)
    assert len(x) > 200
    assert x.min() >= 135 and x.max() < 187
    assert y.min() >= 88 and y.max() < 142
    # The flame retains colour instead of becoming the old solid white blob.
    assert not np.any(np.all(a[88:142, 135:187] > 235, axis=2))


def test_moonlight_and_firelight_have_distinct_palettes(scene):
    a = pixels(scene)
    night = a[39:63, 35:59].mean(axis=(0, 1))
    stone = a[100:137, 121:133].mean(axis=(0, 1))
    assert night[2] > night[0] * 1.5
    assert stone[0] > stone[2] * 1.3


def test_intensity_lights_the_room_and_warmth_changes_fire(scene):
    bright = pixels(scene, uIntensity=1.5)
    dim = pixels(scene, uIntensity=0.3)
    assert bright[85:142, 115:134].mean() > dim[85:142, 115:134].mean() * 1.2
    red = pixels(scene, uWarmth=0)
    gold = pixels(scene, uWarmth=1)
    assert gold[95:132, 140:183, 1].mean() > red[95:132, 140:183, 1].mean()


def test_motion_does_not_turn_the_whole_scene_into_noise(scene):
    a, b = pixels(scene, 12.0), pixels(scene, 12.1)
    assert np.abs(a - b).mean() < 8
    # Geometry of the bench and bookshelf is stationary even as the light flickers.
    assert np.abs(a[55:95, 234:289] - b[55:95, 234:289]).mean() < 5


def test_coffee_steam_moves_and_is_confined_to_the_mug(scene):
    a = pixels(scene, 12, uSteam=1)
    b = pixels(scene, 12, uSteam=0)
    changed = np.any(a != b, axis=2)
    assert changed.sum() > 8
    allowed = np.zeros(changed.shape, dtype=bool)
    allowed[108:124, 70:89] = True
    assert not np.any(changed & ~allowed)
    c = pixels(scene, 13, uSteam=1)
    assert not np.array_equal(a[108:124, 70:89], c[108:124, 70:89])


def test_clock_hands_follow_wall_time_not_animation_time(scene):
    midnight = pixels(scene, 12, clock_seconds=0)
    nine = pixels(scene, 12, clock_seconds=9 * 3600)
    noon = pixels(scene, 12, clock_seconds=12 * 3600)
    assert np.array_equal(midnight, noon)
    changed = np.any(midnight != nine, axis=2)
    assert changed.sum() > 3
    allowed = np.zeros(changed.shape, dtype=bool)
    allowed[45:65, 151:172] = True
    assert not np.any(changed & ~allowed)
    # At 09:00 the hour hand points left; 00:00 points up.
    assert nine[54:56, 158:160].mean() < midnight[54:56, 158:160].mean()


@pytest.mark.parametrize("time", [11.125, 31.5, 56.5])
def test_each_window_visitor_is_visible_and_cannot_enter_the_room(scene, time):
    a = pixels(scene, time, uShowcase=1, uWeather=1, uLife=1)
    b = pixels(scene, time, uShowcase=1, uWeather=1, uLife=0)
    changed = np.any(a != b, axis=2)
    assert changed[67:93, 35:88].sum() > 100
    # Life may also draw the cat. All differences above the rug stay in the glass.
    allowed = np.zeros(changed.shape, dtype=bool)
    allowed[39:92, 35:88] = True
    allowed[130:, :] = True
    assert not np.any(changed & ~allowed)


def test_visitors_arrive_wait_and_leave(scene):
    def visitor_area(t):
        a = pixels(scene, t, uShowcase=1, uWeather=1, uLife=1)
        b = pixels(scene, t, uShowcase=1, uWeather=1, uLife=0)
        return np.any(a[67:93, 35:88] != b[67:93, 35:88], axis=2).sum()
    assert visitor_area(7) == 0
    assert visitor_area(11.125) > 100
    assert visitor_area(15) == 0


def test_weather_can_hide_the_moon_and_make_a_blizzard(scene):
    clear = pixels(scene, 60, uWeather=1, uLife=0)
    snow = pixels(scene, 60, uWeather=2, uLife=0)
    blizzard = pixels(scene, 60, uWeather=3, uLife=0)
    clouds = pixels(scene, 60, uWeather=4, uLife=0)
    def flakes(a):
        crop = a[67:92, 35:88]
        return ((crop[..., 1] > 110) & (crop[..., 2] > 130)).sum()
    assert flakes(blizzard) > flakes(snow) + 35
    assert flakes(snow) > flakes(clear)
    assert clouds[45:57, 67:80].mean() < clear[45:57, 67:80].mean() * 0.9


def test_automatic_weather_changes_without_moving_indoor_objects(scene):
    a = pixels(scene, 55, uWeather=0, uLife=0)
    b = pixels(scene, 415, uWeather=0, uLife=0)
    assert np.abs(a[39:92, 35:88] - b[39:92, 35:88]).mean() > 3


def test_sleigh_needs_a_visible_full_moon(scene):
    def sky_difference(t, weather, showcase=1):
        a = pixels(scene, t, uShowcase=showcase, uWeather=weather, uLife=1)
        b = pixels(scene, t, uShowcase=showcase, uWeather=weather, uLife=0)
        return np.any(a[39:65, 35:88] != b[39:65, 35:88], axis=2).sum()
    assert sky_difference(4.8, 1) > 20
    assert sky_difference(4.8, 4) == 0
    assert sky_difference(606, 1, showcase=0) == 0  # same scheduled pass, crescent moon


def test_cat_arrives_breathes_and_eventually_leaves(scene):
    def cat_mask(t):
        a = pixels(scene, t, uLife=1)
        b = pixels(scene, t, uLife=0)
        return np.any(a[142:, :] != b[142:, :], axis=2)
    assert cat_mask(0).sum() == 0
    assert cat_mask(30).sum() > 100
    assert cat_mask(55).sum() > 250
    assert cat_mask(180).sum() == 0
    assert not np.array_equal(cat_mask(55), cat_mask(57))


@pytest.mark.parametrize("start, end, direction", [(35, 41, 1), (148, 155, -1)])
def test_cat_lowers_and_raises_her_body_without_a_pose_jump(scene, start, end, direction):
    centers = []
    for time in np.arange(start + 0.01, end, 1 / 12):
        a = pixels(scene, float(time), uLife=1)
        b = pixels(scene, float(time), uLife=0)
        # Lower silhouette excludes floating Zs and outdoor visitors.
        mask = np.any(a[149:, 145:215] != b[149:, 145:215], axis=2)
        y, _ = np.where(mask)
        assert len(y) > 200
        centers.append(y.mean())
    assert (centers[-1] - centers[0]) * direction > 1
    # A single-frame switch used to drop the whole body several art pixels.
    assert np.max(np.abs(np.diff(centers))) < 0.5


def test_window_reflects_firelight_without_losing_its_cool_palette(scene):
    dark = pixels(scene, 12, uIntensity=0, uWeather=1, uLife=0)
    bright = pixels(scene, 12, uIntensity=1.5, uWeather=1, uLife=0)
    reflection = (bright - dark)[70:88, 73:88].mean(axis=(0, 1))
    assert reflection[0] > 1
    assert reflection[0] > reflection[2] * 2
    sky = bright[42:60, 39:57].mean(axis=(0, 1))
    assert sky[2] > sky[0] * 1.5


def test_integer_upscale_matches_native_art(scene):
    large = FrameRenderer((1920, 1080))
    try:
        expected = np.repeat(np.repeat(pixels(scene), 6, axis=0), 6, axis=1)
        actual = pixels(large)
        assert np.abs(actual - expected).mean() < 0.1
        # Each output block is exactly constant: no filtering or subpixel blur.
        assert np.array_equal(actual[::6, ::6], actual[5::6, 5::6])
    finally:
        large.close()


@pytest.mark.parametrize("size", [
    (640, 480), (360, 640), (840, 360),
    (1366, 768), (1920, 1080), (2560, 1440), (3840, 2160),
    (3440, 1440), (1080, 1920),
])
def test_room_remains_visible_on_other_aspects(size):
    renderer = FrameRenderer(size)
    try:
        a = pixels(renderer)
        hot = (a[..., 0] > 210) & (a[..., 1] > 65) & (a[..., 2] < 175)
        y, x = np.where(hot)
        assert len(x) > 100
        assert x.min() > 0 and x.max() < size[0] - 1
        assert y.min() > 0 and y.max() < size[1] - 1
        # Check the window as well as the fire: fitting only the hearth could
        # leave the left of the cabin clipped on narrow or portrait screens.
        fit = min(size[0] / 320, size[1] / 180)
        x0 = int(size[0] / 2 + (40 - 160) * fit)
        x1 = int(size[0] / 2 + (57 - 160) * fit)
        y0 = int(size[1] / 2 - (137 - 90) * fit)
        y1 = int(size[1] / 2 - (121 - 90) * fit)
        assert 0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]
        glass = a[y0:y1, x0:x1].mean(axis=(0, 1))
        assert glass[2] > glass[0] * 1.5
    finally:
        renderer.close()

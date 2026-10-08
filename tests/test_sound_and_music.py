"""Check shipped audio headroom, loop boundaries and softened crackles."""
from pathlib import Path
import wave

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name,seconds', [('fire', 24), ('wind', 24), ('lofi', 48)])
def test_shipped_audio_has_headroom_and_a_quiet_loop_boundary(name, seconds):
    with wave.open(str(ROOT / 'assets' / 'audio' / f'{name}.wav')) as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        assert stream.getframerate() == 22050
        assert stream.getnframes() == seconds * 22050
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(float) / 32767
    assert .025 < np.sqrt(np.mean(samples ** 2)) < .2
    assert np.max(np.abs(samples)) <= .781
    assert abs(samples[-1] - samples[0]) < .08


def test_fire_avoids_loud_full_band_clicks():
    with wave.open(str(ROOT / 'assets' / 'audio' / 'fire.wav')) as stream:
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(float) / 32767
    power = np.abs(np.fft.rfft(samples)) ** 2
    frequencies = np.fft.rfftfreq(len(samples), 1 / 22050)
    assert np.max(np.abs(samples)) <= .301
    assert power[frequencies > 4000].sum() / power.sum() < .01
    assert np.max(np.abs(np.diff(samples))) < .10

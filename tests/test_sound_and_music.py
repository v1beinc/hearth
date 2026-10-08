"""Check shipped audio and the native player's restricted local page server."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
import sys
import wave

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.music_page import MusicPage


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


def test_music_page_serves_only_player_files_and_closes(monkeypatch):
    opened = []
    monkeypatch.setattr('tools.music_page.webbrowser.open', lambda url, **kwargs: opened.append(url))
    page = MusicPage()
    try:
        url = page.open()
        assert page.open() == url and opened == [url, url]
        assert page.server.server_address[0] == '127.0.0.1'
        with urlopen(url, timeout=3) as response:
            body = response.read().decode('utf-8')
            assert 'music.js' in body and 'LTphVIore3A' in body
            assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
        with urlopen(url + 'music.js', timeout=3) as response:
            assert 'new YT.Player' in response.read().decode('utf-8')
        for route in ('hearth.toml', '../hearth.py', '.git/config'):
            with pytest.raises(HTTPError) as error:
                urlopen(url + route, timeout=3)
            assert error.value.code == 404
    finally:
        page.close()
    assert page.server is None and not page.thread

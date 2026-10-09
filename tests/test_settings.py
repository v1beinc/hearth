"""Portable settings, validation and atomic preservation of working files."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.settings import SettingsError, read_settings, validate, write_settings


def test_portable_example_round_trip(tmp_path):
    data = read_settings(ROOT / 'config.example.json')
    path = tmp_path / 'вечер.json'
    write_settings(path, data)
    assert read_settings(path) == data
    assert 'music' in data and not data['music']


@pytest.mark.parametrize('section,key,value', [
    ('scene', 'uSpeed', -1), ('scene', 'uPixel', 100), ('scene', 'uWeather', 1.5),
    ('scene', 'uScale', float('nan')), ('scene', 'uWarmth', True),
    ('audio', 'music_volume', '0.5'), ('audio', 'repeat', 1),
    ('window', 'width', 0), ('window', 'height', 720.5),
    ('music', 'position', float('inf')), ('music', 'path', '\0broken'),
])
def test_invalid_values_never_replace_working_settings(tmp_path, section, key, value):
    path = tmp_path / 'config.json'
    original = read_settings(ROOT / 'config.example.json')
    write_settings(path, original)
    damaged = json.loads(json.dumps(original))
    damaged[section][key] = value
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        write_settings(path, damaged)
    assert path.read_bytes() == before


@pytest.mark.parametrize('data', [{}, {'version': 2}, {'version': True},
                                  {'version': 1, 'scene': []}, {'version': 1, 'scene': {'uSpeeed': 1}}])
def test_unknown_versions_and_malformed_sections_are_rejected(data):
    with pytest.raises(SettingsError):
        validate(data)


def test_interrupted_replace_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    data = read_settings(ROOT / 'config.example.json')
    write_settings(path, data)
    before = path.read_bytes()
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr('tools.settings.os.replace', fail)
    data['scene']['uSpeed'] = 2
    with pytest.raises(OSError):
        write_settings(path, data)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('payload', [
    '{"version":1,"scene":{"uSpeed":' + '9' * 400 + '}}',
    '[' * 2000 + '0' + ']' * 2000,
])
def test_extreme_invalid_json_is_reported_without_crashing(tmp_path, payload):
    path = tmp_path / 'broken.json'
    path.write_text(payload, encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        read_settings(path)
    assert path.read_bytes() == before

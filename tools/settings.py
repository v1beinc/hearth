"""Versioned JSON preferences. Validate everything before changing live state."""
import json
import math
import os
from pathlib import Path
import tempfile

VERSION = 1
LIMITS = {
    "uIntensity": (0, 2), "uSpeed": (0, 3), "uWarmth": (0, 1),
    "uScale": (.5, 2), "uDetail": (0, 1), "uEmbers": (0, 1),
    "uRoom": (0, 1), "uPixel": (1, 20), "uFps": (1, 60),
    "uDither": (0, 1), "uSteps": (2, 32), "uWall": (0, 1),
    "uSteam": (0, 1), "uWeather": (0, 4), "uShowcase": (0, 1),
    "uLife": (0, 1), "uDayMode": (0, 4),
}


class SettingsError(ValueError):
    pass


def number(value, low, high, field, integer=False):
    if type(value) not in (float, int) or not low <= value <= high or not math.isfinite(value):
        raise SettingsError(f"{field}: ожидается число от {low} до {high}")
    if integer and int(value) != value:
        raise SettingsError(f"{field}: ожидается целое число")
    return int(value) if integer else float(value)


def boolean(value, field):
    if type(value) is not bool:
        raise SettingsError(f"{field}: ожидается true или false")
    return value


def validate(data):
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != VERSION:
        raise SettingsError("Неподдерживаемая версия настроек (нужна version: 1)")
    unknown = set(data) - {"version", "shader", "scene", "window", "audio", "music"}
    if unknown:
        raise SettingsError(f"Неизвестные разделы: {', '.join(sorted(unknown))}")
    shader = data.get("shader", "hearth")
    if shader not in ("hearth", "hearth2", "fire"):
        raise SettingsError("Неизвестный вид сцены")
    result = {"version": VERSION, "shader": shader}
    for section in ("scene", "window", "audio", "music"):
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise SettingsError(f"{section}: ожидается объект")
        result[section] = {}
        allowed = {
            "scene": set(LIMITS), "window": {"width", "height", "fullscreen"},
            "audio": {"ambient_enabled", "ambient_volume", "music_volume", "repeat"},
            "music": {"path", "position"},
        }[section]
        if set(values) - allowed:
            raise SettingsError(f"Неизвестные параметры в {section}: {', '.join(sorted(set(values) - allowed))}")
        for key, value in values.items():
            field = f"{section}.{key}"
            if section == "scene":
                low, high = LIMITS[key]
                value = number(value, low, high, field, key in ("uWeather", "uShowcase", "uLife", "uDayMode"))
            elif key in ("fullscreen", "ambient_enabled", "repeat"):
                value = boolean(value, field)
            elif key in ("width", "height"):
                value = number(value, 240 if key == "width" else 180, 16384, field, True)
            elif key.endswith("volume"):
                value = number(value, 0, 1, field)
            elif key == "position":
                value = number(value, 0, 7 * 86400, field)
            elif key == "path":
                if not isinstance(value, str) or len(value) > 32767 or "\0" in value:
                    raise SettingsError("music.path: неверный путь")
            result[section][key] = value
    return result


def read_settings(path):
    try:
        if Path(path).stat().st_size > 128 * 1024:
            raise SettingsError("Файл настроек слишком большой")
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return validate(data)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, SettingsError):
            raise
        raise SettingsError(f"Не удалось прочитать настройки: {exc}") from exc


def write_settings(path, data):
    """Replace atomically; a failed write preserves the previous working file."""
    payload = json.dumps(validate(data), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

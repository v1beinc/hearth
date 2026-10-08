# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26"]
# ///
"""Synthesize Hearth's original seamless sound loops; no recordings or samples.

    uv run tools/generate_audio.py

The quiet electric-piano arrangement, bass and drums are composed here. Fire
and wind are filtered noise with circular envelopes. Fixed seed, PCM16 WAV.
"""
from pathlib import Path
import wave

import numpy as np

RATE = 22050
ROOT = Path(__file__).resolve().parents[1]


def normalize(samples, rms):
    samples = samples - samples.mean()
    samples *= rms / max(float(np.sqrt(np.mean(samples ** 2))), 1e-9)
    # Leave headroom for mixing and avoid clipping even on crackle transients.
    samples *= min(1.0, 0.78 / max(float(np.max(np.abs(samples))), 1e-9))
    return samples


def noise(rng, count, cutoff, highpass=0):
    spectrum = np.fft.rfft(rng.normal(size=count))
    frequency = np.fft.rfftfreq(count, 1 / RATE)
    spectrum *= np.exp(-(frequency / cutoff) ** 2)
    if highpass:
        spectrum *= 1 - np.exp(-(frequency / highpass) ** 2)
    spectrum[0] = 0
    return normalize(np.fft.irfft(spectrum, n=count), 1)


def add_loop(track, sound, start):
    index = (int(start * RATE) + np.arange(len(sound))) % len(track)
    np.add.at(track, index, sound)


def make_loops():
    rng = np.random.default_rng(18271)
    n = RATE * 24
    time = np.arange(n) / RATE
    fire = noise(rng, n, 1000, 50) * 0.045
    fire += noise(rng, n, 130) * 0.025
    for start in rng.uniform(0, 24, 110):
        age = np.arange(int(RATE * rng.uniform(0.025, 0.13))) / RATE
        click = rng.normal(size=len(age)) * np.exp(-age / 0.016)
        click *= np.minimum(age / 0.0015, 1) * rng.uniform(0.035, 0.16)
        add_loop(fire, click, start)
    gust = 0.55 + 0.22 * np.sin(2 * np.pi * time / 24) + 0.15 * np.sin(2 * np.pi * time / 8)
    wind = noise(rng, n, 550, 65) * gust

    music = np.zeros(RATE * 48)
    beat = 0.75  # 80 BPM, sixteen bars, four original chord voicings.
    chords = [(52, 55, 59, 62), (48, 52, 55, 59), (43, 47, 50, 54), (50, 54, 57, 64)]

    def piano(note, duration=4):
        age = np.arange(int(duration * RATE)) / RATE
        frequency = 440 * 2 ** ((note - 69) / 12)
        attack = 1 - np.exp(-age / 0.015)
        envelope = attack * np.exp(-age / 1.5) * (1 - np.exp(-(duration - age) / 0.03))
        phase = 2 * np.pi * frequency * age
        tone = np.sin(phase + 0.35 * np.sin(phase * 2) * np.exp(-age / 0.6))
        tone += 0.14 * np.sin(phase * 2) + 0.05 * np.sin(phase * 3)
        return tone * envelope

    for bar in range(8):
        start = bar * 8 * beat
        chord = chords[bar % 4]
        for k, note in enumerate(chord):
            sound = piano(note) * 0.065
            add_loop(music, sound, start + k * 0.04)
            add_loop(music, sound * 0.18, start + k * 0.04 + beat * 0.5)
        # Sparse upper notes and an understated walking bass, no borrowed melody.
        for k, choice in enumerate([2, 1, 3]):
            add_loop(music, piano(chord[choice] + 12, 2.5) * 0.038, start + (2 + k * 2) * beat)
        for k in range(4):
            age = np.arange(int(1.3 * RATE)) / RATE
            frequency = 440 * 2 ** ((chord[0] - 12 - 69) / 12)
            bass = np.sin(2 * np.pi * frequency * age) * np.exp(-age / 0.65)
            bass *= (1 - np.exp(-age / 0.015)) * (1 - np.exp(-(1.3 - age) / 0.03))
            add_loop(music, bass * 0.08, start + k * beat * 2)
    for step in range(128):
        age = np.arange(int(0.09 * RATE)) / RATE
        hat = rng.normal(size=len(age))
        hat = np.concatenate(([0], np.diff(hat))) * np.exp(-age / 0.015) * 0.004
        hat *= np.minimum(age / 0.001, 1)
        add_loop(music, hat, step * beat / 2)
    for step in range(64):
        age = np.arange(int(0.3 * RATE)) / RATE
        if step % 4 in (0, 2):
            kick = np.sin(2 * np.pi * (48 * age + 2 * (1 - np.exp(-age * 24))))
            kick *= np.exp(-age / 0.09) * np.minimum(age / 0.004, 1) * 0.08
            add_loop(music, kick, step * beat)
        if step % 4 in (1, 3):
            snare = rng.normal(size=len(age)) * np.exp(-age / 0.04) * 0.012
            snare *= np.minimum(age / 0.003, 1)
            add_loop(music, snare, step * beat + 0.014)
    return {"fire": normalize(fire, 0.11), "wind": normalize(wind, 0.10),
            "lofi": normalize(music, 0.13)}


def write_wav(path, samples):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, RATE, len(samples), "NONE", "not compressed"))
        stream.writeframes(np.rint(samples * 32767).astype("<i2").tobytes())


def main():
    target = ROOT / "assets" / "audio"
    target.mkdir(parents=True, exist_ok=True)
    for name, samples in make_loops().items():
        write_wav(target / f"{name}.wav", samples)
        print(f"{name}: {len(samples) / RATE:.0f}s, original synthesized PCM16")


if __name__ == "__main__":
    main()

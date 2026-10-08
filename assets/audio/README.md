# Original audio for Hearth

These WAV loops are synthesized by `tools/generate_audio.py`: filtered noise
for the fire and wind, and an original electric-piano/bass/drum arrangement at
80 BPM. No recordings, sample packs, YouTube audio or third-party music are used.

Regenerate deterministically with `uv run tools/generate_audio.py`.
Playback is optional and starts only when the user enables sound.

The fireplace uses a soft combustion bed and irregular, rounded wood crackles.
Its high-frequency energy and transient peaks are limited to avoid harsh clicks.
Regenerate only this loop with `uv run tools/generate_audio.py --only fire`.
The 48-second lofi track is the native player's fallback when no local mix exists.

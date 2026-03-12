"""ElevenLabs audio generation tools — SFX, music, and dialogue.

Generates audio via ElevenLabs API using ELEVENLABS_API_KEY.
Three tools: generate_sound_effect, generate_music, generate_dialogue.
"""

import json
import logging
import os
import time
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)

AUDIO_DIR = Path.home() / "audio" / "hermes-gen"


def _check_elevenlabs() -> bool:
    """Return True if ElevenLabs API key is configured."""
    return bool(os.getenv("ELEVENLABS_API_KEY"))


def _ensure_dirs():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tool 1: Sound Effects
# ---------------------------------------------------------------------------

def _generate_sfx(args, **kw):
    """Generate a sound effect using ElevenLabs."""
    import requests

    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return json.dumps({"error": "ELEVENLABS_API_KEY not configured"})

    prompt = args.get("prompt", "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    duration = args.get("duration")

    try:
        _ensure_dirs()
        payload = {"text": prompt}
        if duration:
            payload["duration_seconds"] = duration

        resp = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

        ts = time.strftime("%Y%m%d_%H%M%S")
        path = AUDIO_DIR / f"sfx_{ts}.mp3"
        with open(path, "wb") as f:
            f.write(resp.content)
        return f"Sound effect saved to {path} ({len(resp.content)} bytes)"
    except Exception as e:
        return json.dumps({"error": f"SFX generation failed: {e}"})


registry.register(
    name="generate_sound_effect",
    toolset="audio_gen",
    schema={
        "name": "generate_sound_effect",
        "description": (
            "Generate a sound effect from a text description using ElevenLabs. "
            "Saves MP3 to ~/audio/hermes-gen/."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the sound effect (e.g. 'sword clashing on shield')",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds (optional, let AI decide by default)",
                },
            },
            "required": ["prompt"],
        },
    },
    handler=_generate_sfx,
    check_fn=_check_elevenlabs,
    requires_env=["ELEVENLABS_API_KEY"],
)


# ---------------------------------------------------------------------------
# Tool 2: Music Generation
# ---------------------------------------------------------------------------

def _generate_music(args, **kw):
    """Generate music using ElevenLabs."""
    import requests

    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return json.dumps({"error": "ELEVENLABS_API_KEY not configured"})

    prompt = args.get("prompt", "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    duration_ms = args.get("duration_seconds", 30) * 1000
    instrumental = args.get("instrumental", True)

    try:
        _ensure_dirs()
        resp = requests.post(
            "https://api.elevenlabs.io/v1/music",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={
                "prompt": prompt,
                "music_length_ms": int(duration_ms),
                "force_instrumental": instrumental,
            },
            timeout=240,
        )
        resp.raise_for_status()

        ts = time.strftime("%Y%m%d_%H%M%S")
        path = AUDIO_DIR / f"music_{ts}.mp3"
        with open(path, "wb") as f:
            f.write(resp.content)
        return f"Music saved to {path} ({len(resp.content)} bytes, {duration_ms/1000:.0f}s)"
    except Exception as e:
        return json.dumps({"error": f"Music generation failed: {e}"})


registry.register(
    name="generate_music",
    toolset="audio_gen",
    schema={
        "name": "generate_music",
        "description": (
            "Generate music from a text prompt using ElevenLabs. "
            "Saves MP3 to ~/audio/hermes-gen/. Supports 3s-5min duration."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Music description (genre, mood, instruments, tempo)",
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "Duration in seconds (default: 30, max: 300)",
                },
                "instrumental": {
                    "type": "boolean",
                    "description": "Instrumental only, no vocals (default: true)",
                },
            },
            "required": ["prompt"],
        },
    },
    handler=_generate_music,
    check_fn=_check_elevenlabs,
    requires_env=["ELEVENLABS_API_KEY"],
)


# ---------------------------------------------------------------------------
# Tool 3: Multi-Speaker Dialogue
# ---------------------------------------------------------------------------

def _generate_dialogue(args, **kw):
    """Generate multi-speaker dialogue using ElevenLabs."""
    import requests

    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return json.dumps({"error": "ELEVENLABS_API_KEY not configured"})

    lines = args.get("lines", [])
    if not lines:
        return json.dumps({"error": "lines array is required"})

    try:
        # Resolve voice names to IDs
        voices_resp = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
            timeout=10,
        )
        voice_map = {}
        if voices_resp.status_code == 200:
            for v in voices_resp.json().get("voices", []):
                voice_map[v["name"].lower()] = v["voice_id"]
                short_name = v["name"].split(" - ")[0].strip().lower()
                voice_map[short_name] = v["voice_id"]

        inputs = []
        for line in lines:
            voice_name = line.get("voice", "Rachel")
            voice_id = voice_map.get(voice_name.lower(), voice_name)
            inputs.append({"text": line["text"], "voice_id": voice_id})

        resp = requests.post(
            "https://api.elevenlabs.io/v1/text-to-dialogue",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={
                "inputs": inputs,
                "model_id": "eleven_v3",
            },
            timeout=60,
        )
        resp.raise_for_status()

        _ensure_dirs()
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = AUDIO_DIR / f"dialogue_{ts}.mp3"
        with open(path, "wb") as f:
            f.write(resp.content)
        return f"Dialogue saved to {path} ({len(resp.content)} bytes, {len(lines)} lines)"

    except Exception as e:
        return json.dumps({"error": f"Dialogue generation failed: {e}"})


registry.register(
    name="generate_dialogue",
    toolset="audio_gen",
    schema={
        "name": "generate_dialogue",
        "description": (
            "Generate multi-speaker dialogue audio using ElevenLabs v3. "
            "Each line has text and voice name. Supports audio tags: "
            "[laughing], [whispering], [sad], [excited]. "
            "Saves MP3 to ~/audio/hermes-gen/."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "description": "Array of dialogue lines",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The spoken text (supports [emotion] tags)",
                            },
                            "voice": {
                                "type": "string",
                                "description": "Voice name (e.g. Rachel, Adam, Bella)",
                            },
                        },
                        "required": ["text", "voice"],
                    },
                },
            },
            "required": ["lines"],
        },
    },
    handler=_generate_dialogue,
    check_fn=_check_elevenlabs,
    requires_env=["ELEVENLABS_API_KEY"],
)

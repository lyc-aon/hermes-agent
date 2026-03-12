"""OpenAI image generation tool — gpt-image-1.5 / gpt-image-1.

Generates images via OpenAI's images API using OPENAI_IMAGE_API_KEY
(or falls back to OPENAI_API_KEY). Supports gpt-image-1.5 (default,
better instruction following, 20% cheaper) and gpt-image-1.

Registered as a separate tool alongside the FAL-based image_generate
so both can coexist. If only one provider key is configured, only
that tool appears.
"""

import json
import logging
import os
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

# Model defaults
DEFAULT_MODEL = "gpt-image-1.5"
FALLBACK_MODEL = "gpt-image-1"

# Size mapping — OpenAI only supports these three fixed sizes
SIZE_MAP = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}

# Quality options (gpt-image-1 and 1.5)
VALID_QUALITIES = ["low", "medium", "high"]


def _get_api_key() -> Optional[str]:
    """Return the OpenAI API key for image generation.

    Checks OPENAI_IMAGE_API_KEY first (dedicated key for image gen),
    then falls back to OPENAI_API_KEY (general-purpose key).
    """
    return os.getenv("OPENAI_IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")


def _check_openai_image() -> bool:
    """Return True if OpenAI image generation is available."""
    if not _get_api_key():
        return False
    try:
        import openai  # noqa: F401 — already a core Hermes dependency
        return True
    except ImportError:
        return False


def _openai_image_generate(args, **kw):
    prompt = args.get("prompt", "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    api_key = _get_api_key()
    if not api_key:
        return json.dumps({"error": "OPENAI_IMAGE_API_KEY or OPENAI_API_KEY not set"})

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    # Resolve parameters
    aspect = args.get("aspect_ratio", "landscape").lower().strip()
    size = SIZE_MAP.get(aspect, SIZE_MAP["landscape"])
    quality = args.get("quality", "high").lower().strip()
    if quality not in VALID_QUALITIES:
        quality = "high"
    model = args.get("model", DEFAULT_MODEL)
    if model not in (DEFAULT_MODEL, FALLBACK_MODEL):
        model = DEFAULT_MODEL

    # Background transparency (PNG only)
    background = args.get("background", "auto")
    if background not in ("transparent", "opaque", "auto"):
        background = "auto"

    # Output format
    output_format = args.get("output_format", "png")
    if output_format not in ("png", "jpeg", "webp"):
        output_format = "png"

    try:
        logger.info("Generating image with %s: %s", model, prompt[:80])

        generate_kwargs = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "background": background,
            "output_format": output_format,
            "n": 1,
        }

        response = client.images.generate(**generate_kwargs)

        if not response.data:
            return json.dumps({"success": False, "image": None, "error": "No image returned"})

        image_data = response.data[0]

        # Response may have url or b64_json depending on output
        image_url = getattr(image_data, "url", None)
        b64 = getattr(image_data, "b64_json", None)

        if image_url:
            return json.dumps({
                "success": True,
                "image": image_url,
                "model": model,
                "size": size,
                "quality": quality,
            }, indent=2)
        elif b64:
            # Save base64 to a temp file and return path
            import base64
            import tempfile
            ext = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}.get(output_format, ".png")
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, prefix="hermes_img_") as f:
                f.write(base64.b64decode(b64))
                return json.dumps({
                    "success": True,
                    "image": f.name,
                    "format": "local_file",
                    "model": model,
                    "size": size,
                    "quality": quality,
                }, indent=2)
        else:
            return json.dumps({"success": False, "image": None, "error": "Unexpected response format"})

    except Exception as e:
        logger.error("OpenAI image generation failed: %s", e, exc_info=True)
        return json.dumps({
            "success": False,
            "image": None,
            "error": str(e),
        })


# ---------------------------------------------------------------------------
# Schema & Registration
# ---------------------------------------------------------------------------

OPENAI_IMAGE_GENERATE_SCHEMA = {
    "name": "openai_image_generate",
    "description": (
        "Generate images from text prompts using OpenAI's GPT Image models "
        "(gpt-image-1.5 or gpt-image-1). Returns an image URL. "
        "Display it using markdown: ![description](URL). "
        "Supports landscape (1536x1024), square (1024x1024), and portrait (1024x1536). "
        "Quality: low (fast/cheap), medium, high (best detail). "
        "Use gpt-image-1.5 (default) for best instruction following and text rendering."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text prompt describing the desired image. Be detailed and descriptive.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["landscape", "square", "portrait"],
                "description": "Image aspect ratio. landscape=1536x1024, square=1024x1024, portrait=1024x1536.",
                "default": "landscape",
            },
            "quality": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Image quality. 'high' for best detail, 'low' for fast/cheap generation.",
                "default": "high",
            },
            "model": {
                "type": "string",
                "enum": ["gpt-image-1.5", "gpt-image-1"],
                "description": "Model to use. gpt-image-1.5 (default) has better instruction following and text rendering.",
                "default": "gpt-image-1.5",
            },
            "background": {
                "type": "string",
                "enum": ["transparent", "opaque", "auto"],
                "description": "Background style. 'transparent' for PNG with no background, 'opaque' for solid, 'auto' to let model decide.",
                "default": "auto",
            },
            "output_format": {
                "type": "string",
                "enum": ["png", "jpeg", "webp"],
                "description": "Output image format. PNG supports transparency.",
                "default": "png",
            },
        },
        "required": ["prompt"],
    },
}

registry.register(
    name="openai_image_generate",
    toolset="image_gen",
    schema=OPENAI_IMAGE_GENERATE_SCHEMA,
    handler=lambda args, **kw: _openai_image_generate(args, **kw),
    check_fn=_check_openai_image,
    requires_env=["OPENAI_IMAGE_API_KEY"],
)

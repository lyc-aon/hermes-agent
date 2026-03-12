"""Image processing tools — Pillow-based image manipulation for game assets and general use.

Provides 11 tools for analyzing, transforming, and optimizing images.
All core tools require only Pillow. Optional tools (remove_background,
make_sprite_sheet) degrade gracefully when their deps are missing.
"""

import importlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hex(color: str) -> tuple:
    """Parse '#rrggbb' or 'rrggbb' to (r, g, b)."""
    color = color.lstrip("#")
    if len(color) != 6:
        raise ValueError(f"Invalid hex color: #{color}")
    return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))


def _resolve_output(input_path: str, suffix: str, output: str = None) -> str:
    """Generate output path: use explicit output or append suffix before extension."""
    if output:
        return output
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}{suffix}{p.suffix}"))


def _ensure_pillow():
    """Import and return PIL.Image, raising clear error if missing."""
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise RuntimeError("Pillow is not installed. Install with: pip install Pillow")


def _check_pillow() -> bool:
    """Return True if Pillow is available."""
    return bool(importlib.util.find_spec("PIL"))


def _check_rembg() -> bool:
    """Return True if rembg is available."""
    return _check_pillow() and bool(importlib.util.find_spec("rembg"))


def _check_texture_packer() -> bool:
    """Return True if PyTexturePacker is available."""
    return _check_pillow() and bool(importlib.util.find_spec("PyTexturePacker"))


# ---------------------------------------------------------------------------
# 1. analyze_image_file
# ---------------------------------------------------------------------------

def _analyze_image_file(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    try:
        img = Image.open(path)
    except Exception as e:
        return json.dumps({"error": f"Cannot open image: {e}"})

    file_size = os.path.getsize(path)
    info = {
        "path": path,
        "format": img.format or "unknown",
        "mode": img.mode,
        "width": img.width,
        "height": img.height,
        "file_size_bytes": file_size,
        "file_size_human": f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024*1024):.2f} MB",
    }

    info["has_transparency"] = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info

    if img.mode == "RGBA":
        bbox = img.getchannel("A").getbbox()
        if bbox:
            info["content_bounds"] = {"x": bbox[0], "y": bbox[1], "width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1]}
        else:
            info["content_bounds"] = None
    else:
        info["content_bounds"] = {"x": 0, "y": 0, "width": img.width, "height": img.height}

    dpi = img.info.get("dpi")
    if dpi:
        info["dpi"] = {"x": round(dpi[0]), "y": round(dpi[1])}

    try:
        info["frame_count"] = getattr(img, "n_frames", 1)
    except Exception:
        info["frame_count"] = 1

    try:
        if img.width * img.height <= 512 * 512:
            colors = img.getcolors(maxcolors=65536)
            info["unique_colors"] = len(colors) if colors else "more than 65536"
        else:
            info["unique_colors"] = "image too large to count (>512x512)"
    except Exception:
        info["unique_colors"] = "unknown"

    img.close()
    return json.dumps(info, indent=2)


ANALYZE_IMAGE_FILE_SCHEMA = {
    "name": "analyze_image_file",
    "description": "Analyze image metadata: dimensions, format, mode, file size, transparency, content bounds, DPI, frame count, and color count.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="analyze_image_file",
    toolset="image_processing",
    schema=ANALYZE_IMAGE_FILE_SCHEMA,
    handler=lambda args, **kw: _analyze_image_file(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 2. crop_image
# ---------------------------------------------------------------------------

def _crop_image(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    img = Image.open(path)
    output = args.get("output", _resolve_output(path, "_cropped"))

    mode = args.get("mode", "auto")
    padding = args.get("padding", 0)

    if mode == "manual":
        x = args.get("x", 0)
        y = args.get("y", 0)
        width = args.get("width")
        height = args.get("height")
        if width is None or height is None:
            return json.dumps({"error": "Manual crop requires width and height"})
        box = (x, y, x + width, y + height)
    else:
        if img.mode == "RGBA":
            bbox = img.getchannel("A").getbbox()
        else:
            from PIL import ImageChops
            bg = Image.new(img.mode, img.size, (255,) * len(img.getbands()))
            diff = ImageChops.difference(img, bg)
            bbox = diff.getbbox()

        if bbox is None:
            img.close()
            return json.dumps({"error": "No content found to crop (image is empty or uniform)"})
        box = bbox

    if padding > 0:
        box = (
            max(0, box[0] - padding),
            max(0, box[1] - padding),
            min(img.width, box[2] + padding),
            min(img.height, box[3] + padding),
        )

    cropped = img.crop(box)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output)
    result = {
        "output": output,
        "original_size": f"{img.width}x{img.height}",
        "cropped_size": f"{cropped.width}x{cropped.height}",
        "crop_box": {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]},
    }
    img.close()
    cropped.close()
    return json.dumps(result, indent=2)


CROP_IMAGE_SCHEMA = {
    "name": "crop_image",
    "description": "Crop an image. Auto-crop removes transparent/white borders, or specify manual coordinates.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "output": {"type": "string", "description": "Output path (default: adds _cropped suffix)"},
            "mode": {"type": "string", "enum": ["auto", "manual"], "description": "Crop mode (default: auto)"},
            "x": {"type": "integer", "description": "Left coordinate (manual mode)"},
            "y": {"type": "integer", "description": "Top coordinate (manual mode)"},
            "width": {"type": "integer", "description": "Crop width (manual mode)"},
            "height": {"type": "integer", "description": "Crop height (manual mode)"},
            "padding": {"type": "integer", "description": "Padding pixels around content (default: 0)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="crop_image",
    toolset="image_processing",
    schema=CROP_IMAGE_SCHEMA,
    handler=lambda args, **kw: _crop_image(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 3. resize_image
# ---------------------------------------------------------------------------

def _resize_image(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    from PIL import ImageOps

    img = Image.open(path)
    output = args.get("output", _resolve_output(path, "_resized"))

    filter_name = args.get("filter", "lanczos").upper()
    resample_map = {
        "NEAREST": Image.Resampling.NEAREST,
        "BILINEAR": Image.Resampling.BILINEAR,
        "BICUBIC": Image.Resampling.BICUBIC,
        "LANCZOS": Image.Resampling.LANCZOS,
    }
    resample = resample_map.get(filter_name, Image.Resampling.LANCZOS)

    scale = args.get("scale")
    width = args.get("width")
    height = args.get("height")
    fit_mode = args.get("fit_mode", "contain")

    if scale:
        new_w = round(img.width * scale)
        new_h = round(img.height * scale)
        result_img = img.resize((new_w, new_h), resample)
    elif width and height:
        if fit_mode == "fill":
            result_img = img.resize((width, height), resample)
        elif fit_mode == "cover":
            result_img = ImageOps.fit(img, (width, height), method=resample)
        else:
            result_img = img.copy()
            result_img.thumbnail((width, height), resample)
    elif width:
        ratio = width / img.width
        new_h = round(img.height * ratio)
        result_img = img.resize((width, new_h), resample)
    elif height:
        ratio = height / img.height
        new_w = round(img.width * ratio)
        result_img = img.resize((new_w, height), resample)
    else:
        img.close()
        return json.dumps({"error": "Specify scale, width, height, or width+height"})

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result_img.save(output)
    result = {
        "output": output,
        "original_size": f"{img.width}x{img.height}",
        "new_size": f"{result_img.width}x{result_img.height}",
        "filter": filter_name.lower(),
    }
    img.close()
    result_img.close()
    return json.dumps(result, indent=2)


RESIZE_IMAGE_SCHEMA = {
    "name": "resize_image",
    "description": "Resize an image by scale factor, dimensions, or fit mode. Supports nearest (pixel art), lanczos (quality), bicubic, bilinear.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "output": {"type": "string", "description": "Output path (default: adds _resized suffix)"},
            "scale": {"type": "number", "description": "Scale factor (e.g. 2.0 for double size)"},
            "width": {"type": "integer", "description": "Target width in pixels"},
            "height": {"type": "integer", "description": "Target height in pixels"},
            "fit_mode": {"type": "string", "enum": ["contain", "cover", "fill"], "description": "How to fit when both width and height given (default: contain)"},
            "filter": {"type": "string", "enum": ["nearest", "bilinear", "bicubic", "lanczos"], "description": "Resampling filter (default: lanczos, use nearest for pixel art)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="resize_image",
    toolset="image_processing",
    schema=RESIZE_IMAGE_SCHEMA,
    handler=lambda args, **kw: _resize_image(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 4. convert_image
# ---------------------------------------------------------------------------

def _convert_image(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    target_format = args.get("format", "png").lower()
    quality = args.get("quality", 90)

    if target_format == "svg":
        output = args.get("output")
        if not output:
            output = str(Path(path).with_suffix(".svg"))
        Path(output).parent.mkdir(parents=True, exist_ok=True)

        # Prefer potrace (subprocess), fall back to vtracer (Python)
        if shutil.which("potrace"):
            Image = _ensure_pillow()
            img_for_svg = Image.open(path).convert("L")
            with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp:
                bmp_path = tmp.name
                img_for_svg.save(bmp_path, "BMP")
                img_for_svg.close()
            try:
                subprocess.run(
                    ["potrace", bmp_path, "-s", "-o", output, "--flat"],
                    check=True, capture_output=True, timeout=30,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                os.unlink(bmp_path)
                return json.dumps({"error": f"potrace failed: {e}"})
            os.unlink(bmp_path)
            return json.dumps({"output": output, "format": "svg", "source": path, "tool": "potrace"})

        try:
            import vtracer
        except ImportError:
            return json.dumps({"error": "SVG conversion requires potrace (apt install potrace) or vtracer (pip install vtracer)"})
        vtracer.convert_image_to_svg_py(
            path, output,
            colormode="color", hierarchical="stacked", mode="spline",
            filter_speckle=4, color_precision=6, layer_difference=16,
            corner_threshold=60, length_threshold=4.0, max_iterations=10,
            splice_threshold=45, path_precision=3,
        )
        return json.dumps({"output": output, "format": "svg", "source": path, "tool": "vtracer"})

    Image = _ensure_pillow()
    img = Image.open(path)

    ext_map = {"png": ".png", "webp": ".webp", "jpeg": ".jpg", "jpg": ".jpg", "avif": ".avif"}
    ext = ext_map.get(target_format)
    if not ext:
        img.close()
        return json.dumps({"error": f"Unsupported format: {target_format}. Use: png, webp, jpeg, avif, svg"})

    # AVIF codec check
    if target_format == "avif":
        try:
            from PIL import features
            if not features.check_codec("avif"):
                img.close()
                return json.dumps({"error": "AVIF codec not available in this Pillow build. Use webp or png instead."})
        except (ImportError, AttributeError):
            img.close()
            return json.dumps({"error": "AVIF support requires Pillow 9.1+ with libavif. Use webp or png instead."})

    output = args.get("output")
    if not output:
        output = str(Path(path).with_suffix(ext))

    save_img = img
    if target_format in ("jpeg", "jpg") and img.mode in ("RGBA", "LA", "PA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        save_img = background

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {}
    if target_format in ("jpeg", "jpg", "webp", "avif"):
        save_kwargs["quality"] = quality
    if target_format == "png":
        save_kwargs["optimize"] = True

    save_img.save(output, **save_kwargs)
    result = {
        "output": output,
        "format": target_format,
        "source": path,
        "original_size_bytes": os.path.getsize(path),
        "output_size_bytes": os.path.getsize(output),
    }
    img.close()
    if save_img is not img:
        save_img.close()
    return json.dumps(result, indent=2)


CONVERT_IMAGE_SCHEMA = {
    "name": "convert_image",
    "description": "Convert image between formats: PNG, WebP, JPEG, AVIF. SVG vectorization via potrace or vtracer. AVIF requires Pillow 9.1+ with libavif.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to source image"},
            "format": {"type": "string", "enum": ["png", "webp", "jpeg", "avif", "svg"], "description": "Target format (default: png)"},
            "output": {"type": "string", "description": "Output path (default: same name, new extension)"},
            "quality": {"type": "integer", "description": "Quality for lossy formats 1-100 (default: 90)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="convert_image",
    toolset="image_processing",
    schema=CONVERT_IMAGE_SCHEMA,
    handler=lambda args, **kw: _convert_image(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 5. color_adjust
# ---------------------------------------------------------------------------

def _color_adjust(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    from PIL import ImageEnhance

    img = Image.open(path)
    output = args.get("output", _resolve_output(path, "_adjusted"))

    adjustments = []

    brightness = args.get("brightness")
    if brightness is not None:
        img = ImageEnhance.Brightness(img).enhance(brightness)
        adjustments.append(f"brightness={brightness}")

    contrast = args.get("contrast")
    if contrast is not None:
        img = ImageEnhance.Contrast(img).enhance(contrast)
        adjustments.append(f"contrast={contrast}")

    saturation = args.get("saturation")
    if saturation is not None:
        img = ImageEnhance.Color(img).enhance(saturation)
        adjustments.append(f"saturation={saturation}")

    sharpness = args.get("sharpness")
    if sharpness is not None:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
        adjustments.append(f"sharpness={sharpness}")

    # Tint — HSV hue rotation (preserves saturation and lightness)
    tint = args.get("tint")
    if tint is not None:
        try:
            import colorsys
            tint_rgb = _parse_hex(tint)
            target_h, _, _ = colorsys.rgb_to_hsv(tint_rgb[0] / 255.0, tint_rgb[1] / 255.0, tint_rgb[2] / 255.0)
            alpha = None
            if img.mode == "RGBA":
                alpha = img.getchannel("A")
            rgb_img = img.convert("RGB")
            # Per-pixel hue rotation
            pixels = list(rgb_img.getdata())
            new_pixels = []
            for r, g, b in pixels:
                _, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                nr, ng, nb = colorsys.hsv_to_rgb(target_h, s, v)
                new_pixels.append((int(nr * 255), int(ng * 255), int(nb * 255)))
            rgb_img.putdata(new_pixels)
            if alpha is not None:
                rgb_img = rgb_img.convert("RGBA")
                rgb_img.putalpha(alpha)
            img = rgb_img
            adjustments.append(f"tint={tint}")
        except ValueError as e:
            return json.dumps({"error": str(e)})

    if not adjustments:
        img.close()
        return json.dumps({"error": "No adjustments specified. Use: brightness, contrast, saturation, sharpness, tint"})

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)
    result = {
        "output": output,
        "adjustments": adjustments,
    }
    img.close()
    return json.dumps(result, indent=2)


COLOR_ADJUST_SCHEMA = {
    "name": "color_adjust",
    "description": "Adjust image brightness, contrast, saturation, sharpness, or apply color tint via HSV hue rotation. Values: 1.0=no change, >1=increase, <1=decrease.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "output": {"type": "string", "description": "Output path (default: adds _adjusted suffix)"},
            "brightness": {"type": "number", "description": "Brightness factor (1.0=normal)"},
            "contrast": {"type": "number", "description": "Contrast factor (1.0=normal)"},
            "saturation": {"type": "number", "description": "Saturation factor (1.0=normal)"},
            "sharpness": {"type": "number", "description": "Sharpness factor (1.0=normal)"},
            "tint": {"type": "string", "description": "Hex color to tint toward (e.g. '#ff0000') — rotates hue while preserving saturation/lightness"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="color_adjust",
    toolset="image_processing",
    schema=COLOR_ADJUST_SCHEMA,
    handler=lambda args, **kw: _color_adjust(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 6. optimize_image
# ---------------------------------------------------------------------------

def _optimize_image(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    output = args.get("output", path)
    quality = args.get("quality", 80)
    ext = Path(path).suffix.lower()

    original_size = os.path.getsize(path)

    if os.path.abspath(output) != os.path.abspath(path):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, output)

    optimized = False
    tool_used = "none"

    if ext == ".png":
        if shutil.which("pngquant"):
            try:
                subprocess.run(
                    ["pngquant", "--force", "--quality", f"{max(quality-20,0)}-{quality}",
                     "--output", output, "--", output],
                    check=True, capture_output=True, timeout=30,
                )
                optimized = True
                tool_used = "pngquant"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.debug("pngquant failed: %s", e)
        if not optimized and shutil.which("oxipng"):
            try:
                subprocess.run(
                    ["oxipng", "-o", "2", "--strip", "safe", output],
                    check=True, capture_output=True, timeout=30,
                )
                optimized = True
                tool_used = "oxipng"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.debug("oxipng failed: %s", e)

    elif ext == ".webp":
        if shutil.which("cwebp"):
            try:
                tmp_out = output + ".tmp.webp"
                subprocess.run(
                    ["cwebp", "-q", str(quality), output, "-o", tmp_out],
                    check=True, capture_output=True, timeout=30,
                )
                shutil.move(tmp_out, output)
                optimized = True
                tool_used = "cwebp"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.debug("cwebp failed: %s", e)
                tmp_out = output + ".tmp.webp"
                if os.path.exists(tmp_out):
                    os.remove(tmp_out)

    elif ext in (".jpg", ".jpeg"):
        Image = _ensure_pillow()
        img = Image.open(output)
        img.save(output, "JPEG", quality=quality, optimize=True)
        img.close()
        optimized = True
        tool_used = "pillow"

    if not optimized:
        Image = _ensure_pillow()
        img = Image.open(output)
        save_kwargs = {"optimize": True}
        if ext == ".webp":
            save_kwargs["quality"] = quality
        img.save(output, **save_kwargs)
        img.close()
        optimized = True
        tool_used = "pillow"

    new_size = os.path.getsize(output)
    savings = original_size - new_size
    pct = (savings / original_size * 100) if original_size > 0 else 0

    return json.dumps({
        "output": output,
        "original_size_bytes": original_size,
        "optimized_size_bytes": new_size,
        "savings_bytes": savings,
        "savings_percent": round(pct, 1),
        "tool_used": tool_used,
    }, indent=2)


OPTIMIZE_IMAGE_SCHEMA = {
    "name": "optimize_image",
    "description": "Compress/optimize an image. PNG via pngquant/oxipng, WebP via cwebp, JPEG via Pillow. Falls back to Pillow if system tools missing.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "output": {"type": "string", "description": "Output path (default: optimize in-place)"},
            "quality": {"type": "integer", "description": "Quality level 1-100 (default: 80)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="optimize_image",
    toolset="image_processing",
    schema=OPTIMIZE_IMAGE_SCHEMA,
    handler=lambda args, **kw: _optimize_image(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 7. image_effects
# ---------------------------------------------------------------------------

def _image_effects(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    from PIL import ImageFilter, ImageChops

    effect = args.get("effect", "silhouette")
    output = args.get("output", _resolve_output(path, f"_{effect}"))
    color = args.get("color", "#000000")

    img = Image.open(path).convert("RGBA")
    r, g, b, a = img.split()

    try:
        color_rgb = _parse_hex(color)
    except ValueError as e:
        img.close()
        return json.dumps({"error": str(e)})

    if effect == "silhouette":
        mask = a.point(lambda x: 255 if x > 0 else 0)
        fill = Image.new("RGBA", img.size, color_rgb + (255,))
        result = Image.new("RGBA", img.size, (0, 0, 0, 0))
        result.paste(fill, mask=mask)

    elif effect == "outline":
        thickness = args.get("thickness", 2)
        dilated = a.filter(ImageFilter.MaxFilter(2 * thickness + 1))
        outline_mask = ImageChops.subtract(dilated, a)
        outline_layer = Image.new("RGBA", img.size, color_rgb + (255,))
        outline_result = Image.new("RGBA", img.size, (0, 0, 0, 0))
        outline_result.paste(outline_layer, mask=outline_mask)
        result = Image.alpha_composite(outline_result, img)

    elif effect == "glow":
        radius = args.get("radius", 10)
        intensity = args.get("intensity", 0.8)
        glow_alpha = a.filter(ImageFilter.GaussianBlur(radius=radius))
        glow_alpha = glow_alpha.point(lambda x: min(255, int(x * intensity)))
        glow_layer = Image.new("RGBA", img.size, color_rgb + (255,))
        glow_layer.putalpha(glow_alpha)
        result = Image.alpha_composite(glow_layer, img)

    elif effect == "shadow":
        offset_x = args.get("offset_x", 4)
        offset_y = args.get("offset_y", 4)
        blur = args.get("blur", 5)
        opacity = args.get("opacity", 150)
        shadow_alpha = a.filter(ImageFilter.GaussianBlur(radius=blur))
        shadow_alpha = shadow_alpha.point(lambda x: min(opacity, x))
        canvas_w = img.width + abs(offset_x) + blur * 2
        canvas_h = img.height + abs(offset_y) + blur * 2
        pad_x = max(0, -offset_x) + blur
        pad_y = max(0, -offset_y) + blur
        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_color = Image.new("RGBA", img.size, color_rgb + (255,))
        shadow_color.putalpha(shadow_alpha)
        shadow_layer.paste(shadow_color, (pad_x + offset_x, pad_y + offset_y))
        shadow_layer.paste(img, (pad_x, pad_y), img)
        result = shadow_layer

    elif effect == "pixelate":
        factor = args.get("factor", 8)
        small_w = max(1, img.width // factor)
        small_h = max(1, img.height // factor)
        small = img.resize((small_w, small_h), Image.Resampling.NEAREST)
        result = small.resize(img.size, Image.Resampling.NEAREST)

    else:
        img.close()
        return json.dumps({"error": f"Unknown effect: {effect}. Use: silhouette, outline, glow, shadow, pixelate"})

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    result_size = f"{result.width}x{result.height}"
    img.close()
    result.close()
    return json.dumps({
        "output": output,
        "effect": effect,
        "size": result_size,
    }, indent=2)


IMAGE_EFFECTS_SCHEMA = {
    "name": "image_effects",
    "description": "Apply visual effects: silhouette (solid color fill), outline (border around sprite), glow (soft colored aura), shadow (drop shadow), pixelate. All Pillow-native.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to RGBA image"},
            "effect": {"type": "string", "enum": ["silhouette", "outline", "glow", "shadow", "pixelate"], "description": "Effect to apply"},
            "output": {"type": "string", "description": "Output path (default: adds _<effect> suffix)"},
            "color": {"type": "string", "description": "Hex color for effect (default: #000000)"},
            "thickness": {"type": "integer", "description": "Outline thickness in pixels (outline effect, default: 2)"},
            "radius": {"type": "integer", "description": "Glow radius in pixels (glow effect, default: 10)"},
            "intensity": {"type": "number", "description": "Glow intensity 0-1 (glow effect, default: 0.8)"},
            "offset_x": {"type": "integer", "description": "Shadow X offset (shadow effect, default: 4)"},
            "offset_y": {"type": "integer", "description": "Shadow Y offset (shadow effect, default: 4)"},
            "blur": {"type": "integer", "description": "Shadow blur radius (shadow effect, default: 5)"},
            "opacity": {"type": "integer", "description": "Shadow opacity 0-255 (shadow effect, default: 150)"},
            "factor": {"type": "integer", "description": "Pixelation factor (pixelate effect, default: 8)"},
        },
        "required": ["path", "effect"],
    },
}

registry.register(
    name="image_effects",
    toolset="image_processing",
    schema=IMAGE_EFFECTS_SCHEMA,
    handler=lambda args, **kw: _image_effects(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 8. process_game_asset
# ---------------------------------------------------------------------------

def _process_game_asset(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()

    width = args.get("width", 64)
    height = args.get("height", 64)
    pixel_art = args.get("pixel_art", True)
    output = args.get("output", _resolve_output(path, "_asset"))
    remove_bg = args.get("remove_background", True)

    steps = []

    with tempfile.TemporaryDirectory() as tmpdir:
        current = path

        # Step 1: Remove background (optional)
        if remove_bg:
            try:
                from rembg import remove, new_session
                session = new_session(args.get("bg_model", "isnet-anime"))
                img = Image.open(current)
                result = remove(img, session=session)
                step1_path = os.path.join(tmpdir, "01_nobg.png")
                result.save(step1_path)
                current = step1_path
                steps.append("remove_background")
                img.close()
                result.close()
            except (ImportError, SystemExit):
                import sys
                for key in [k for k in sys.modules if k == "rembg" or k.startswith("rembg.")]:
                    del sys.modules[key]
                steps.append("remove_background_skipped (rembg not installed)")

        # Step 2: Auto-crop
        img = Image.open(current)
        if img.mode == "RGBA":
            bbox = img.getchannel("A").getbbox()
        else:
            from PIL import ImageChops
            bg = Image.new(img.mode, img.size, (255,) * len(img.getbands()))
            diff = ImageChops.difference(img, bg)
            bbox = diff.getbbox()

        if bbox:
            padding = args.get("padding", 2)
            padded_box = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(img.width, bbox[2] + padding),
                min(img.height, bbox[3] + padding),
            )
            img = img.crop(padded_box)
            steps.append(f"crop ({img.width}x{img.height})")

        # Step 3: Resize
        resample = Image.Resampling.NEAREST if pixel_art else Image.Resampling.LANCZOS
        img.thumbnail((width, height), resample)
        steps.append(f"resize ({img.width}x{img.height})")

        step3_path = os.path.join(tmpdir, "03_resized.png")
        img.save(step3_path)
        img.close()

        # Step 4: Optimize
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(step3_path, output)

        ext = Path(output).suffix.lower()
        if ext == ".png" and shutil.which("pngquant"):
            try:
                pngquant_cmd = ["pngquant", "--force", "--quality", "75-85"]
                if pixel_art:
                    pngquant_cmd.append("--nofs")
                pngquant_cmd.extend(["--output", output, "--", output])
                subprocess.run(
                    pngquant_cmd,
                    check=True, capture_output=True, timeout=30,
                )
                steps.append("optimize (pngquant)")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                steps.append("optimize_skipped (pngquant failed)")
        else:
            opt_img = Image.open(output)
            opt_img.save(output, optimize=True)
            opt_img.close()
            steps.append("optimize (pillow)")

    final_img = Image.open(output)
    result = {
        "output": output,
        "final_size": f"{final_img.width}x{final_img.height}",
        "file_size_bytes": os.path.getsize(output),
        "pipeline_steps": steps,
        "pixel_art_mode": pixel_art,
    }
    final_img.close()
    return json.dumps(result, indent=2)


PROCESS_GAME_ASSET_SCHEMA = {
    "name": "process_game_asset",
    "description": "Full game asset pipeline: remove background (optional) -> auto-crop -> resize -> optimize. Perfect for turning AI-generated images into game sprites.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to source image"},
            "output": {"type": "string", "description": "Output path (default: adds _asset suffix)"},
            "width": {"type": "integer", "description": "Target width (default: 64)"},
            "height": {"type": "integer", "description": "Target height (default: 64)"},
            "pixel_art": {"type": "boolean", "description": "Use nearest-neighbor resampling for pixel art (default: true)"},
            "remove_background": {"type": "boolean", "description": "Try to remove background (default: true, skips if rembg missing)"},
            "bg_model": {"type": "string", "description": "rembg model: isnet-anime (default), u2net, silueta"},
            "padding": {"type": "integer", "description": "Padding pixels around content after crop (default: 2)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="process_game_asset",
    toolset="image_processing",
    schema=PROCESS_GAME_ASSET_SCHEMA,
    handler=lambda args, **kw: _process_game_asset(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 9. remove_background
# ---------------------------------------------------------------------------

def _remove_background(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    try:
        from rembg import remove, new_session
    except (ImportError, SystemExit):
        import sys
        for key in [k for k in sys.modules if k == "rembg" or k.startswith("rembg.")]:
            del sys.modules[key]
        return json.dumps({
            "error": "Missing dependency: rembg. Install with: pip install 'rembg[cpu]' (~500MB with onnxruntime)"
        })

    Image = _ensure_pillow()
    output = args.get("output", _resolve_output(path, "_nobg"))
    model = args.get("model", "isnet-anime")

    session = new_session(model)
    img = Image.open(path)
    result = remove(img, session=session)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result.save(output)

    result_info = {
        "output": output,
        "model": model,
        "original_mode": img.mode,
        "result_mode": result.mode,
    }
    img.close()
    result.close()
    return json.dumps(result_info, indent=2)


REMOVE_BACKGROUND_SCHEMA = {
    "name": "remove_background",
    "description": "Remove image background using AI (rembg). Best for sprites and product photos. Requires: pip install 'rembg[cpu]'",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "output": {"type": "string", "description": "Output path (default: adds _nobg suffix)"},
            "model": {"type": "string", "enum": ["isnet-anime", "u2net", "silueta"], "description": "Model: isnet-anime (best for sprites, default), u2net (general), silueta (fast)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="remove_background",
    toolset="image_processing",
    schema=REMOVE_BACKGROUND_SCHEMA,
    handler=lambda args, **kw: _remove_background(args, **kw),
    check_fn=_check_pillow,
    description="Remove image background using AI (rembg)",
)


# ---------------------------------------------------------------------------
# 10. extract_palette
# ---------------------------------------------------------------------------

def _extract_palette(args, **kw):
    path = args.get("path", "")
    if not os.path.isfile(path):
        return json.dumps({"error": f"File not found: {path}"})

    Image = _ensure_pillow()
    count = args.get("count", 8)

    img = Image.open(path).convert("RGBA")
    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
    rgb_img.paste(img, mask=img.split()[3])
    quantized = rgb_img.quantize(colors=count, method=Image.Quantize.MEDIANCUT)
    palette_data = quantized.getpalette()
    color_counts = sorted(quantized.getcolors(), key=lambda x: -x[0])

    total_pixels = img.width * img.height
    palette = []
    for pixel_count, idx in color_counts[:count]:
        r = palette_data[idx * 3]
        g = palette_data[idx * 3 + 1]
        b = palette_data[idx * 3 + 2]
        palette.append({
            "hex": f"#{r:02x}{g:02x}{b:02x}",
            "rgb": [r, g, b],
            "proportion": round(pixel_count / total_pixels, 4),
        })

    img.close()
    rgb_img.close()
    return json.dumps({
        "path": path,
        "count": len(palette),
        "palette": palette,
    }, indent=2)


EXTRACT_PALETTE_SCHEMA = {
    "name": "extract_palette",
    "description": "Extract dominant colors from an image using Pillow quantization. Returns hex, RGB, and proportion. No extra dependencies needed.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to image file"},
            "count": {"type": "integer", "description": "Number of colors to extract (default: 8)"},
        },
        "required": ["path"],
    },
}

registry.register(
    name="extract_palette",
    toolset="image_processing",
    schema=EXTRACT_PALETTE_SCHEMA,
    handler=lambda args, **kw: _extract_palette(args, **kw),
    check_fn=_check_pillow,
)


# ---------------------------------------------------------------------------
# 11. make_sprite_sheet
# ---------------------------------------------------------------------------

def _make_sprite_sheet(args, **kw):
    directory = args.get("directory", "")
    if not os.path.isdir(directory):
        return json.dumps({"error": f"Directory not found: {directory}"})

    try:
        from PyTexturePacker import Packer
    except ImportError:
        return json.dumps({
            "error": "Missing dependency: PyTexturePacker. Install with: pip install PyTexturePacker"
        })

    Image = _ensure_pillow()
    output = args.get("output", os.path.join(directory, "spritesheet"))
    max_width = args.get("max_width", 2048)
    max_height = args.get("max_height", 2048)
    padding = args.get("padding", 1)

    Path(output).parent.mkdir(parents=True, exist_ok=True)

    packer = Packer.create(
        max_width=max_width,
        max_height=max_height,
        bg_color=0x00000000,
        border_padding=padding,
        shape_padding=padding,
        enable_rotated=False,
    )

    png_files = sorted(Path(directory).glob("*.png"))
    if not png_files:
        return json.dumps({"error": f"No PNG files found in {directory}"})

    for png in png_files:
        packer.pack(str(png))

    packer.save(output)

    atlas_path = output + ".png"
    json_path = output + ".json"

    result = {
        "atlas": atlas_path if os.path.isfile(atlas_path) else None,
        "metadata": json_path if os.path.isfile(json_path) else None,
        "sprite_count": len(png_files),
        "sprites": [p.name for p in png_files],
    }

    if os.path.isfile(atlas_path):
        result["atlas_size_bytes"] = os.path.getsize(atlas_path)
        atlas = Image.open(atlas_path)
        result["atlas_dimensions"] = f"{atlas.width}x{atlas.height}"
        atlas.close()

    return json.dumps(result, indent=2)


MAKE_SPRITE_SHEET_SCHEMA = {
    "name": "make_sprite_sheet",
    "description": "Pack a directory of PNGs into a sprite atlas + JSON metadata. Requires: pip install PyTexturePacker",
    "parameters": {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory containing PNG sprites"},
            "output": {"type": "string", "description": "Output base path (will create .png + .json, default: <dir>/spritesheet)"},
            "max_width": {"type": "integer", "description": "Max atlas width (default: 2048)"},
            "max_height": {"type": "integer", "description": "Max atlas height (default: 2048)"},
            "padding": {"type": "integer", "description": "Padding between sprites (default: 1)"},
        },
        "required": ["directory"],
    },
}

registry.register(
    name="make_sprite_sheet",
    toolset="image_processing",
    schema=MAKE_SPRITE_SHEET_SCHEMA,
    handler=lambda args, **kw: _make_sprite_sheet(args, **kw),
    check_fn=_check_pillow,
)

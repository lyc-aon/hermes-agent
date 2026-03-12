---
name: image-processing
description: Recipes and best practices for the image processing toolset — pipelines, format selection, and pixel art workflows
version: 1.0.0
author: Lycaon Solutions
license: MIT
metadata:
  hermes:
    tags: [Image Processing, Game Assets, Pixel Art, Optimization]
    requires_tools: [analyze_image_file]
---

# Image Processing — Pipelines & Best Practices

Guide for using the 11 image processing tools effectively. Covers common workflows, format decisions, and how to chain tools for best results.

## Tools Overview

| Tool | Use When |
|------|----------|
| `analyze_image_file` | First step — understand what you're working with |
| `crop_image` | Removing whitespace/transparency borders, or cutting a region |
| `resize_image` | Scaling up/down, fitting to target dimensions |
| `convert_image` | Changing format (PNG↔WebP↔JPEG↔AVIF↔SVG) |
| `color_adjust` | Tweaking brightness/contrast/saturation, or recoloring via tint |
| `optimize_image` | Compressing file size without visible quality loss |
| `image_effects` | Adding silhouette, outline, glow, shadow, or pixelation |
| `process_game_asset` | One-call pipeline: remove bg → crop → resize → optimize |
| `remove_background` | AI background removal (requires rembg) |
| `extract_palette` | Pull dominant colors from an image |
| `make_sprite_sheet` | Pack a directory of PNGs into an atlas + JSON metadata |

## Decision: Use `process_game_asset` or Individual Tools?

**Use `process_game_asset` when:**
- Converting an AI-generated image into a game sprite
- You want the standard pipeline (remove bg → crop → resize → optimize) in one call
- Target size is known (default 64x64)

**Use individual tools when:**
- You need to inspect results between steps
- You want non-standard order (e.g., resize before crop)
- You need effects (glow, outline) that aren't in the pipeline
- You're not making game assets

## Common Pipelines

### AI Image → Game Sprite (single call)
```
process_game_asset(path, width=64, height=64, pixel_art=true)
```
Handles everything. Use `pixel_art=false` for smooth/painted art styles.

### AI Image → Game Sprite (manual control)
```
1. analyze_image_file(path)              — check dimensions, transparency
2. remove_background(path)               — if it has a background
3. crop_image(path, mode="auto")         — trim empty space
4. resize_image(path, width=64, filter="nearest")  — scale down
5. optimize_image(path)                  — compress
```

### Sprite with Effects
```
1. process_game_asset(path)              — get the base sprite
2. image_effects(path, effect="outline", color="#ffffff", thickness=1)
   — or —
   image_effects(path, effect="glow", color="#00ffff", radius=8)
   — or —
   image_effects(path, effect="shadow", offset_x=2, offset_y=2)
```

### Color Variants from One Sprite
```
1. extract_palette(original)             — see what colors are in it
2. color_adjust(original, tint="#ff0000", output="red_variant.png")
3. color_adjust(original, tint="#0000ff", output="blue_variant.png")
4. color_adjust(original, tint="#00ff00", output="green_variant.png")
```
Tint rotates hue while preserving saturation and lightness — good for team colors, elemental variants, etc.

### Batch Sprite Sheet
```
1. (generate/process multiple sprites into a directory)
2. make_sprite_sheet(directory="/sprites/", max_width=1024, padding=1)
```
Outputs `spritesheet.png` + `spritesheet.json` with frame coordinates.

### Web Image Optimization
```
1. analyze_image_file(path)              — check format and size
2. convert_image(path, format="webp", quality=85)
   — or for modern browsers —
   convert_image(path, format="avif", quality=80)
3. optimize_image(output)                — squeeze out remaining bytes
```

### Photo Touch-Up
```
1. color_adjust(path, brightness=1.1, contrast=1.15, saturation=1.2)
2. resize_image(output, width=1920)      — if needed for web
3. optimize_image(output, quality=85)
```

## Format Selection

| Format | Best For | Alpha | Lossy | Notes |
|--------|----------|-------|-------|-------|
| PNG | Sprites, pixel art, screenshots | Yes | No | Use pngquant for smaller files |
| WebP | Web images, photos | Yes | Both | ~30% smaller than JPEG at same quality |
| AVIF | Modern web, photos | Yes | Yes | ~50% smaller than JPEG, slow to encode, needs Pillow codec |
| JPEG | Photos, no transparency needed | No | Yes | Universally supported |
| SVG | Icons, logos, simple shapes | N/A | N/A | Vector — infinite scaling. Uses potrace or vtracer |

**Rule of thumb:** Sprites → PNG. Web photos → WebP. Cutting edge → AVIF. Need vectors → SVG.

## Resampling Filters

| Filter | Use For |
|--------|---------|
| `nearest` | Pixel art — preserves hard edges, no blurring |
| `lanczos` | Photos and painted art — highest quality downscale |
| `bicubic` | General purpose — good balance of speed and quality |
| `bilinear` | Fast, acceptable quality for previews |

**Always use `nearest` for pixel art.** Any other filter will blur the pixels.

## Tips

- **Always `analyze_image_file` first** when working with an unfamiliar image. It tells you dimensions, format, transparency, and color count — all of which affect your tool choices.
- **`optimize_image` is safe to run in-place** (default behavior). It won't increase file size.
- **Crop before resize** — removing empty space first means the resize targets the actual content.
- **`process_game_asset` defaults to `pixel_art=true`** — set it to `false` for smooth/painted art to avoid jagged edges.
- **`color_adjust` tint is hue rotation**, not a color overlay. A red tint on a gray image stays gray (no saturation to rotate). Use `saturation` > 1.0 first if needed.
- **`extract_palette` needs no extra deps** — it uses Pillow's built-in quantization.
- **`remove_background` is heavy** (~500MB deps). It's optional — `process_game_asset` skips it gracefully if rembg isn't installed.

## Pitfalls

- **AVIF not available**: Depends on Pillow being built with libavif. The tool checks and gives a clear error. Fall back to WebP.
- **SVG from photos**: Potrace/vtracer vectorize by tracing edges. Results are artistic, not photorealistic. Best for simple shapes, icons, and pixel art.
- **Large images + `extract_palette`**: Works fine but quantization on very large images is slower. No timeout risk, just patience.
- **pngquant not installed**: `optimize_image` and `process_game_asset` fall back to Pillow's optimizer. Install pngquant for best PNG compression.

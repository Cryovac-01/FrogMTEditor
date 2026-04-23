"""Generate restrained technical illustration assets for the Qt desktop shell."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "src" / "native_assets"
MANIFEST_PATH = ASSET_DIR / "native_asset_manifest.json"
SCENE_SIZE = (2560, 1440)


def rgba(hex_value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    hex_value = hex_value.lstrip("#")
    return (int(hex_value[0:2], 16), int(hex_value[2:4], 16), int(hex_value[4:6], 16), alpha)


PALETTE = {
    "bg_0": rgba("#0b1218"),
    "bg_1": rgba("#101923"),
    "bg_2": rgba("#16212b"),
    "panel_0": rgba("#16212c", 244),
    "panel_1": rgba("#101923", 244),
    "panel_soft": rgba("#1c2733", 226),
    "line": rgba("#48596c", 255),
    "line_soft": rgba("#2b3744", 180),
    "text": rgba("#f4f8fc", 255),
    "muted": rgba("#93a0af", 255),
    "accent": rgba("#5ec277", 255),
    "accent_soft": rgba("#8bd5a0", 170),
    "cyan": rgba("#74c7dc", 255),
    "cyan_soft": rgba("#acddea", 150),
    "white_soft": rgba("#f7fbff", 165),
    "shadow": rgba("#000000", 84),
}


@dataclass(frozen=True)
class ExportSpec:
    filename: str
    crop: tuple[int, int, int, int]
    size: tuple[int, int]


@dataclass(frozen=True)
class SceneSpec:
    key: str
    prompt: str
    seed: int
    builder: Callable[[random.Random], Image.Image]
    outputs: tuple[ExportSpec, ...]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple[int, int, int, int], c2: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(4))  # type: ignore[return-value]


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        color = mix(top, bottom, y / max(1, height - 1))
        draw.line((0, y, width, y), fill=color)
    return image


def soft_glow(canvas: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int, int], blur: int) -> None:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
    canvas.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(radius=blur)))


def add_blueprint_grid(canvas: Image.Image, step: int = 88) -> None:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = canvas.size
    for x in range(0, width, step):
        alpha = 18 if x % (step * 4) else 28
        draw.line((x, 0, x, height), fill=(PALETTE["line_soft"][0], PALETTE["line_soft"][1], PALETTE["line_soft"][2], alpha))
    for y in range(0, height, step):
        alpha = 18 if y % (step * 4) else 28
        draw.line((0, y, width, y), fill=(PALETTE["line_soft"][0], PALETTE["line_soft"][1], PALETTE["line_soft"][2], alpha))
    canvas.alpha_composite(overlay)


def add_noise(canvas: Image.Image, amount: int = 10) -> None:
    noise = Image.effect_noise(canvas.size, amount).convert("L")
    grain = Image.merge("RGBA", (noise, noise, noise, Image.new("L", canvas.size, 12)))
    canvas.alpha_composite(grain)


def rounded_panel(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    fill_top: tuple[int, int, int, int],
    fill_bottom: tuple[int, int, int, int],
    radius: int = 28,
    outline: tuple[int, int, int, int] | None = None,
    shadow: bool = True,
) -> None:
    x0, y0, x1, y1 = box
    panel = vertical_gradient((x1 - x0, y1 - y0), fill_top, fill_bottom)
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, panel.size[0] - 1, panel.size[1] - 1), radius=radius, fill=255)
    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_image = Image.new("RGBA", panel.size, PALETTE["shadow"])
        shadow_layer.paste(shadow_image, (x0, y0 + 18), mask)
        canvas.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(radius=20)))
    canvas.paste(panel, (x0, y0), mask)
    if outline:
        ImageDraw.Draw(canvas).rounded_rectangle(box, radius=radius, outline=outline, width=2)


def draw_wave(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: tuple[int, int, int, int], width: int) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)


def draw_stat_card(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    kind: str,
    rng: random.Random,
) -> None:
    rounded_panel(canvas, box, PALETTE["panel_soft"], PALETTE["panel_1"], radius=26, outline=PALETTE["line"])
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + 18, y0 + 16, x1 - 18, y0 + 28), radius=10, fill=(255, 255, 255, 16))
    if kind == "wave":
        points = []
        for idx in range(6):
            px = x0 + 34 + idx * ((x1 - x0 - 68) / 5)
            py = y0 + 110 + math.sin(idx * 0.8 + rng.random() * 0.4) * 18 - idx * 4
            points.append((px, py))
        draw_wave(draw, points, PALETTE["accent"], 4)
        draw_wave(draw, [(x, y + 24) for x, y in points], PALETTE["cyan_soft"], 3)
    elif kind == "bars":
        bar_x = x0 + 42
        for idx, height in enumerate((72, 102, 64, 118)):
            fill = PALETTE["accent"] if idx in {1, 3} else PALETTE["white_soft"]
            draw.rounded_rectangle((bar_x, y1 - 46 - height, bar_x + 34, y1 - 46), radius=12, fill=fill)
            bar_x += 56
    elif kind == "spectrum":
        for row in range(4):
            y = y0 + 54 + row * 38
            draw.rounded_rectangle((x0 + 30, y, x1 - 32, y + 18), radius=9, fill=(255, 255, 255, 10))
            value = (0.35, 0.58, 0.47, 0.72)[row]
            draw.rounded_rectangle((x0 + 30, y, x0 + 30 + int((x1 - x0 - 62) * value), y + 18), radius=9, fill=PALETTE["accent"] if row in {1, 3} else PALETTE["cyan_soft"])
    canvas.alpha_composite(overlay)


def draw_dimension_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=2)
    if x1 == x2:
        draw.line((x1 - 10, y1, x1 + 10, y1), fill=color, width=2)
        draw.line((x2 - 10, y2, x2 + 10, y2), fill=color, width=2)
    if y1 == y2:
        draw.line((x1, y1 - 10, x1, y1 + 10), fill=color, width=2)
        draw.line((x2, y2 - 10, x2, y2 + 10), fill=color, width=2)


def draw_engine_blueprint(rng: random.Random) -> Image.Image:
    canvas = vertical_gradient(SCENE_SIZE, PALETTE["bg_0"], PALETTE["bg_2"])
    add_blueprint_grid(canvas, 92)
    soft_glow(canvas, (1960, 240), 240, rgba("#5ec277", 36), 110)
    soft_glow(canvas, (520, 300), 220, rgba("#74c7dc", 32), 90)

    rounded_panel(canvas, (220, 170, 760, 460), PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"])
    rounded_panel(canvas, (1830, 180, 2330, 440), PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"])
    rounded_panel(canvas, (1820, 530, 2360, 890), PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"])

    draw_stat_card(canvas, (220, 170, 760, 460), "wave", rng)
    draw_stat_card(canvas, (1830, 180, 2330, 440), "bars", rng)
    draw_stat_card(canvas, (1820, 530, 2360, 890), "spectrum", rng)

    tech = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tech)
    base = (760, 940, 1670, 1090)
    draw.rounded_rectangle(base, radius=40, outline=PALETTE["line"], width=3, fill=(18, 27, 36, 120))
    draw.line((860, 1014, 1572, 1014), fill=PALETTE["accent"], width=4)

    block = (840, 590, 1570, 888)
    draw.rounded_rectangle(block, radius=46, outline=PALETTE["white_soft"], width=3, fill=(44, 58, 72, 48))
    draw.rounded_rectangle((900, 654, 1508, 844), radius=34, outline=PALETTE["line"], width=2, fill=(27, 38, 49, 110))

    for idx in range(6):
        x0 = 922 + idx * 98
        draw.rounded_rectangle((x0, 488 + (idx % 2) * 14, x0 + 66, 690 + (idx % 2) * 14), radius=28, outline=PALETTE["white_soft"], width=3, fill=(64, 82, 99, 56))
        draw.ellipse((x0 + 18, 520 + (idx % 2) * 14, x0 + 48, 550 + (idx % 2) * 14), outline=PALETTE["line"], width=2)

    draw.line((980, 720, 1412, 720), fill=PALETTE["accent"], width=16)
    draw.line((884, 760, 760, 882), fill=PALETTE["white_soft"], width=10)
    draw.line((1540, 760, 1660, 882), fill=PALETTE["white_soft"], width=10)
    draw.ellipse((726, 848, 790, 912), outline=PALETTE["accent"], width=4, fill=(31, 44, 58, 180))
    draw.ellipse((1630, 848, 1694, 912), outline=PALETTE["accent"], width=4, fill=(31, 44, 58, 180))

    draw_dimension_line(draw, (804, 548), (804, 918), PALETTE["line"])
    draw_dimension_line(draw, (846, 942), (1566, 942), PALETTE["line"])
    draw_dimension_line(draw, (1716, 692), (1716, 914), PALETTE["cyan_soft"])
    draw.line((1716, 692, 1636, 692), fill=PALETTE["cyan_soft"], width=2)
    draw.line((1716, 914, 1674, 914), fill=PALETTE["cyan_soft"], width=2)

    canvas.alpha_composite(tech.filter(ImageFilter.GaussianBlur(radius=0.4)))
    add_noise(canvas, 7)
    return canvas


def draw_tire_blueprint(rng: random.Random) -> Image.Image:
    canvas = vertical_gradient(SCENE_SIZE, PALETTE["bg_0"], PALETTE["bg_2"])
    add_blueprint_grid(canvas, 92)
    soft_glow(canvas, (460, 260), 190, rgba("#74c7dc", 26), 80)
    soft_glow(canvas, (1970, 250), 220, rgba("#5ec277", 32), 100)

    draw_stat_card(canvas, (1700, 210, 2310, 520), "spectrum", rng)
    draw_stat_card(canvas, (1620, 620, 2340, 960), "wave", rng)

    tech = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tech)
    cx, cy = 940, 770
    outer = (420, 250, 1460, 1290)
    inner = (582, 410, 1298, 1130)
    core = (724, 552, 1156, 986)
    draw.ellipse(outer, outline=PALETTE["white_soft"], width=4, fill=(34, 46, 58, 40))
    draw.ellipse(inner, outline=PALETTE["line"], width=3, fill=(20, 29, 38, 100))
    draw.ellipse(core, outline=PALETTE["white_soft"], width=3, fill=(60, 76, 92, 70))
    draw.ellipse((842, 672, 1038, 868), outline=PALETTE["accent"], width=3, fill=(27, 39, 32, 110))

    for idx in range(16):
        angle = idx * math.tau / 16
        x1 = cx + math.cos(angle) * 148
        y1 = cy + math.sin(angle) * 148
        x2 = cx + math.cos(angle) * 248
        y2 = cy + math.sin(angle) * 248
        draw.line((x1, y1, x2, y2), fill=PALETTE["white_soft"], width=5)
    for idx in range(22):
        angle = idx * math.tau / 22
        x1 = cx + math.cos(angle) * 420
        y1 = cy + math.sin(angle) * 420
        x2 = cx + math.cos(angle) * 504
        y2 = cy + math.sin(angle) * 504
        draw.line((x1, y1, x2, y2), fill=PALETTE["line"], width=8)

    draw_dimension_line(draw, (360, 1280), (1520, 1280), PALETTE["line"])
    draw_dimension_line(draw, (1574, 254), (1574, 1282), PALETTE["line"])
    draw.line((1574, 462, 1382, 462), fill=PALETTE["cyan_soft"], width=2)
    draw.line((1574, 932, 1296, 932), fill=PALETTE["cyan_soft"], width=2)

    card = (240, 920, 680, 1140)
    rounded_panel(tech, card, PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"], shadow=False)
    draw.rounded_rectangle((270, 954, 638, 972), radius=8, fill=(255, 255, 255, 14))
    draw.line((284, 1046, 370, 1006), fill=PALETTE["cyan"], width=4)
    draw.line((370, 1006, 452, 1038), fill=PALETTE["white_soft"], width=4)
    draw.line((452, 1038, 560, 970), fill=PALETTE["accent"], width=4)
    draw.line((560, 970, 632, 994), fill=PALETTE["white_soft"], width=4)

    canvas.alpha_composite(tech.filter(ImageFilter.GaussianBlur(radius=0.4)))
    add_noise(canvas, 7)
    return canvas


def draw_audio_board(rng: random.Random) -> Image.Image:
    canvas = vertical_gradient(SCENE_SIZE, PALETTE["bg_0"], PALETTE["bg_2"])
    add_blueprint_grid(canvas, 88)
    soft_glow(canvas, (560, 240), 180, rgba("#74c7dc", 30), 85)
    soft_glow(canvas, (1980, 260), 220, rgba("#5ec277", 34), 100)

    draw_stat_card(canvas, (280, 180, 1040, 560), "wave", rng)
    draw_stat_card(canvas, (1130, 180, 2260, 620), "wave", rng)

    tech = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tech)

    board = (360, 760, 2240, 1160)
    rounded_panel(tech, board, PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"], shadow=False)
    for idx in range(8):
        x = 470 + idx * 190
        draw.rounded_rectangle((x, 816, x + 28, 1096), radius=14, outline=PALETTE["line"], width=2, fill=(19, 29, 38, 140))
        slider_y = 948 - (idx % 4) * 42 - (idx // 4) * 12
        fill = PALETTE["accent"] if idx in {1, 4, 6} else PALETTE["white_soft"]
        draw.rounded_rectangle((x - 10, slider_y, x + 38, slider_y + 54), radius=18, fill=fill)
    for idx in range(4):
        knob_y = 902 + idx * 64
        for col in range(3):
            cx = 1710 + col * 124
            draw.ellipse((cx - 34, knob_y - 34, cx + 34, knob_y + 34), outline=PALETTE["white_soft"], width=3, fill=(33, 45, 57, 110))
            start_angle = 210
            end_angle = 318 - idx * 8 + col * 6
            draw.arc((cx - 38, knob_y - 38, cx + 38, knob_y + 38), start=start_angle, end=end_angle, fill=PALETTE["accent"], width=5)

    meter = (1120, 690, 1580, 1110)
    rounded_panel(tech, meter, PALETTE["panel_soft"], PALETTE["panel_1"], outline=PALETTE["line"], shadow=False)
    for idx, height in enumerate((120, 180, 138, 212, 154)):
        x = 1180 + idx * 74
        fill = PALETTE["accent"] if idx in {1, 3} else PALETTE["white_soft"]
        draw.rounded_rectangle((x, 1030 - height, x + 40, 1030), radius=14, fill=fill)

    canvas.alpha_composite(tech.filter(ImageFilter.GaussianBlur(radius=0.35)))
    add_noise(canvas, 7)
    return canvas


def build_brand_mark() -> Image.Image:
    canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    soft_glow(canvas, (70, 52), 34, rgba("#5ec277", 52), 18)
    soft_glow(canvas, (48, 76), 24, rgba("#74c7dc", 44), 18)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((14, 14, 114, 114), outline=PALETTE["line"], width=3, fill=(18, 27, 36, 228))
    draw.arc((22, 22, 106, 106), start=210, end=342, fill=PALETTE["accent"], width=8)
    draw.arc((22, 22, 106, 106), start=8, end=156, fill=PALETTE["cyan_soft"], width=6)
    draw.line((42, 80, 62, 60), fill=PALETTE["white_soft"], width=4)
    draw.line((62, 60, 84, 70), fill=PALETTE["cyan"], width=4)
    draw.line((84, 70, 96, 48), fill=PALETTE["accent"], width=4)
    for point, fill in (((42, 80), PALETTE["white_soft"]), ((62, 60), PALETTE["cyan"]), ((84, 70), PALETTE["accent"]), ((96, 48), PALETTE["accent_soft"])):
        draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=fill)
    return canvas


def export_crop(scene: Image.Image, crop: tuple[int, int, int, int], size: tuple[int, int], destination: Path) -> None:
    tile = scene.crop(crop)
    tile = ImageOps.fit(tile, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    destination.parent.mkdir(parents=True, exist_ok=True)
    tile.save(destination, format="PNG", optimize=True)


def save_png(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def build_scene_specs() -> tuple[SceneSpec, ...]:
    return (
        SceneSpec(
            key="engine_blueprint",
            prompt=(
                "Use case: ui-mockup. Asset type: enterprise desktop illustration. "
                "Primary request: precise engine blueprint board with restrained glass telemetry, dark slate panels, "
                "subtle green accent, cyan analytical highlights, and no text."
            ),
            seed=71811,
            builder=draw_engine_blueprint,
            outputs=(
                ExportSpec("welcome_hero.png", (160, 120, 2380, 1322), (960, 520)),
                ExportSpec("create_engine_scene.png", (720, 320, 1920, 1020), (560, 320)),
                ExportSpec("curve_banner.png", (1340, 490, 2340, 848), (620, 220)),
                ExportSpec("header_mesh.png", (770, 550, 1950, 900), (640, 180)),
                ExportSpec("sidebar_signal.png", (235, 168, 840, 460), (320, 120)),
            ),
        ),
        SceneSpec(
            key="tire_blueprint",
            prompt=(
                "Use case: ui-mockup. Asset type: enterprise desktop illustration. "
                "Primary request: technical tire and wheel detail board with measured linework, restrained green accents, "
                "cool cyan analysis highlights, and no text."
            ),
            seed=71812,
            builder=draw_tire_blueprint,
            outputs=(
                ExportSpec("create_tire_scene.png", (420, 240, 1900, 1100), (560, 320)),
            ),
        ),
        SceneSpec(
            key="audio_board",
            prompt=(
                "Use case: ui-mockup. Asset type: enterprise desktop illustration. "
                "Primary request: premium audio control board with clean waveform monitors, mixer strips, "
                "dark technical surfaces, restrained green and cyan accents, and no text."
            ),
            seed=71813,
            builder=draw_audio_board,
            outputs=(
                ExportSpec("audio_banner.png", (980, 640, 2360, 1130), (620, 220)),
            ),
        ),
    )


def generate_assets() -> dict[str, object]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "generator": "pillow_technical_illustration_v3",
        "scene_size": {"width": SCENE_SIZE[0], "height": SCENE_SIZE[1]},
        "assets": [],
    }

    save_png(build_brand_mark(), ASSET_DIR / "brand_mark.png")
    manifest["brand_mark"] = {"filename": "brand_mark.png", "generator": "pillow_technical_illustration_v3"}

    for spec in build_scene_specs():
        rng = random.Random(spec.seed)
        scene = spec.builder(rng)
        outputs = []
        for export in spec.outputs:
            export_crop(scene, export.crop, export.size, ASSET_DIR / export.filename)
            outputs.append(
                {
                    "filename": export.filename,
                    "crop": {
                        "left": export.crop[0],
                        "top": export.crop[1],
                        "right": export.crop[2],
                        "bottom": export.crop[3],
                    },
                    "size": {"width": export.size[0], "height": export.size[1]},
                }
            )
        manifest["assets"].append(
            {
                "scene": spec.key,
                "seed": spec.seed,
                "prompt": spec.prompt,
                "outputs": outputs,
            }
        )

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    manifest = generate_assets()
    output_count = sum(len(scene["outputs"]) for scene in manifest.get("assets", []))
    print(f"Generated {output_count + 1} desktop UI assets in {ASSET_DIR}")
    print(f"Wrote asset manifest: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

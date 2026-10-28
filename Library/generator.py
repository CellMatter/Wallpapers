import bisect
import colorsys
import functools
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .config import config

spine_samples = 300


def smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0), 1)
    return t * t * (3 - 2 * t)


def make_spine(rng):
    base = rng.uniform(0.5, 0.62)
    bend = rng.uniform(0.95, 1.15)
    curl = rng.uniform(3.0, 5.0)
    waves = [(rng.uniform(0.04, 0.08), rng.uniform(3, 6.5), rng.uniform(0, math.tau)) for _ in range(2)]

    def spine_y(u):
        v = base + sum(a * math.sin(f * u + p) for a, f, p in waves)
        return v - curl * max(u - bend, 0) ** 2

    return spine_y


def spine_frame(spine_y, aspect):
    # Points along the spine, their arc length, and running sums of the unit normals pointing to its lower/right side.
    points, arc, sum_x, sum_y = [], [], [0], [0]
    for i in range(spine_samples + 1):
        u = -0.2 + i * (aspect + 0.4) / spine_samples
        y = spine_y(u)
        slope = (spine_y(u + 1e-4) - spine_y(u - 1e-4)) / 2e-4
        length = math.hypot(1, slope)
        arc.append(arc[-1] + math.hypot(u - points[-1][0], y - points[-1][1]) if points else 0)
        points.append((u, y))
        sum_x.append(sum_x[-1] - slope / length)
        sum_y.append(sum_y[-1] + 1 / length)
    return points, arc, sum_x, sum_y


def edge(frame, offset, scale):
    # An edge at distance d uses the normal averaged over the spine within 2d of each point. With the plain normal,
    # edges deeper than a hump's radius fold over themselves into sharp creases; the averaged one drapes instead.
    points, arc, sum_x, sum_y = frame
    result = []
    for (u, y), s in zip(points, arc):
        d = offset(u)
        lo, hi = bisect.bisect_left(arc, s - 2 * d), bisect.bisect_right(arc, s + 2 * d)
        nx, ny = sum_x[hi] - sum_x[lo], sum_y[hi] - sum_y[lo]
        length = math.hypot(nx, ny)
        result.append(((u + d * nx / length) * scale, (y + d * ny / length) * scale))
    return result


def draw_band(draw, frame, scale, start, end, shade_from, shade_to, steps):
    edges = [edge(frame, lambda u, t=k / steps: start(u) + t * (end(u) - start(u)), scale) for k in range(steps + 1)]
    for k in range(steps):
        shade = shade_from + (shade_to - shade_from) * k / steps
        draw.polygon(edges[k] + edges[k + 1][::-1], fill=int(shade))


def generate_wallpaper(width, height, seed=None):
    rng = random.Random(seed)
    supersample = config["supersample"]
    big_w, big_h = width * supersample, height * supersample
    aspect = width / height
    frame = spine_frame(make_spine(rng), aspect)

    canvas = Image.new("L", (big_w, big_h), 0)

    sheet_count = rng.randint(5, 7)
    spacing = rng.uniform(0.09, 0.12)
    fan_start, fan_amount = rng.uniform(0.3, 0.8), rng.uniform(0.9, 1.4)

    def fan(u):
        # Sheets are pinched together on the left and spread apart in the curl.
        return 0.65 + fan_amount * smoothstep(fan_start, aspect, u)

    wiggles = [(rng.uniform(0.1, 0.35), rng.uniform(1.5, 4), rng.uniform(0, math.tau)) for _ in range(sheet_count)]

    def sheet_top(i):
        return functools.cache(lambda u: sum(spacing * fan(u) * (1 + a * math.sin(f * u + p)) for a, f, p in wiggles[:i]))

    # Back to front: lower sheets first so upper ones overlap and shadow them.
    for i in reversed(range(sheet_count)):
        last = i == sheet_count - 1
        top = sheet_top(i)
        size = rng.uniform(1.05, 1.25) * (4 if last else 1)
        bottom = functools.cache(lambda u, top=top, size=size: top(u) + spacing * fan(u) * size)
        brightness = rng.uniform(75, 100)

        shadow = Image.new("L", (width, height), 0)
        outline = edge(frame, top, height) + edge(frame, bottom, height)[::-1]
        ImageDraw.Draw(shadow).polygon([(x + 6, y + 16) for x, y in outline], fill=140)
        shadow = shadow.filter(ImageFilter.GaussianBlur(22)).resize((big_w, big_h), Image.BILINEAR)
        canvas = ImageChops.subtract(canvas, shadow)
        draw = ImageDraw.Draw(canvas)

        # A fan of thin layers near the top, each starting with a lit edge, then a plain matte face.
        layer_count = rng.randint(12, 20)
        gaps = [rng.uniform(0.6, 1.0) for _ in range(layer_count)]
        lines_part = rng.uniform(0.55, 0.8) / (4 if last else 1)
        squeeze, squeeze_freq, squeeze_phase = rng.uniform(0.2, 0.5), rng.uniform(2, 6), rng.uniform(0, math.tau)

        def layer(p, top=top, bottom=bottom):
            # Layers bunch up and spread out along the sheet.
            def offset(u):
                local = p * (1 + squeeze * math.sin(squeeze_freq * u + squeeze_phase))
                return top(u) + min(local, 1) * (bottom(u) - top(u))
            return offset

        face_top = layer(lines_part)
        face_height = 1.0 if last else 0.4
        face_end = lambda u: face_top(u) + face_height * (bottom(u) - face_top(u))
        draw_band(draw, frame, big_h, face_top, face_end, brightness * 0.55, 0 if last else brightness * 0.4, 60 if last else 8)
        if not last:
            draw_band(draw, frame, big_h, face_end, bottom, brightness * 0.4, brightness * 0.3, 4)

        positions = [lines_part * sum(gaps[:j]) / sum(gaps) for j in range(layer_count)] + [lines_part]
        for j in range(layer_count):
            shade = brightness * (1 - 0.35 * j / layer_count)
            draw_band(draw, frame, big_h, layer(positions[j]), layer(positions[j + 1]), shade, shade * 0.9, 3)
        for j in range(layer_count):
            shade = brightness * (1 - 0.35 * j / layer_count)
            draw.line(edge(frame, layer(positions[j]), big_h), fill=min(255, int(shade * 1.3) + 10), width=supersample)

    image = canvas.resize((width, height), Image.LANCZOS)
    # Fade toward the left.
    falloff = Image.linear_gradient("L").rotate(90).resize((width, height)).point(lambda v: 190 + v * 65 // 255)
    image = ImageChops.multiply(image, falloff)
    # Bottom-right corner fades to black.
    corner_size = int(height * 1.3)
    corner = Image.radial_gradient("L").resize((corner_size, corner_size)).point(lambda v: min(255, v * 2))
    vignette = Image.new("L", (width, height), 255)
    vignette.paste(corner, (width - corner_size // 2, height - corner_size // 2))
    return ImageChops.multiply(image, vignette)


def get_random_bright_color():
    hue = random.uniform(*random.choice(config["hue_ranges"])) % 360
    saturation = random.uniform(*config["saturation"])
    value = random.uniform(*config["brightness"])
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, saturation, value))


def apply_tint(source, tint_r, tint_g, tint_b):
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    gray = rgba.convert("L")

    red = gray.point(lambda v: v * tint_r // 255)
    green = gray.point(lambda v: v * tint_g // 255)
    blue = gray.point(lambda v: v * tint_b // 255)

    return Image.merge("RGBA", (red, green, blue, alpha))


def render_wallpaper(width, height):
    return apply_tint(generate_wallpaper(width, height), *get_random_bright_color())

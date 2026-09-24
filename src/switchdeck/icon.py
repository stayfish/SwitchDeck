from __future__ import annotations


def create_tray_image(size: int = 64):
    """Create a transparent icon containing one black bidirectional arrow."""
    from PIL import Image, ImageDraw

    scale = 4
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = canvas_size // 2
    left = int(canvas_size * 0.12)
    right = int(canvas_size * 0.88)
    head = int(canvas_size * 0.22)
    half_height = int(canvas_size * 0.20)
    width = max(4, int(canvas_size * 0.09))
    black = (0, 0, 0, 255)

    draw.line((left + head, y, right - head, y), fill=black, width=width)
    draw.polygon(
        [(left, y), (left + head, y - half_height), (left + head, y + half_height)],
        fill=black,
    )
    draw.polygon(
        [(right, y), (right - head, y - half_height), (right - head, y + half_height)],
        fill=black,
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)

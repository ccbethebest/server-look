"""Rebuild the application icon (requires Pillow only at development time)."""
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    assets = Path(__file__).resolve().parents[1] / 'assets'
    assets.mkdir(exist_ok=True)
    image = Image.new('RGBA', (512, 512))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 492, 492), radius=110, fill='#142C48')
    draw.rounded_rectangle((102, 68, 410, 444), radius=38, fill='#244866')
    for y in (100, 204, 308):
        draw.rounded_rectangle((124, y, 388, y + 84), radius=18, fill='#EDF5FC')
        draw.rounded_rectangle((145, y + 24, 259, y + 34), radius=5, fill='#52748F')
        draw.rounded_rectangle((145, y + 48, 235, y + 58), radius=5, fill='#A1B7C8')
        draw.ellipse((324, y + 30, 348, y + 54), fill='#13B89A')
    image.save(assets / 'server.png')
    image.save(assets / 'server.ico', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == '__main__':
    main()

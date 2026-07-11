from PIL import Image

from sprite_atlas.remove_background import remove_presentation_background


def test_checkerboard_corners_become_transparent():
    img = Image.new("RGB", (32, 32), (240, 240, 240))
    out = remove_presentation_background(img)
    assert out.getpixel((0, 0))[3] == 0

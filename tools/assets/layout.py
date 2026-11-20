"""Default VRAM placement of the book's generated textures (single source of truth).

Image x is in 16-bit units, y in lines; CLUT x is a multiple of 16. The two 320x240
draw/display buffers of the book's projects occupy x 0..319, y 0..479, so everything
here lives to the right of x=320 or below y=480.

Each entry: (texture name from texgen.py, bpp, x, y, clut_x, clut_y)
"""
SETS = {
    # SHIP.TPK: 3 textures, all in page x=10 (640..703), y page 0
    "ship": [("hull_a", 4, 640, 0, 0, 480), ("hull_b", 4, 656, 0, 0, 481), ("wing", 4, 672, 0, 0, 482)],
    # TRACK.TPK: 8 tiles, 2 rows of 4 in page x=6 (384..447)
    "track": [(n, 4, 384 + 16 * (i % 4), 64 * (i // 4), 16, 480 + i) for i, n in enumerate(
        ["asphalt", "asphalt_worn", "lane_stripe", "boost", "start_line", "wall_a", "wall_b", "glow"])],
    # PROPS.TPK: scenery textures, page x=8 (512..575)
    "props": [("pylon", 4, 512, 0, 32, 480), ("tower", 4, 520, 0, 32, 481)],
    # Chapter 30 demo textures (loose TIMs)
    "demo": [("crate", 8, 704, 0, 0, 496), ("panel", 4, 736, 0, 0, 497), ("logo", 4, 768, 0, 0, 498),
             ("sky16", 16, 832, 0, 0, 0)],
}

def placement(set_name, index):
    n, bpp, x, y, cx, cy = SETS[set_name][index]
    return dict(name=n, bpp=bpp, x=x, y=y, clut_x=cx, clut_y=cy)

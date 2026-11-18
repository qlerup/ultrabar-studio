"""Read model-matched thumbnails from a local Bambu Studio installation."""

import base64
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path

from PIL import Image


THUMBNAILS = {
    'a1': ('A1', 'printer_thumbnail_n2s_png.png'),
    'a1-mini': ('A1 mini', 'printer_thumbnail_n1_png.png'),
    'a2l': ('A2L', 'printer_preview_N9.png'),
    'p1p': ('P1P', 'printer_thumbnail_p1p_png.png'),
    'p1s': ('P1S', 'printer_thumbnail_p1s_png.png'),
    'p2s': ('P2S', 'printer_thumbnail_N7_png.png'),
    'x1': ('X1', 'printer_thumbnail_png.png'),
    'x1c': ('X1 Carbon', 'printer_thumbnail_x1c_png.png'),
    'x1e': ('X1E', 'printer_thumbnail_x1e_png.png'),
    'x2d': ('X2D', 'printer_thumbnail_N6_png.png'),
    'h2d': ('H2D', 'printer_thumbnail_h2d_png.png'),
    'h2d-pro': ('H2D Pro', 'printer_thumbnail_o1e_png.png'),
    'h2s': ('H2S', 'printer_thumbnail_o1s_png.png'),
    'h2c': ('H2C', 'printer_thumbnail_o1c_png.png'),
    'h3c': ('H3C', 'printer_thumbnail_N10_png.png'),
}


def installation_dirs():
    for variable in ('ProgramW6432', 'ProgramFiles', 'LOCALAPPDATA'):
        location = os.environ.get(variable)
        if location:
            root = Path(location)
            yield root / 'Programs' if variable == 'LOCALAPPDATA' else root


@lru_cache(maxsize=len(THUMBNAILS))
def thumbnail(model):
    asset = THUMBNAILS.get(model)
    if asset is None:
        return None
    name, filename = asset
    for root in installation_dirs():
        resources = root / 'Bambu Studio' / 'resources'
        for path in (resources / 'images' / filename, resources / 'profiles' / 'BBL' / f'Bambu Lab {name}_cover.png'):
            if encoded := encode_thumbnail(path):
                return encoded
    return None


def encode_thumbnail(path):
    try:
        with Image.open(path, formats=['PNG']) as image:
            if max(image.size) > 2048:
                return None
            picture = image.convert('RGBA')
    except (OSError, Image.DecompressionBombError):
        return None
    bounds = picture.getbbox(alpha_only=True)
    if not bounds:
        return None
    picture = picture.crop(bounds)
    for size in (100, 80, 64):
        picture.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = BytesIO()
        picture.quantize(colors=96, method=Image.Quantize.FASTOCTREE).save(output, format='PNG', optimize=True)
        if output.tell() <= 4096:
            return base64.b64encode(output.getvalue()).decode('ascii')
    return None

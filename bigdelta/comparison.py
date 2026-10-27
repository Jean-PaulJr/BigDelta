"""Raster comparison. Explicitly requires matching sheet extents; no semantic inference."""
import base64
import io

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageFilter, ImageOps


def png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def render(path, number):
    with pdfium.PdfDocument(str(path)) as doc:
        if not 1 <= number <= len(doc):
            raise ValueError('Page number is outside the document.')
        page = doc[number - 1]
        w, h = page.get_size()
        bitmap = page.render(scale=min(1.5, 1600 / max(w, h)))
        image = bitmap.to_pil().convert('RGB').copy()
        bitmap.close()
        page.close()
        return image, (round(w, 1), round(h, 1))


def compare(left_path, right_path, left_page, right_page):
    left, ls = render(left_path, left_page)
    right, rs = render(right_path, right_page)
    if ls != rs or left.size != right.size:
        raise ValueError('Sheets must have matching page sizes and orientation. Align exported drawings before comparison.')
    a, b = ImageOps.grayscale(left), ImageOps.grayscale(right)
    diff = ImageChops.difference(a, b)
    mask = diff.point(lambda v: 255 if v > 35 else 0)
    changed = mask.histogram()[255] / (left.width * left.height) * 100
    # Old ink is magenta; new ink is teal; coincident ink is dark.
    overlay = Image.merge('RGB', (b, a, ImageChops.lighter(a, b)))
    highlighted = Image.composite(Image.new('RGB', left.size, '#ef794d'), right, mask.filter(ImageFilter.MaxFilter(3)))
    return dict(left=png(left), right=png(right), overlay=png(overlay), difference=png(highlighted),
                changed_percent=round(changed, 4), width=left.width, height=left.height)

import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

import widget_presentation
import widget_scene


class WidgetImagePresetTests(unittest.TestCase):
    def test_package_can_resize_model_photo_with_same_renderer(self):
        field = dict(key='model', type='choice', options=[dict(value='standard'), dict(value='tall')])
        panel = dict(connection=dict(fields=[field]))
        presentation = dict(api=1, source=dict(scope='connection', key='model'), presets=[
            dict(value='standard'),
            dict(value='tall', images={'printer': {'large': [151, 4, 98, 132], 'asset': 'large.png'}}),
        ])
        widget_presentation.validate(presentation, panel)
        layout = {'large': [dict(op='image', value='printer', box=[158, 49, 87, 87])]}
        photo = widget_scene.encoded(Image.new('RGBA', (60, 90), 'red'))
        with patch('bambu_artwork.local_image', return_value=photo) as selected, patch(
            'bambu_artwork.thumbnail', return_value=photo
        ):
            results = []
            for model in ('standard', 'tall'):
                preset = widget_presentation.resolve(presentation, {}, {'model': model})
                spec = dict(kind='bambu', _presentation=preset)
                frame = widget_scene.make(layout, 'large', spec, {}, {'model': model}, 'Printer', 0)
                image = Image.open(io.BytesIO(base64.b64decode(frame['png'])))
                results.append(image.getchannel('R').point(lambda pixel: 255 if pixel == 255 else 0).getbbox())
            selected.assert_called_once_with('large.png')
        self.assertEqual(results, [(172, 49, 230, 136), (156, 4, 244, 136)])
        presentation['presets'][1]['images']['printer']['asset'] = '../unsafe.png'
        with self.assertRaises(ValueError):
            widget_presentation.validate(presentation, panel)

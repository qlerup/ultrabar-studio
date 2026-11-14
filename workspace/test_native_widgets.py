from copy import deepcopy
import unittest
from editor import EditError
from native_widgets import specifications


def card(key,drive):
    return dict(id='studio_native_'+key*32,type='PC_CONTROL',param=dict(payload=dict(action='studioNative',params=dict(kind='disk',drive=drive,accent='#94d9bb'))))


class NativeWidgetTests(unittest.TestCase):
    def test_per_widget_drive_sources_survive(self):
        rows=[dict(homeData=[card('a','C:\\'),card('b','D:\\'),card('c','all')])]
        result=specifications(rows)
        self.assertEqual([s['drive'] for s in result.values()],['C:\\','D:\\','all'])

    def test_legacy_cards_do_not_get_native_renderers(self):
        self.assertEqual(specifications([dict(homeData=[dict(type='STORAGE',id='original')])]),{})

    def test_bad_data_is_rejected_before_native_code(self):
        for field,value in [('drive','../../private'),('drive',None),('kind','shell'),('accent','red')]:
            widget=card('a','C:\\');widget['param']['payload']['params'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(EditError):
                specifications([dict(homeData=[widget])])

    def test_profile_id_collision_cannot_change_sensor(self):
        first=card('a','C:\\');second=deepcopy(first);second['param']['payload']['params']['drive']='D:\\'
        with self.assertRaises(EditError):specifications([dict(homeData=[first]),dict(homeData=[second])])

    def test_wrong_native_id_is_rejected(self):
        widget=card('a','all');widget['id']='stock'
        with self.assertRaises(EditError):specifications([dict(homeData=[widget])])

    def test_background_and_text_colors_are_independent(self):
        first=card('a','C:\\');first['bgColor']='#f2f4f0';first['param']['payload']['params']['textColor']='#172421'
        second=card('b','D:\\')
        result=specifications([dict(homeData=[first,second])])
        self.assertEqual(result[first['id']]['background'],'#f2f4f0')
        self.assertEqual(result[first['id']]['textColor'],'#172421')
        self.assertEqual(result[second['id']]['background'],'#192325')

    def test_invalid_text_color_is_rejected(self):
        widget=card('a','all');widget['param']['payload']['params']['textColor']='invalid'
        with self.assertRaises(EditError):specifications([dict(homeData=[widget])])


if __name__=='__main__':unittest.main()

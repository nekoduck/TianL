import tempfile, unittest
from pathlib import Path

from tianl.core import rnd, rnd_b2, cal, cal_str, SLOTS, t_of, day_slot
from tianl.defs import Defs, DefsError


def write(root, name, text):
    p = Path(root) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


class CoreTests(unittest.TestCase):
    def test_rng_is_counter_based(self):
        self.assertEqual(rnd(1, 'a', 2), rnd(1, 'a', 2))
        self.assertNotEqual(rnd(1, 'a', 2), rnd(1, 'a', 3))
        self.assertTrue(0 <= rnd(7) < 1 and 0 <= rnd_b2(7) < 1)
        self.assertNotEqual(rnd(1), rnd_b2(1))

    def test_calendar(self):
        self.assertEqual(len(SLOTS), 12)
        c = cal(360 + 97)
        self.assertEqual((c['year'], c['month'], c['dom'], c['festival']), (1, 4, 8, '佛诞'))
        self.assertEqual(cal_str(360 + 97), '第1年四月初八')
        self.assertEqual(day_slot(t_of(5, 7)), (5, 7))


class DefsTests(unittest.TestCase):
    def test_inheritance_and_refs(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '''
["facility:base:bed"]
_abstract = true
slots = 1
ads = { e = 30 }
["facility:shaolin:bed"]
parent = "facility:base:bed"
ads = { c = 1 }
place = "place:shaolin:dorm"
["place:shaolin:dorm"]
code = "SH_DORM"
name = "僧寮"
''')
            D = Defs.load(d)
            bed = D.get('facility:shaolin:bed')
            self.assertEqual(bed['slots'], 1)
            self.assertEqual(bed['ads'], {"e": 30, "c": 1})   # 字典逐层合并
            self.assertNotIn('_abstract', bed)
            self.assertEqual([x['id'] for x in D.by_kind('facility')], ['facility:shaolin:bed'])
            self.assertEqual(len(D.by_kind('facility', include_abstract=True)), 2)
            self.assertEqual(D.by_code('place', 'SH_DORM')['name'], '僧寮')

    def test_dangling_ref_cycle_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["place:x:a"]\ncode="A"\nnext = "place:x:missing"\nnote = "place:x:ignored"\n')
            with self.assertRaises(DefsError) as cm:
                Defs.load(d)
            self.assertTrue(any('place:x:missing' in p for p in cm.exception.problems))
            self.assertFalse(any('ignored' in p for p in cm.exception.problems))
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["item:x:a"]\nparent="item:x:b"\n["item:x:b"]\nparent="item:x:a"\n')
            with self.assertRaises(DefsError):
                Defs.load(d)
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["item:x:a"]\nv=1\n')
            write(d, 'b.toml', '["item:x:a"]\nv=2\n')
            with self.assertRaises(DefsError):
                Defs.load(d)

    def test_place_needs_code_and_unique(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["place:x:a"]\nname="甲"\n')
            with self.assertRaises(DefsError):
                Defs.load(d)
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["place:x:a"]\ncode="Z"\n["place:x:b"]\ncode="Z"\n')
            with self.assertRaises(DefsError):
                Defs.load(d)

    def test_bad_key(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'a.toml', '["nonsense:x:a"]\nv=1\n')
            with self.assertRaises(DefsError):
                Defs.load(d)


if __name__ == '__main__':
    unittest.main()

"""canon 测试的公共件（本文件自己没有用例）：合成的三联版面小书、临时目录、真原文的缓存载入。

合成文本全部是为测试自编的虚构内容，与任何已出版作品无关；真原文只在 sources/tianlong.txt 存在时才读，
测试里**不写任何原文片段**：真文本的锚点、窗口都是从载入的文本里现取的。
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tianl.canon import schema as S
from tianl.canon import text as T

REAL_SOURCE = S.REPO_ROOT / 'sources' / 'tianlong.txt'
HAVE_REAL = REAL_SOURCE.is_file()
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'canon'

IND = '　　'
WM = '★Ｄ★Ｏ★Ｓ★Ｐ★Ｙ★'


def synth_lines():
    """合成三联版面：论坛头、卷首、3 回正文、后记、附录、论坛尾；含独立水印行、行尾水印、全角空格空行。"""
    return [
        '-' * 42,
        '☆★某某论坛： bbs.example.com★☆',
        '★☆本电子书由 某某 整理制作☆★',
        '☆★版权归原作者所有，请勿用于商业用途★☆',
        '-' * 42,
        '“虚构作品集”序',
        IND + '这是为测试自编的序言，作者并不存在。',
        IND,
        '释义',
        IND + '序言的第二段，同样是虚构的。',
        '　',
        '',
        '一 石桥夜雨',
        '',
        IND + '林远在石桥等了三日，船始终没有来。老艄公说：“水涨了。”他只好住下。',
        IND + WM,
        IND + '当夜，苏小棠也来到石桥。她笑着说：“林少侠，你也在此？”林远点了点头。' + IND + WM,
        IND + '林远哈哈一笑……“好！”苏小棠道：“且慢。”',
        '二 白塔寺中 清晨',
        IND + '次日清晨，两人同往白塔寺借宿。慧明大师接待了他们！',
        IND + '大师年过六旬，言语不多。林远在院中闲逛。',
        IND + WM,
        IND + '另一位僧人慧能性子急躁，爱下棋。',
        '三 云梦镇上',
        IND + '林远追到云梦镇，在街口遇见了黑衣客。林远一怔。',
        IND + '黑衣客摘下面巾，竟是苏小棠。她把玉符交还林远。',
        '后记',
        IND + '这是虚构的后记，只有两句。第二句在这里。',
        IND + '后记的第二段。',
        '附录 某某先生书函',
        IND + '附录的唯一一段。',
        '',
        '-' * 42,
        '☆★某某论坛： bbs.example.com★☆',
        '★☆本电子书由 某某 整理制作☆★',
        '☆★版权归原作者所有，请勿用于商业用途★☆',
        '-' * 42,
        '',
    ]


def synth_text(crlf=False):
    t = '\n'.join(synth_lines())
    return t.replace('\n', '\r\n') if crlf else t


def synth_store(**kw):
    return T.TextStore.from_text(synth_text(), **kw)


class TmpDirCase(unittest.TestCase):
    """每个用例一个临时目录 self.tmp（Path）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def write(self, name, text):
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8', newline='')
        return p

    def source(self, text=None, name='book.txt'):
        return self.write(name, synth_text() if text is None else text)


def run_main(fn, argv):
    """调用某个 main(argv, out=…)，返回 (退出码, stdout 文本)；stderr 被截获，放在 run_main.err。"""
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = fn(argv, out=buf)
    run_main.err = err.getvalue()
    return rc, buf.getvalue()


run_main.err = ''


_REAL = None


def real_store():
    """真原文（载入一次，缓存；严格 50 回）。"""
    global _REAL
    if _REAL is None:
        _REAL = T.TextStore.from_file(REAL_SOURCE, expect_chapters=T.BOOK_CHAPTERS)
    return _REAL

"""C 段第一步验收：tianl/npc 忠实复现 reference/npc_spike.py（哈希 e8f8209eeb8ca94a）。

全部数字与哈希来自 reference/logs/npc_run_log.txt。除逐项断言外，还把 report.proto_report() 的输出
与日志逐行比对（耗时行只记录、不比对）。整个文件约 3 秒。
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tianl.npc.report import proto_report, strip_timing

LOG = Path(__file__).resolve().parent.parent / 'reference' / 'logs' / 'npc_run_log.txt'

BASE_HASH = 'e8f8209eeb8ca94a'
N1_HASH = {'无人代理': '49b736e95bc98576', '监院派人代理': '7ea5fd293c81e755'}
D90_HASH = '776dafc4d1ba0e4b'
SEED_HASH = {1: '8042175f53c5ed64', 2: 'adb39d7cbbaa4ef0', 3: '3693cd1af44172e5', 4: '8af473c0a39bc539',
             5: 'c76430933afccfb0'}


class ProtoBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines, cls.info = proto_report(include_all=True)
        cls.m = cls.info['m']
        cls.w = cls.info['base']
        cls.eng = cls.w.engine

    # ---- 1 基准 ----
    def test_baseline_hash(self):
        self.assertEqual(self.m['hash'], BASE_HASH)
        self.assertEqual(self.w.hash, BASE_HASH)

    def test_baseline_numbers(self):
        m, st = self.m, self.eng.stat
        self.assertEqual(round(m['attend'], 3), 0.993)
        self.assertEqual((m['theft'], m['seen']), (7, 1))
        self.assertEqual(m['report'], 1)
        self.assertEqual(m['sanction'], 1)
        self.assertEqual(m['cases'], {'悬案': 5, '已处分': 1, '在查': 1})
        self.assertEqual(m['absence'], 24)
        self.assertEqual((m['slack_seen'], m['slack']), (9, 24))
        self.assertEqual((m['half'], m['meals']), (0, 60))
        self.assertEqual(m['friends'], 35)
        self.assertEqual(m['foes'], 1)
        self.assertEqual(m['gone'], 0)
        self.assertEqual(st['ps'], 21600)                            # 决策数
        self.assertEqual(m['jobs'], (870, 870))                      # 差事完成/发布
        self.assertEqual((m['chat'], m['shared']), (625, 156))       # 闲谈、传话
        self.assertEqual((m['viol'], m['full']), (0, 200))           # 预约越界、满员改选
        self.assertEqual(m['friend_same'], 34)
        self.assertEqual(m['ill'], 10)
        self.assertEqual(m['acting'], 0)

    def test_package_shares_and_time_allocation(self):
        lines = self.lines
        want = ('行为包占比：作息 24.3%  值守 4.6%  处分 0.1%  岗位 4.5%  差事 4.0%  强制 1.5%  怠工 0.1%  自由 7.7%  '
                '越轨 0.3%  身份 4.8%  集体 48.1%')
        self.assertIn(want, lines)
        self.assertIn('清众 每日时辰分配：睡眠 3.21  坐禅 2.29  斋食 2.00  课诵 2.00  作务 0.94  自修 0.66  交游 0.49  '
                      '洗沐 0.26  病 0.13  受罚 0.02  其他 0.01', lines)
        self.assertIn('执事 每日时辰分配：睡眠 3.08  作务 2.50  斋食 2.00  课诵 1.83  坐禅 1.78  交游 0.35  '
                      '洗沐 0.22  自修 0.21  病 0.03', lines)
        self.assertIn('过堂人数：实到/应到 = 3546/3546（偏差 0.00%）', lines)

    def test_rumor_curve_and_hops(self):
        rm = self.eng.rumor
        self.assertEqual([c for d, c in rm.curve], [2, 5, 8, 11, 14, 20, 24, 28, 31, 32, 35, 37, 38, 38, 38, 35, 35, 35,
                                                    36, 37, 37, 22, 22, 22, 22])
        self.assertEqual([c for d, c in rm.cum], [2, 5, 8, 11, 14, 20, 24, 28, 31, 32, 35, 37, 38, 38, 38, 38, 38, 38,
                                                  39, 40, 40, 40, 40, 40, 40])
        self.assertEqual(dict(sorted(rm.hops.items())), {1: 5, 2: 11, 3: 14, 4: 9})
        self.assertEqual(rm.curve[-1][1], 22)

    def test_day8_traces_verbatim(self):
        text = '\n'.join(self.lines)
        self.assertIn('—— 第 8 日 慧海（典座，精进37 守戒78 合群29 馋33）\n   子 东寮·就寝[作息] | 丑 东寮·就寝[作息] | '
                      '寅 香积厨·厨务[值守] | 卯 香积厨·厨务[值守] | 辰 斋堂·早斋[集体] | 巳 香积厨·厨务[值守] | '
                      '午 斋堂·午斋[集体] | 未 廊下·闲谈[自由] | 申 香积厨·厨务[值守] | 酉 大雄宝殿·晚课[集体] | '
                      '戌 禅堂·晚坐[集体] | 亥 东寮·就寝[作息]', text)
        self.assertIn('—— 第 8 日 虚真（武僧，精进45 守戒22 合群53 馋92）\n   子 西寮·就寝[作息] | 丑 香积厨·夜里偷食[越轨] | '
                      '寅 禅堂·晨坐[集体] | 卯 大雄宝殿·早课[集体] | 辰 斋堂·早斋[集体] | 巳 后山·打柴[差事] | '
                      '午 斋堂·午斋[集体] | 未 西寮·小憩[自由] | 申 练武场·习武[身份] | 酉 大雄宝殿·晚课[集体] | '
                      '戌 禅堂·晚坐[集体] | 亥 西寮·就寝[作息]', text)
        self.assertIn('—— 第 8 日 虚平（武僧，精进18 守戒38 合群41 馋55）\n   子 西寮·就寝[作息] | 丑 西寮·就寝[作息] | '
                      '寅 西寮·贪睡不起[越轨] | 卯 西寮·贪睡不起[越轨] | 辰 斋堂·早斋[集体] | 巳 磨坊·舂米[差事] | '
                      '午 斋堂·午斋[集体] | 未 大雄宝殿·罚跪香[处分] | 申 练武场·习武[身份] | 酉 大雄宝殿·晚课[集体] | '
                      '戌 禅堂·晚坐[集体] | 亥 西寮·就寝[作息]', text)
        self.assertIn('—— 第 8 日 虚义（武僧，精进42 守戒60 合群56 馋18）', text)

    def test_glutton_causal_chain_verbatim(self):
        want = ['—— 惯犯 虚真 的因果链：',
                '   #0 第2日丑 偷食  见证0人 夜里偷食', '   #2 第2日寅 失窃 ←#0 见证5人 ',
                '   #6 第4日丑 偷食  见证0人 夜里偷食', '   #7 第4日寅 失窃 ←#6 见证5人 ',
                '   #14 第8日丑 偷食  见证0人 夜里偷食', '   #15 第8日寅 失窃 ←#14 见证5人 ',
                '   #20 第11日丑 偷食  见证0人 夜里偷食', '   #22 第11日寅 失窃 ←#20 见证5人 ',
                '   #31 第17日丑 偷食  见证0人 夜里偷食', '   #32 第17日寅 失窃 ←#31 见证5人 ',
                '   #36 第19日丑 偷食  见证1人 夜里偷食', '   #37 第19日丑 举报 ←#36 见证0人 ',
                '   #38 第20日丑 偷食  见证0人 夜里偷食', '   #39 第20日寅 失窃 ←#38 见证5人 ',
                '   #41 第20日午 处分 ←#36 见证59人 罚跪香三日']
        i = self.lines.index(want[0])
        self.assertEqual(self.lines[i:i + len(want)], want)

    # ---- 2 确定性与观察者 ----
    def test_rerun_and_observer(self):
        self.assertEqual(self.info['rerun'].hash, BASE_HASH)
        self.assertEqual(self.info['observed'].hash, BASE_HASH)
        self.assertEqual(self.info['observed'].engine.narr, 860)     # 观察者站在廊下，多生成 860 条叙述
        self.assertEqual(self.eng.narr, 0)
        self.assertIn('确定性：重跑哈希 True；观察者在廊下 True（多生成 860 条细节叙述）', self.lines)

    # ---- 3 实验 N1 ----
    def test_experiment_n1(self):
        for tag, h in N1_HASH.items():
            x, mx = self.info['n1_' + tag]
            self.assertEqual(mx['hash'], h, tag)
        no, mn = self.info['n1_无人代理']
        yes, my = self.info['n1_监院派人代理']
        self.assertEqual((mn['theft'], mn['seen'], mn['report'], mn['sanction'], mn['half'], mn['foes']),
                         (58, 48, 109, 45, 8, 17))
        self.assertEqual((my['theft'], my['seen'], my['report'], my['sanction'], my['half'], my['foes']),
                         (7, 1, 1, 1, 0, 1))
        self.assertEqual([t for d, t, h, hu in no.engine.daily if 9 <= d <= 16], [3, 4, 8, 27, 45, 55, 55, 55])
        self.assertEqual([t for d, t, h, hu in yes.engine.daily if 9 <= d <= 16], [3, 3, 4, 4, 4, 4, 4, 4])

    # ---- 4 90 日与五个种子 ----
    def test_90_days_and_seeds(self):
        x, m90 = self.info['d90']
        self.assertEqual(m90['hash'], D90_HASH)
        self.assertEqual((m90['theft'], m90['sanction'], m90['gone']), (16, 4, 1))    # 惯犯走完四级阶梯，迁单出寺
        for sd, h in SEED_HASH.items():
            self.assertEqual(self.info['seed%d' % sd][1]['hash'], h, 'seed %d' % sd)

    # ---- 5 与日志逐行比对 ----
    def test_report_matches_log_line_by_line(self):
        ref = LOG.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(self.lines), len(ref))
        for i, (a, b) in enumerate(zip(self.lines, ref), 1):
            self.assertEqual(strip_timing(a), strip_timing(b), '第 %d 行' % i)

    def regress_tool(self, *flags):
        tool = LOG.parent.parent.parent / 'tools' / 'npc_regress.py'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        r = subprocess.run([sys.executable, str(tool), *flags, '--diff'], capture_output=True, text=True, check=False,
                           env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out, ref = r.stdout.splitlines(), LOG.read_text(encoding='utf-8').splitlines()
        if '--all' not in flags:                                     # 基准部分 = 日志里 N1 标题之前的行
            ref = ref[:next(i for i, x in enumerate(ref) if x.startswith('== 实验 N1'))]
        self.assertEqual([strip_timing(x) for x in out], [strip_timing(x) for x in ref])
        self.assertIn('与日志逐行比对：一致', r.stderr)

    def test_regress_tool_stdout_has_the_prototype_format(self):
        """命令行工具（基准部分）的标准输出与日志逐行相同。完整的 --all 版本见下一条（慢测试，与上面 proto_report 同一函数）。"""
        self.regress_tool()

    @unittest.skipUnless(os.environ.get('TIANL_SLOW'), '慢测试：TIANL_SLOW=1 打开')
    def test_regress_tool_all_stdout_matches_the_whole_log(self):
        self.regress_tool('--all')

    def test_speed_tool_prints_a_ratio_and_leaves_the_prototype_untouched(self):
        tool = LOG.parent.parent.parent / 'tools' / 'npc_regress.py'
        r = subprocess.run([sys.executable, str(tool), '--speed', '1'], capture_output=True, text=True, check=False,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '')                                # 速度对照写到标准错误，不混进回归输出
        self.assertRegex(r.stderr, r'移植版/原型 = \d+\.\d+')
        stale = list((LOG.parent.parent / '__pycache__').glob('npc_spike*')) if (LOG.parent.parent / '__pycache__').is_dir() else []
        self.assertEqual(stale, [])                                   # 加载原型时不写字节码：reference/ 下不留文件

    # ---- 6 速度：只记录，不是通过线 ----
    def test_speed_is_reported_not_asserted(self):
        us = self.m['us']
        self.assertGreater(us, 0)
        print('\n[速度记录] 基准每次决策 %.1f 微秒（原型日志 4.5 微秒；仅记录，不是通过线）' % us)


if __name__ == '__main__':
    unittest.main()

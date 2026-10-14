"""Synthetic coverage for point-by-point JD analysis."""
import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('jd_gap_analysis', Path(__file__).parents[1] / 'scripts/jd_gap_analysis.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


SYNTHETIC_JD = '''培训运营-抖音生活服务
职位描述
1、业务培训策略输出与体系落地闭环：开展培训体系建设。
2、项目运营：负责内外训项目落地。
3、组织经验萃取：提炼方法论。
4、学习资源搭建与AI赋能推广：建设课件与题库。
5、学习氛围建设：提升学习自驱力。
职位要求
1、本科及以上学历，有项目管理实操经验。
2、有抖音短视频和直播运营经验优先。
3、具备协调沟通和公众表达能力。
4、熟练使用PPT、思维导图及AI工具。
5、接受变化并有培训创新思考。
6、具备AI+培训融合思维。'''


def evidence():
    refs = ['yantu-segmentation', 'yantu-coordination', 'huohua-feedback-loop',
            'huohua-operation-guides', 'huohua-lifecycle', 'angli-structured-documents',
            'angli-qa-versioning', 'mirror-offline-evaluation', 'mirror-interactive-delivery']
    return {'person': {'education_zh': '合成大学｜本科'}, 'entries': [
        {'source_ref': 'career-evidence-bank.md#synthetic', 'bullets': [
            {'id': ref, 'zh': '合成测试证据：学习计划或文档整理。'} for ref in refs]}]}


class GapAnalysisTests(unittest.TestCase):
    def test_training_jd_has_all_points_and_seven_days(self):
        result = analysis.analyze(SYNTHETIC_JD, evidence())
        self.assertEqual(result['summary']['total'], 11)
        self.assertEqual([item['number'] for item in result['items']], [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 6])
        self.assertEqual(len(result['plan']), 7)
        self.assertEqual(result['items'][6]['fit'], '较弱相关')
        self.assertIn('短视频和直播', result['items'][6]['gap'])
        self.assertTrue(all(item['action'] and item['proof'] for item in result['items']))

    def test_missing_evidence_is_not_invented(self):
        result = analysis.analyze(SYNTHETIC_JD, {'person': {'education_zh': ''}, 'entries': []})
        self.assertEqual(result['summary']['related'], 0)
        self.assertTrue(all(not item['evidence'] and item['status'] == 'unverified' for item in result['items']))
        self.assertTrue(all(item['fit'] == '待核实' for item in result['items']))

    def test_generic_jd_uses_cautious_fallback(self):
        result = analysis.analyze('职位描述\n1、维护客户关系。\n职位要求\n1、熟练使用 SQL。', evidence())
        self.assertEqual(result['summary']['total'], 2)
        self.assertEqual(result['summary']['unverified'], 2)
        self.assertEqual(len(result['plan']), 7)

    def test_requires_numbered_points(self):
        with self.assertRaises(ValueError):
            analysis.analyze('只有一行没有编号的 JD', evidence())


if __name__ == '__main__':
    unittest.main()

"""Synthetic persistence checks for the private, offline BOSS workbench."""

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import boss_workspace


URL = 'https://www.zhipin.com/job_detail/Ab1234567890.html?lid=private-token'


class BossWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-boss-workspace-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name)
        (self.case / 'search-preferences.json').write_text(json.dumps({
            'locations': ['上海'], 'excluded_companies': ['原雇主公司']}, ensure_ascii=False), encoding='utf-8')

    def test_seed_preferences_and_reclassify_saved_rows(self):
        first = boss_workspace.state(self.case)
        self.assertEqual(first['settings']['cities'], ['上海'])
        self.assertEqual(first['settings']['excluded_companies'], ['原雇主公司'])
        self.assertIsNone(first['screen'])
        data = json.dumps({'jobs': [{'url': URL, 'company': '合成公司', 'title': 'AI 产品运营',
                                     'city': '上海', 'salary': '10-15K', 'tags': '双休',
                                     'description': '岗位职责：维护知识库。任职要求：有内容经验。'}]}, ensure_ascii=False)
        imported = boss_workspace.screen_jobs(self.case, {'data': data})
        self.assertEqual(imported['screen']['summary']['shortlist'], 1)
        self.assertEqual(imported['job_count'], 1)
        self.assertNotIn('lid=', imported['screen']['results'][0]['job']['url'])
        self.assertNotIn('lid=', (self.case / 'boss-jobs.json').read_text(encoding='utf-8'))
        settings = {**first['settings'], 'require_weekends_off': True, 'min_salary_k': 16}
        changed = boss_workspace.save_settings(self.case, {'settings': settings})
        self.assertEqual(changed['screen']['summary']['excluded'], 1)
        self.assertEqual(boss_workspace.state(self.case)['screen']['summary']['excluded'], 1)
        self.assertFalse((self.case / 'application-tracker.csv').exists())

    def test_blocked_companies_are_merged_without_external_action(self):
        result = boss_workspace.import_blocked(self.case, {'data': '原雇主公司\n合成公司\n合成公司'})
        self.assertEqual(result['settings']['excluded_companies'], ['原雇主公司', '合成公司'])
        self.assertFalse(result['automated_actions'])
        self.assertEqual(result['imported_companies'], 2)

    def test_bad_import_does_not_replace_previous_jobs(self):
        csv = '岗位链接,公司,岗位,城市\n' + URL + ',合成公司,运营,上海\n'
        boss_workspace.screen_jobs(self.case, {'data': csv})
        before = (self.case / 'boss-jobs.json').read_bytes()
        with self.assertRaises(ValueError):
            boss_workspace.screen_jobs(self.case, {'data': '岗位链接,公司\nhttps://example.test,甲,多余列'})
        self.assertEqual((self.case / 'boss-jobs.json').read_bytes(), before)
        with self.assertRaises(ValueError):
            boss_workspace.save_settings(self.case, {'settings': {'min_salary_k': 20, 'max_salary_k': 10}})
        self.assertFalse((self.case / 'boss-settings.json').exists())


if __name__ == '__main__':
    unittest.main()

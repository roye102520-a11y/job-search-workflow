"""Synthetic, offline checks for the BOSS export assistant."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import boss_assist as boss


def job(**changes):
    row = {
        'url': 'https://www.zhipin.com/job_detail/Ab1234567890.html?lid=private-session',
        'company': '合成甲公司', 'title': 'AI 产品运营', 'city': '上海',
        'salary': '10-15K·13薪', 'company_size': '1000-9999人',
        'open_positions': '24', 'tags': ['双休', '五险一金'],
        'description': '维护 AI 产品知识库。',
    }
    row.update(changes)
    return row


class BossAssistantTests(unittest.TestCase):
    def test_config_rejects_typos_bad_ranges_and_unsafe_placeholders(self):
        invalid = [
            {'salary_floor': 10}, {'keywords': '运营'}, {'keywords': ['']},
            {'min_salary_k': True}, {'max_salary_k': float('nan')},
            {'min_salary_k': 20, 'max_salary_k': 10},
            {'max_open_positions': -1}, {'max_open_positions': True},
            {'require_weekends_off': 'true'},
            {'greeting_confirmed': True},
            {'greeting_template': '我有 {candidate_metric} 的成果'},
            {'greeting_template': '你好 {company.__class__}'},
        ]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                boss.validate_config(config)

    def test_blocked_company_import_is_exact_and_deduplicated(self):
        self.assertEqual(boss.import_blocked_companies('公司名称\n- 合成甲公司\n合成乙,合成甲公司; #注释'), ['合成甲公司', '合成乙'])
        self.assertEqual(boss.import_blocked_companies('["合成甲公司", {"company":"合成乙"}]'), ['合成甲公司', '合成乙'])
        self.assertEqual(boss.import_blocked_companies('公司名称,备注\n合成甲公司,已屏蔽\n合成乙,已屏蔽'), ['合成甲公司', '合成乙'])
        result = boss.evaluate_jobs([job(company='合成甲公司'), job(company='合成甲公司研究院', url='https://www.zhipin.com/job_detail/Cd1234567890.html')],
                                    {'excluded_companies': ['合成甲公司']})
        self.assertEqual([item['status'] for item in result['results']], ['excluded', 'shortlist'])

    def test_salary_never_infers_missing_or_annual_pay(self):
        rows = [job(salary='面议'), job(salary='年薪 30 万', url='https://www.zhipin.com/job_detail/Cd1234567890.html'),
                job(salary='5-6K', url='https://www.zhipin.com/job_detail/Ef1234567890.html'),
                job(salary='5-12K', url='https://www.zhipin.com/job_detail/Gh1234567890.html'),
                job(salary='1-1.5万/月', url='https://www.zhipin.com/job_detail/Ij1234567890.html')]
        result = boss.evaluate_jobs(rows, {'min_salary_k': 10})
        self.assertEqual([item['status'] for item in result['results']],
                         ['needs_verification', 'needs_verification', 'excluded', 'needs_verification', 'shortlist'])
        self.assertIn('未推断', result['results'][0]['needs_verification'][0])

    def test_weekend_claim_is_read_from_text_but_stays_unverified(self):
        rows = [job(tags='', description='没有说明休息安排'),
                job(tags='双休', description='实行大小周', url='https://www.zhipin.com/job_detail/Cd1234567890.html'),
                job(tags='', title='周末双休的运营岗位', url='https://www.zhipin.com/job_detail/Ef1234567890.html')]
        result = boss.evaluate_jobs(rows, {'require_weekends_off': True})
        self.assertEqual([item['status'] for item in result['results']], ['needs_verification', 'excluded', 'shortlist'])
        self.assertTrue(any('实际休息制度仍需核实' in reason for reason in result['results'][2]['reasons']))

    def test_open_count_zero_means_unlimited_and_unknown_needs_review(self):
        rows = [job(open_positions='999'), job(open_positions='', url='https://www.zhipin.com/job_detail/Cd1234567890.html')]
        unlimited = boss.evaluate_jobs(rows, {'max_open_positions': 0})
        self.assertEqual([r['status'] for r in unlimited['results']], ['shortlist', 'shortlist'])
        limited = boss.evaluate_jobs(rows, {'max_open_positions': 200})
        self.assertEqual([r['status'] for r in limited['results']], ['excluded', 'needs_verification'])

    def test_stable_id_dedup_ignores_session_parameters_but_unknown_urls_survive(self):
        rows = [job(), job(url='https://www.zhipin.com/job_detail/Ab1234567890.html?lid=another'),
                job(url='https://zhipin.com.evil.test/job_detail/Ab1234567890.html'),
                job(url='https://zhipin.com.evil.test/job_detail/Ab1234567890.html')]
        result = boss.evaluate_jobs(rows, {})
        self.assertEqual([r['status'] for r in result['results']],
                         ['shortlist', 'duplicate', 'needs_verification', 'needs_verification'])
        self.assertIsNone(boss.stable_boss_id('https://not-zhipin.com/job_detail/Ab1234567890.html'))
        self.assertIsNone(boss.stable_boss_id('https://www.zhipin.com:9999/job_detail/Ab1234567890.html'))
        self.assertEqual(result['results'][1]['duplicate_of'], 1)
        self.assertNotIn('lid=', result['results'][0]['job']['url'])

    def test_conflicting_rows_with_same_stable_id_are_not_silently_merged(self):
        result = boss.evaluate_jobs([job(), job(company='合成乙公司')], {})
        self.assertEqual(result['results'][1]['status'], 'needs_verification')
        self.assertIn('冲突', result['results'][1]['needs_verification'][0])

    def test_greeting_is_only_a_confirmed_local_draft(self):
        row = job()
        template = '您好，我关注 {company} 的 {title} 岗位，想了解岗位要求。'
        without_confirmation = boss.evaluate_jobs([row], {'greeting_template': template})
        self.assertIsNone(without_confirmation['results'][0]['greeting_draft'])
        result = boss.evaluate_jobs([row], {'greeting_template': template, 'greeting_confirmed': True})
        self.assertEqual(result['results'][0]['greeting_draft'], '您好，我关注 合成甲公司 的 AI 产品运营 岗位，想了解岗位要求。')
        self.assertFalse(result['automated_actions'])
        self.assertTrue(result['review_only'])

    def test_invalid_row_is_reported_and_valid_rows_are_not_lost(self):
        result = boss.evaluate_jobs([{'url': 'javascript:alert(1)', 'company': 'X', 'title': 'Y'},
                                     job(description='x' * 100001), job()], {})
        self.assertEqual(result['summary']['invalid'], 2)
        self.assertEqual(result['results'][0]['index'], 3)

    def test_json_csv_and_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / 'jobs.json'
            json_path.write_text(json.dumps({'jobs': [job()]}, ensure_ascii=False), encoding='utf-8')
            csv_path = root / 'jobs.csv'
            csv_path.write_text('岗位链接,公司,岗位,城市,薪资,公司规模,在招岗位数,标签,简介\n'
                                'https://www.zhipin.com/job_detail/Ab1234567890.html,合成甲公司,AI 产品运营,上海,10-15K,1000-9999人,24,双休,维护知识库\n', encoding='utf-8')
            config_path = root / 'settings.json'
            config_path.write_text(json.dumps({'keywords': ['AI']}, ensure_ascii=False), encoding='utf-8')
            blocked = root / 'blocked.txt'
            blocked.write_text('合成乙公司\n', encoding='utf-8')
            output = root / 'result.json'
            self.assertEqual(len(boss.load_jobs(json_path)), 1)
            self.assertEqual(len(boss.load_jobs(csv_path)), 1)
            self.assertEqual(len(boss.parse_jobs_text(json_path.read_text(encoding='utf-8'))), 1)
            self.assertEqual(len(boss.parse_jobs_text(csv_path.read_text(encoding='utf-8'))), 1)
            with self.assertRaises(ValueError):
                boss.parse_jobs_text('岗位链接,公司\nhttps://example.test,甲,多余列', 'csv')
            process = subprocess.run([sys.executable, str(ROOT / 'scripts/boss_assist.py'), '--jobs', str(csv_path),
                                      '--config', str(config_path), '--blocked-companies', str(blocked),
                                      '--output', str(output)], capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['summary']['shortlist'], 1)


if __name__ == '__main__':
    unittest.main()

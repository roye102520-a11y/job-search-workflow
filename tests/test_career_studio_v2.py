"""V2 regression corpus; every write uses disposable synthetic cases."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import resume_pipeline as pipeline
from jd_requirements import assess, summary
from evidence_selection import decisions
import boss_assist as boss
import career_workspace as workspace

CORPUS = json.loads((ROOT / 'tests/fixtures/career-v2-cases.json').read_text())


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='career-v2-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name) / 'case'
        shutil.copytree(ROOT / 'tests/fixtures/synthetic-case', self.case)
        self.data = pipeline.load_evidence(self.case)

    def request(self, **changes):
        value = dict(jd=CORPUS['single'][0]['jd'], title='用户运营', company='合成团队', family='auto', language='zh', url='https://example.test/job?id=v2')
        return {**value, **changes}

    def test_ten_single_and_ten_mixed_routes(self):
        for case in CORPUS['single'] + CORPUS['mixed']:
            with self.subTest(case=case['id']):
                result = pipeline.route(case['jd'], case['title'])
                self.assertEqual(result['family'], case['family'])
                self.assertIn('basis', result)
                self.assertEqual(result['score_type'], '规则排序分，非概率')

    def test_ten_hard_conditions(self):
        for case in CORPUS['hard']:
            with self.subTest(case=case['id']):
                items = assess(case['jd'], self.data)
                self.assertEqual(items[0]['status'], case['status'])
                if items[0]['status'] in {'supported', 'partial', 'not_met'}:
                    self.assertTrue(items[0]['evidence'])
                self.assertEqual(bool(summary(items)['required_blockers']), case['status'] != 'supported')

    def test_no_data_never_means_not_met(self):
        for jd in ['必需：至少10年用户运营经验。', '必需：计算机硕士。', '必需：5年机器学习经验。', '必需：SQL。']:
            self.assertEqual(assess(jd, {'person': {}, 'entries': []})[0]['status'], 'unknown')

    def test_degree_copy_is_candidate_specific(self):
        d = copy.deepcopy(self.data)
        d['person'].update(education_zh='合成第二候选人｜计算机｜硕士', education_en='Master in Computer Science')
        result = assess('必需：计算机硕士。', d)[0]
        self.assertEqual(result['status'], 'supported')
        self.assertIn('合成第二候选人', result['reason'])
        self.assertNotIn('商务英语', result['reason'])

    def test_adjacent_tags_do_not_prove_rag(self):
        d = copy.deepcopy(self.data)
        for e in d['entries']:
            for b in e['bullets']:
                b['zh'], b['en'] = '整理资料', 'Organized documents'
        self.assertEqual(assess('必需：RAG。', d)[0]['status'], 'partial')
        self.assertEqual(assess('必需：SQL。', d)[0]['status'], 'unknown')

    def test_manual_direction_does_not_override_unsupported(self):
        self.assertEqual(pipeline.route('负责分布式模型训练', '机器学习工程师', 'product-operations')['outcome'], 'unsupported')
        mixed = CORPUS['mixed'][5]
        result = pipeline.route(mixed['jd'], mixed['title'], 'user-operations')
        self.assertEqual(result['family'], 'user-operations')
        self.assertIsNotNone(result['secondary_family'])

    def test_selection_reports_every_candidate_and_does_not_mutate(self):
        before = copy.deepcopy(self.data)
        _, _, audit = decisions(self.data, 'ai-content-operations', '知识库 OCR RAG 离线评测 用户路径', budget=400)
        self.assertEqual(len(audit['candidates']), sum(len(e['bullets']) for e in self.data['entries']))
        self.assertTrue(all(i['reason'] and i['source_ref'] and i['dimensions'] for i in audit['candidates']))
        self.assertTrue(any(not i['selected'] for i in audit['candidates']))
        self.assertEqual(self.data, before)

    def test_priority_rescues_important_omitted_project(self):
        _, _, before = decisions(self.data, 'user-operations', '用户运营 用户服务', budget=400)
        selected, _, after = decisions(self.data, 'user-operations', '用户运营 用户服务', ['project-archive'], budget=400)
        self.assertFalse(any(i['selected'] for i in before['candidates'] if i['entry_id'] == 'project-archive'))
        self.assertTrue(any(e['id'] == 'project-archive' for e in selected))
        self.assertEqual(after['priorities'], ['project-archive'])

    def test_five_fact_update_and_conflict_samples(self):
        for mode in CORPUS['fact_updates']:
            with self.subTest(mode=mode):
                d = copy.deepcopy(self.data)
                if mode == 'source_hash_changed':
                    (self.case / 'coaching-state.md').write_text('changed')
                    with self.assertRaisesRegex(ValueError, '事实源已变化'):
                        pipeline.load_evidence(self.case)
                    shutil.copy2(ROOT / 'tests/fixtures/synthetic-case/coaching-state.md', self.case / 'coaching-state.md')
                elif mode == 'cache_content_changed':
                    old = pipeline.sha(self.case / 'resume-evidence.json')
                    d['person']['name_zh'] = '第二合成候选人'
                    (self.case / 'resume-evidence.json').write_text(json.dumps(d))
                    self.assertNotEqual(old, pipeline.sha(self.case / 'resume-evidence.json'))
                else:
                    if mode == 'pending_bullet': d['entries'][0]['bullets'][0]['confirmation_status'] = 'pending'
                    if mode == 'entry_conflict': d['entries'][0]['conflict'] = '职责尚未核对'
                    if mode == 'project_date_conflict': d['unconfirmed'].append({'field':'projects.start_date_conflict'})
                    selected, _, audit = decisions(d, 'user-operations', '用户服务 用户分层 RAG')
                    self.assertFalse(any(b['id'] == 'support-segmentation' for e in selected for b in e['bullets']) if mode != 'project_date_conflict' else any(e['kind']=='project' for e in selected))
                    self.assertTrue(any('冲突' in i['reason'] or '待确认' in i['reason'] for i in audit['candidates']))

    def test_ten_plus_screening_anomalies(self):
        config = {'min_salary_k':10, 'cities':['上海'], 'require_weekends_off':True, 'excluded_companies':['屏蔽主体'], 'company_aliases':{'屏蔽品牌':'屏蔽主体'}}
        for index, sample in enumerate(CORPUS['screening']):
            with self.subTest(index=index):
                row = {'url': f'https://www.zhipin.com/job_detail/Test{index:08d}.html', 'company':'合成公司', 'title':'运营', 'city':'上海', 'salary':'10-15K', 'tags':'双休', 'description':'维护用户关系并整理问题记录。'}
                row.update({k:v for k,v in sample.items() if k != 'expect'})
                result = boss.evaluate_jobs([row], config)['results'][0]
                self.assertEqual(result['status'], sample['expect'])
                self.assertIsNone(result['last_verified_at'])
                for key in ['matched_conditions','unmet_conditions','unknown_conditions','source']: self.assertIn(key,result)

    def test_salary_units_and_payment_counts(self):
        for value, base, count in [('10-15K·12薪',10,12),('10-15K·13薪',10,13),('1-1.5万/月·14薪',10,14),('10000-15000元/月',10,None),('年薪26万·13薪',20,13)]:
            d = boss.salary_details(value)
            self.assertEqual((d['monthly_min_k'],d['payments']),(base,count))
        self.assertIsNone(boss.salary_details('年薪26万')['monthly_min_k'])
        self.assertIsNone(boss.salary_details('10-15K')['annual_min_k'])

    def test_same_id_with_changed_conditions_is_conflict(self):
        row={'url':'https://www.zhipin.com/job_detail/Ab1234567890.html','company':'合成','title':'运营','salary':'10-15K'}
        result=boss.evaluate_jobs([row, {**row,'salary':'5-6K'}],{})
        self.assertEqual(result['results'][1]['status'],'needs_verification')

    def test_exact_repeat_reuses_files_and_new_priority_creates_version(self):
        before = (self.case / 'resume-evidence.json').read_bytes()
        first = pipeline.generate(self.case, self.request())
        again = pipeline.generate(self.case, self.request())
        self.assertTrue(again['reused'])
        self.assertEqual(first['output_dir'], again['output_dir'])
        changed = pipeline.generate(self.case, self.request(project_priorities=['project-archive']))
        self.assertNotEqual(first['output_dir'], changed['output_dir'])
        self.assertNotIn('manifest', changed['files'])
        self.assertEqual(before,(self.case / 'resume-evidence.json').read_bytes())

    def test_updated_cache_invalidates_material_reuse_and_portfolio(self):
        first = pipeline.generate(self.case, self.request())
        d = copy.deepcopy(self.data); d['person']['name_zh']='第二合成候选人'
        (self.case / 'resume-evidence.json').write_text(json.dumps(d))
        second = pipeline.generate(self.case, self.request())
        self.assertNotEqual(first['output_dir'],second['output_dir'])
        with self.assertRaisesRegex(ValueError,'过期'):
            workspace.build_portfolio(self.case,{'project_ids':['project-compass'],'resume_id':first['output_dir'].split('/')[-1]})

    def test_empty_workspace_has_first_action_and_no_fake_stats(self):
        empty=Path(self.tmp.name)/'empty';empty.mkdir()
        d=workspace.snapshot(empty)
        self.assertEqual(d['task']['primary_action'],'upload')
        self.assertEqual(d['task']['completed_fields'],[])
        self.assertEqual(d['stats']['submitted'],0)

    def test_stale_source_removes_recommendation_evidence(self):
        (self.case / 'coaching-state.md').write_text('changed')
        self.assertTrue(all(not r['evidence'] for r in workspace.recommendations(self.case)))

    def test_distinct_jds_and_candidates_do_not_share_selection(self):
        a=pipeline.preview_selection(self.case,self.request(jd='【合成】岗位职责：用户运营、用户分层、客户成功。记录用户服务问题，整理运营反馈与沟通事项。'))
        b=pipeline.preview_selection(self.case,self.request(title='知识运营',jd='【合成】岗位职责：OCR、文档清洗、知识库、问答、离线评测。维护内容版本，整理结构化文档。'))
        self.assertNotEqual(a['routing']['family'],b['routing']['family'])
        self.assertNotEqual(a['selection']['candidates'],b['selection']['candidates'])

if __name__=='__main__': unittest.main()

class V2AdditionalEvidenceTests(unittest.TestCase):
    def test_pending_education_is_not_used_as_supported(self):
        data={'person':{'education_zh':'合成大学｜本科'},'entries':[],'unconfirmed':[{'field':'person.education'}]}
        self.assertEqual(assess('必需：本科。',data)[0]['status'],'unknown')

    def test_future_employment_does_not_meet_ten_years(self):
        d=json.loads((ROOT/'tests/fixtures/synthetic-case/resume-evidence.json').read_text())
        d['entries'][0]['dates']='2030.01-2040.01'
        d['entries']=d['entries'][:1]
        self.assertEqual(assess('必需：至少10年用户运营经验。',d)[0]['status'],'unknown')

    def test_incomplete_submission_event_never_counts_as_real(self):
        with tempfile.TemporaryDirectory() as name:
            case=Path(name)
            event={'event_id':'synthetic-event','action':'attempt_result','result':'submitted','job_key':'one','timestamp':'2026-01-01T00:00:00+00:00'}
            (case/'application-events.jsonl').write_text(json.dumps(event)+'\n')
            self.assertEqual(workspace.snapshot(case)['stats']['submitted'],0)
            self.assertTrue(workspace.snapshot(case)['warnings'])

    def test_ongoing_education_is_partial(self):
        d={'person':{'education_zh':'合成大学｜本科在读｜预计2027毕业'},'entries':[]}
        self.assertEqual(assess('必需：本科。',d)[0]['status'],'partial')

    def test_company_size_normalization_and_partial_overlap(self):
        row={'url':'https://www.zhipin.com/job_detail/Ab1234567890.html','company':'合成','title':'运营','description':'维护用户关系','company_size':'1,000—9,999人'}
        self.assertEqual(boss.evaluate_jobs([row],{'company_sizes':['1000-9999']})['results'][0]['status'],'shortlist')
        self.assertEqual(boss.evaluate_jobs([{**row,'company_size':'500-1500人'}],{'company_sizes':['1000-9999']})['results'][0]['status'],'needs_verification')
        self.assertEqual(boss.evaluate_jobs([{**row,'company_size':'大型公司'}],{'company_sizes':['1000-9999']})['results'][0]['status'],'needs_verification')

    def test_title_only_without_keyword_does_not_exclude_unknown_jd(self):
        row={'url':'https://www.zhipin.com/job_detail/Ab1234567890.html','company':'合成','title':'综合助理'}
        self.assertEqual(boss.evaluate_jobs([row],{'keywords':['用户运营']})['results'][0]['status'],'needs_verification')

    def test_composite_degree_does_not_hide_sql_requirement(self):
        d={'person':{'education_zh':'合成大学｜本科'},'entries':[]}
        item=assess('必需：本科且熟练使用 SQL。',d)[0]
        self.assertEqual(item['status'],'partial')
        self.assertTrue(summary([item])['required_blockers'])

    def test_conflicting_event_id_never_counts_as_confirmed_submission(self):
        with tempfile.TemporaryDirectory() as name:
            case=Path(name);(case/'receipt.md').write_text('合成回执')
            start={'event_id':'start','action':'attempt_started','attempt_id':'attempt','job_key':'one','timestamp':'2026-01-01T00:00:00+00:00'}
            submitted={'event_id':'result','action':'attempt_result','attempt_id':'attempt','job_key':'one','timestamp':'2026-01-02T00:00:00+00:00','result':'submitted','source':'user_report','evidence_path':'receipt.md'}
            conflict={**submitted,'result':'not_submitted'}
            (case/'application-events.jsonl').write_text('\n'.join(json.dumps(e) for e in [start,submitted,conflict])+'\n')
            self.assertEqual(workspace.snapshot(case)['stats']['submitted'],0)
            self.assertTrue(workspace.snapshot(case)['warnings'])

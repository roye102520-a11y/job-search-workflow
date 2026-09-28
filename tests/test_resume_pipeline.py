"""End-to-end local-only checks for the shared JD-to-resume generator."""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # The standard-library record tests remain runnable without PDF extras.
    PdfReader = None


CASE_SOURCE = Path(__file__).parent / 'fixtures' / 'synthetic-case'
FIXTURES = Path(__file__).parent / 'fixtures' / 'jd_cases.json'
FONT = Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('resume_pipeline', Path(__file__).parents[1] / 'scripts/resume_pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


@unittest.skipUnless(PdfReader, 'PDF test dependencies are not installed; use requirements.txt or the bundled runtime')
class ResumePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-resume-pipeline-')
        self.case = Path(self.tmp.name) / 'case'
        self.case.mkdir()
        for name in ('career-evidence-bank.md', 'coaching-state.md', 'resume-evidence.json'):
            shutil.copy2(CASE_SOURCE / name, self.case / name)
        self.fixtures = json.loads(FIXTURES.read_text(encoding='utf-8'))
        self.addCleanup(self.tmp.cleanup)

    def generate_request(self, request):
        return pipeline.generate(self.case, request, font=FONT)

    def test_six_realistic_synthetic_jds_route_and_generate_expected_packages(self):
        outputs = {item['id']: self.generate_request(item) for item in self.fixtures}
        for item in self.fixtures:
            output = outputs[item['id']]
            self.assertEqual(output['family'], item['expected_family'])
            self.assertEqual(output['status'], 'preparing')
            self.assertTrue(Path(self.case / output['files']['match']).is_file())
            if item['expected_family']:
                self.assertIn('pdf', output['files'])
                pdf = self.case / output['files']['pdf']
                self.assertEqual(len(PdfReader(pdf).pages), 1)
                self.assertTrue((PdfReader(pdf).pages[0].extract_text() or '').strip())
                for name in ('markdown', 'email', 'review'):
                    self.assertTrue((self.case / output['files'][name]).is_file())
            else:
                self.assertNotIn('pdf', output['files'])

    def test_different_job_families_select_meaningfully_different_evidence(self):
        outputs = {item['id']: self.generate_request(item) for item in self.fixtures[:4]}
        user = set(outputs['S01-user-operations']['selected_bullet_ids'])
        ai = set(outputs['S02-ai-content-operations']['selected_bullet_ids'])
        delivery = set(outputs['S03-implementation-support']['selected_bullet_ids'])
        product = set(outputs['S04-product-operations']['selected_bullet_ids'])
        self.assertIn('support-segmentation', user)
        self.assertIn('lifecycle-support', user)
        self.assertIn('content-structured-documents', ai)
        self.assertIn('content-qa-versioning', ai)
        self.assertIn('lifecycle-support', delivery)
        self.assertIn('catalog-information-architecture', product)
        self.assertEqual(len({frozenset(user), frozenset(ai), frozenset(delivery), frozenset(product)}), 4)

    def test_neutral_chronological_role_keeps_two_sourced_details(self):
        data = pipeline.load_evidence(self.case)
        selected, _ = pipeline.select(data, 'user-operations', 'Customer success operational requests and issue follow-up.')
        atlas = next(entry for entry in selected if entry['id'] == 'work-atlas')
        self.assertEqual({bullet['id'] for bullet in atlas['bullets']}, {
            'content-structured-documents', 'content-qa-versioning'
        })

    def test_jd_only_request_generates_with_explicit_or_placeholder_metadata(self):
        from_labeled_jd = self.generate_request({
            'jd': '公司：合成内容团队\n岗位名称：AI 知识库运营专员\n职责：整理业务文档、维护知识库并完成问答质量检查。任职要求：本科。',
            'language': 'zh', 'family': 'auto'
        })
        self.assertEqual(from_labeled_jd['metadata_resolution']['title'], {
            'value': 'AI 知识库运营专员', 'source': 'jd_label'
        })
        self.assertEqual(from_labeled_jd['metadata_resolution']['company'], {
            'value': '合成内容团队', 'source': 'jd_label'
        })
        self.assertIn('pdf', from_labeled_jd['files'])

        without_labels = self.generate_request({
            'jd': self.fixtures[0]['jd'], 'language': 'zh', 'family': 'auto'
        })
        self.assertEqual(without_labels['metadata_resolution']['title']['source'], 'placeholder')
        self.assertEqual(without_labels['metadata_resolution']['company']['source'], 'placeholder')
        self.assertIn('pdf', without_labels['files'])
        self.assertTrue(any('未填写岗位名称' in warning for warning in without_labels['warnings']))

    def test_unsupported_ml_has_blocking_requirements_and_never_creates_resume(self):
        output = self.generate_request(self.fixtures[4])
        self.assertIsNone(output['family'])
        self.assertNotIn('pdf', output['files'])
        self.assertTrue(output['requirement_summary']['required_blockers'])
        self.assertIn('当前不满足', (self.case / output['files']['match']).read_text(encoding='utf-8'))

    def test_generated_resume_excludes_known_false_claims_and_does_not_repeat_highlight(self):
        output = self.generate_request(self.fixtures[1])
        resume = (self.case / output['files']['markdown']).read_text(encoding='utf-8')
        for claim in ('通过率提升15%', '培训时间缩短30%', '30名真实用户', '生产级模型部署'):
            self.assertNotIn(claim, resume)
        self.assertEqual(resume.count('29 份展览设备手册'), 1)
        self.assertIn('硬门槛检查', (self.case / output['files']['match']).read_text(encoding='utf-8'))

    def test_stale_source_digest_blocks_generation_before_writing_artifacts(self):
        cache = self.case / 'resume-evidence.json'
        data = json.loads(cache.read_text(encoding='utf-8'))
        data['sources'][0]['sha256'] = '0' * 64
        cache.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '事实源已变化'):
            self.generate_request(self.fixtures[0])
        self.assertFalse((self.case / 'generated').exists())

    def test_url_creates_only_a_preparing_manifest_with_explicit_open_checks(self):
        request = dict(self.fixtures[0], url='https://example.test/jobs/123?source=synthetic')
        output = self.generate_request(request)
        manifest = json.loads((self.case / output['files']['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'], 'preparing')
        self.assertEqual(manifest['authorization_scope'], '')
        self.assertTrue(manifest['unresolved_required_fields'])
        self.assertEqual(manifest['role_family'], 'user-operations')

    def test_existing_application_url_does_not_create_a_second_manifest(self):
        existing = self.case / 'applications' / 'existing' / 'manifest.json'
        existing.parent.mkdir(parents=True)
        existing.write_text(json.dumps({'url': 'https://example.test/jobs/123?source=synthetic'}), encoding='utf-8')
        request = dict(self.fixtures[0], url='https://example.test/jobs/123?source=synthetic')
        output = self.generate_request(request)
        self.assertNotIn('manifest', output['files'])
        self.assertTrue(any('已有岗位包' in warning for warning in output['warnings']))

    def test_tracking_parameters_and_query_order_do_not_bypass_url_deduplication(self):
        existing = self.case / 'applications' / 'existing' / 'manifest.json'
        existing.parent.mkdir(parents=True)
        existing.write_text(json.dumps({
            'url': 'https://example.test/jobs/123?requisition=R-42&utm_source=career-site&gclid=first'
        }), encoding='utf-8')
        request = dict(self.fixtures[0], url='https://example.test/jobs/123?fbclid=second&requisition=R-42&utm_medium=email')
        output = self.generate_request(request)
        self.assertNotIn('manifest', output['files'])
        self.assertTrue(any('已有岗位包' in warning for warning in output['warnings']))


if __name__ == '__main__':
    unittest.main()

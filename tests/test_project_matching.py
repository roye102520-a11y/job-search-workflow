"""Project/JD matching tests using only the repository's synthetic candidate."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import project_matching as matching
import resume_pipeline as pipeline
from evidence_selection import decisions


def synthetic_profiles():
    """Capabilities grounded in the synthetic fixture's three project entries."""
    evidence_map = {
        'project-reflection': {
            'product_problem_framing': ['reflection-product-boundaries'],
            'prompt_and_evaluation': ['reflection-offline-evaluation'],
            'product_design': ['reflection-product-boundaries'],
        },
        'project-compass': {
            'knowledge_operations': ['catalog-structured-knowledge'],
            'structured_data': ['catalog-structured-knowledge'],
            'ux_transfer': ['catalog-information-architecture'],
        },
        'project-archive': {
            'source_grounded_knowledge': ['archive-rag-citations'],
            'content_quality': ['archive-learning-path'],
            'learning_path': ['archive-learning-path'],
            'user_needs': ['archive-learning-path'],
        },
    }
    def profile(entry_id, name, capabilities):
        return {
            'id': entry_id,
            'name': name,
            'resume_entry_id': entry_id,
            'resume_selectable': True,
            'candidate_contribution': {'status': 'synthetic_source_checked'},
            'source': 'career-evidence-bank.md#' + entry_id,
            'capabilities': [
                {'id': capability_id, 'strength': strength,
                 'evidence_ids': evidence_map[entry_id].get(capability_id, []), 'terms': terms}
                for capability_id, strength, terms in capabilities
            ],
            'implemented': [],
            'unverified': [],
        }

    return [
        profile('project-reflection', 'Reflection Lab', [
            ('product_problem_framing', 'direct', ['product discovery', 'problem framing', 'user needs']),
            ('prompt_and_evaluation', 'direct', ['prompt design', 'LLM evaluation', 'offline evaluation']),
            ('product_design', 'direct', ['product flow', 'interaction design']),
        ]),
        profile('project-compass', 'Compass Knowledge', [
            ('knowledge_operations', 'direct', ['knowledge base', 'knowledge operations', 'content quality']),
            ('structured_data', 'direct', ['structured content', 'data quality', 'taxonomy']),
            ('ux_transfer', 'direct', ['user needs', 'information architecture']),
        ]),
        profile('project-archive', 'Archive Learning', [
            ('source_grounded_knowledge', 'direct', ['knowledge base', 'source-grounded answers', 'citation quality']),
            ('content_quality', 'direct', ['content quality', 'response evaluation']),
            ('learning_path', 'direct', ['user journey', 'information architecture', 'learning path']),
            ('user_needs', 'transferable', ['user needs', 'problem framing']),
        ]),
    ]


class ProjectMatchingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='project-matching-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name) / 'case'
        shutil.copytree(ROOT / 'tests/fixtures/synthetic-case', self.case)
        self.data = pipeline.load_evidence(self.case)
        self.profiles = synthetic_profiles()

    def request(self, jd, family):
        return {'jd': jd, 'title': '合成岗位', 'company': '合成企业', 'family': family, 'language': 'zh'}

    def test_three_jd_families_produce_different_explainable_projects(self):
        cases = {
            'ai-content-operations': 'Responsibilities: knowledge base operations, content quality, data quality, taxonomy, structured content review.',
            'product-operations': 'Responsibilities: product discovery, problem framing, prompt design, LLM evaluation, product flow and requirements.',
            'ux-research': 'Responsibilities: support user research and research operations, synthesize user needs, map the user journey, review information architecture and improve product flow. Prior interview synthesis and usability testing are preferred.',
        }
        results = {}
        for family, jd in cases.items():
            result = matching.match_projects(self.data, jd, self.profiles, family=family)
            results[family] = result
            self.assertLessEqual(len(result['recommendations']), 3)
            for item in result['recommendations']:
                self.assertTrue(item['evidence'])
                self.assertTrue(item['requirement_map'])
                self.assertTrue(all(entry['source_ref'] for entry in item['evidence']))
        selected_sets = {family: tuple(item['id'] for item in result['recommendations'])
                         for family, result in results.items()}
        self.assertGreater(len(set(selected_sets.values())), 1, selected_sets)
        self.assertEqual(results['ai-content-operations']['recommendations'][0]['id'], 'project-compass')
        self.assertEqual(results['product-operations']['recommendations'][0]['id'], 'project-reflection')
        ux = results['ux-research']
        self.assertTrue(ux['ux_research_boundary'])
        self.assertTrue(any('正式用户访谈' in gap for item in ux['recommendations'] for gap in item['gaps']))
        self.assertTrue(all(not item['direct_evidence'] for item in ux['recommendations']))
        self.assertTrue(all(item['transferable_evidence'] for item in ux['recommendations']))

    def test_one_eligible_project_is_not_padded_to_three(self):
        jd = 'Responsibilities: knowledge base operations, content quality, structured content and taxonomy.'
        one = matching.match_projects(self.data, jd, [self.profiles[1]], family='ai-content-operations')
        self.assertEqual([item['id'] for item in one['recommendations']], ['project-compass'])

    def test_profile_only_repository_match_is_visible_but_locked(self):
        locked = {
            'id': 'private-project-needs-confirmation', 'name': 'Private Project',
            'resume_entry_id': None, 'resume_selectable': False,
            'candidate_contribution': {'status': 'needs_confirmation'},
            'source': 'repository README and core code',
            'capabilities': [{'id': 'workflow_design', 'strength': 'repository_feature_only',
                              'evidence_ids': [], 'terms': ['workflow design']}],
            'implemented': [{'name': 'Workflow editor', 'capability': 'workflow_design'}],
            'unverified': ['个人贡献待确认'],
        }
        result = matching.match_projects(self.data, 'Responsibilities: workflow design.', [locked], family='product-operations')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(result['locked_profile_matches'][0]['id'], locked['id'])
        self.assertFalse(result['locked_profile_matches'][0]['resume_selectable'])

    def test_checked_project_is_included_and_empty_selection_deselects_all(self):
        jd = 'Responsibilities: product discovery, product flow, prompt design, LLM evaluation and problem framing.'
        selected, _, audit = decisions(self.data, 'product-operations', jd,
                                       budget=1800, selected_project_ids=['project-reflection'])
        project_ids = {entry['id'] for entry in selected if entry['kind'] == 'project'}
        self.assertEqual(project_ids, {'project-reflection'})
        self.assertEqual(audit['selected_project_ids'], ['project-reflection'])
        empty, _, empty_audit = decisions(self.data, 'product-operations', jd,
                                          budget=1800, selected_project_ids=[])
        self.assertFalse(any(entry['kind'] == 'project' for entry in empty))
        self.assertTrue(all(not row['selected'] for row in empty_audit['candidates'] if row['kind'] == 'project'))

    def test_manual_selection_rejects_unknown_or_unconfirmed_project(self):
        jd = 'Responsibilities: product discovery, problem framing and product flow.'
        with self.assertRaisesRegex(ValueError, '不重复的项目 ID'):
            decisions(self.data, 'product-operations', jd, selected_project_ids=['missing-project'])
        data = copy.deepcopy(self.data)
        data['unconfirmed'].append({'field': 'projects.start_date_conflict'})
        with self.assertRaisesRegex(ValueError, '待确认、冲突'):
            decisions(data, 'product-operations', jd, selected_project_ids=['project-reflection'])

    def test_profile_sources_are_required_and_stale_profiles_are_not_used(self):
        source_paths = ['career-evidence-bank.md', 'resume-evidence.json']
        payload = {'schema_version': 1,
                   'source_digests': {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest()
                                      for name in source_paths},
                   'profiles': self.profiles}
        profile_path = self.case / 'project-capability-profiles.json'
        profile_path.write_text(json.dumps(payload), encoding='utf-8')
        loaded, warnings = matching.load_project_profiles(self.case)
        self.assertEqual(len(loaded), 3)
        self.assertFalse(warnings)
        before = matching.profile_digest(self.case)
        payload['profiles'][0]['name'] = 'Updated Synthetic Project'
        profile_path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertNotEqual(before, matching.profile_digest(self.case))
        (self.case / 'career-evidence-bank.md').write_text('changed source', encoding='utf-8')
        loaded, warnings = matching.load_project_profiles(self.case)
        self.assertEqual(loaded, [])
        self.assertTrue(any('career-evidence-bank.md' in warning for warning in warnings))

    def test_pipeline_preview_defaults_to_recommendations_then_respects_manual_choice(self):
        payload = {'schema_version': 1,
                   'source_digests': {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest()
                                      for name in ['career-evidence-bank.md', 'resume-evidence.json']},
                   'profiles': self.profiles}
        (self.case / 'project-capability-profiles.json').write_text(json.dumps(payload), encoding='utf-8')
        jd = 'Responsibilities: knowledge base operations, content quality, structured content and taxonomy.'
        automatic = pipeline.preview_selection(self.case, self.request(jd, 'ai-content-operations'))
        expected = automatic['project_matching']['default_selected_ids']
        self.assertTrue(expected)
        self.assertEqual(automatic['project_matching']['selected_project_ids'], expected)
        manual = pipeline.preview_selection(self.case, {**self.request(jd, 'ai-content-operations'),
                                                        'selected_project_ids': ['project-archive']})
        selected_projects = {row['entry_id'] for row in manual['selection']['candidates']
                             if row['kind'] == 'project' and row['selected']}
        self.assertEqual(selected_projects, {'project-archive'})


if __name__ == '__main__':
    unittest.main()

"""Synthetic tests for conservative JD requirement classification."""
import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('jd_requirements', Path(__file__).parents[1] / 'scripts/jd_requirements.py')
requirements = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requirements)


EVIDENCE = {
    'person': {'education_zh': '某大学｜商务英语｜本科｜2019.09–2023.06', 'education_en': 'Business English, undergraduate education'},
    'entries': [
        {'kind': 'work', 'dates': '2024.06–2025.05', 'employment_zh': '全职', 'tags': ['user-operations', 'implementation-support'], 'bullets': [
            {'id': 'user-1', 'zh': '管理用户生命周期并制作操作指南。', 'en': '', 'keywords': [], 'tags': ['user-operations', 'implementation-support']}]},
        {'kind': 'work', 'dates': '2025.06–2025.12', 'employment_zh': '全职', 'tags': ['user-operations'], 'bullets': [
            {'id': 'user-2', 'zh': '为用户制定服务计划。', 'en': '', 'keywords': [], 'tags': ['user-operations']}]},
        {'kind': 'work', 'dates': '2024.03–2025.06', 'employment_zh': '兼职', 'tags': ['ai-content-operations'], 'bullets': [
            {'id': 'ai-1', 'zh': '清洗结构化文档，建立知识库。', 'en': '', 'keywords': ['OCR', 'RAG'], 'tags': ['ai-content-operations']}]},
        {'kind': 'project', 'dates': '2026.01–至今', 'employment_zh': '个人项目', 'tags': ['product-operations'], 'bullets': [
            {'id': 'product-1', 'zh': '设计用户路径并交付可交互方案。', 'en': '', 'keywords': [], 'tags': ['product-operations']}]},
    ]}


class RequirementTests(unittest.TestCase):
    def by_text(self, jd):
        return {item['text']: item for item in requirements.assess(jd, EVIDENCE)}

    def test_known_degree_and_user_experience_supported_without_double_count(self):
        items = self.by_text('必需：本科，至少1年用户服务或运营经验。')
        self.assertEqual(items['本科']['status'], 'supported')
        experience = next(item for text, item in items.items() if '用户服务' in text)
        self.assertEqual(experience['status'], 'supported')
        self.assertIn('19 个月', experience['reason'])

    def test_preferred_sql_is_not_promoted_to_required(self):
        items = self.by_text('必需：本科；加分：SQL、OCR、Prompt 或 RAG 应用实践。')
        sql = next(item for text, item in items.items() if 'SQL' in text)
        self.assertEqual(sql['level'], 'preferred')
        self.assertEqual(sql['status'], 'unknown')
        self.assertTrue(requirements.summary(list(items.values()))['ready_for_human_review'])

    def test_content_organization_and_document_management_use_direct_evidence(self):
        items = requirements.assess('任职要求：有内容整理和文档管理经验。', EVIDENCE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['level'], 'required')
        self.assertEqual(items[0]['status'], 'supported')
        self.assertIn('ai-1', items[0]['evidence_refs'])

    def test_masters_and_ml_training_are_documented_not_met(self):
        items = self.by_text('硬性要求：计算机或机器学习相关硕士或博士，5年以上全职机器学习工程经验，独立负责分布式模型训练与PyTorch训练框架。')
        statuses = {item['status'] for item in items.values()}
        self.assertIn('not_met', statuses)
        summary = requirements.summary(list(items.values()))
        self.assertFalse(summary['ready_for_human_review'])
        self.assertTrue(summary['required_blockers'])

    def test_negative_requirement_is_excluded(self):
        items = requirements.assess('岗位不要求 SQL 或 ERP；工作重点不是知识库内容运营；必需：本科。', EVIDENCE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['status'], 'supported')

    def test_unknown_work_permission_and_travel_stay_unknown(self):
        items = requirements.assess('必需：能够接受每月出差；具备工作许可。', EVIDENCE)
        self.assertTrue(items)
        self.assertTrue(all(item['status'] == 'unknown' for item in items))

    def test_english_comma_list_stays_one_experience_requirement(self):
        items = requirements.assess('Required: at least 2 years of customer success, operations, or technical account management experience.', EVIDENCE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['level'], 'required')
        self.assertEqual(items[0]['status'], 'not_met')
        self.assertIn('19 个月', items[0]['reason'])


if __name__ == '__main__':
    unittest.main()

"""Evidence-backed career positioning for the local Career Studio case.

The first version is deliberately deterministic: it reads the validated local
evidence cache and private search preferences, cites source bullets, and never
sends candidate data to an external model.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from career_workspace import read_json
from evidence_quality import exclusion_reason, usable_entries
from resume_pipeline import load_evidence


ROLE_PROFILES = [
    {
        'id': 'ai-operations-knowledge-content', 'default_priority': 'P0',
        'preference_labels': ['AI Operations', 'AI Content Quality / Operations', 'AI Knowledge Operations', 'Data Quality / Operations'],
        'title_zh': 'AI 运营 / AI 内容与知识库运营助理',
        'title_en': 'AI Operations / AI Content & Knowledge Operations Associate',
        'direct_tags': ['ai-content-operations'], 'transfer_tags': [],
        'terms': ['知识库', '问答对', '内容复核', '结构化', '数据清洗', '文档', 'knowledge base', 'question-answer', 'content review', 'structured content', 'data cleaning'],
        'why_direct': '事实库中有与内容、数据或知识流程相关的直接工作职责。',
        'why_transfer': '现有证据来自相邻运营或实施职责，可迁移到 AI 内容与知识流程；不等同于正式 AI 岗位经历。',
        'why_empty': '当前没有可安全引用的直接或相邻经历证据，需先复核事实库。',
        'gaps': ['补充可复现的内容质量标准、抽样复核方法和错误分类案例。', '按 JD 核实 Excel/SQL、双语内容审校及数据来源治理要求。'],
        'difficulty': '中：有 AI 内容与数据整理的直接工作经历；外企岗位仍需核实英语工作要求和质量指标经验。',
    },
    {
        'id': 'llm-evaluation-ai-quality', 'default_priority': 'P0',
        'preference_labels': ['LLM Evaluation / AI Quality'],
        'title_zh': 'LLM 评测 / AI 质量分析专员（初级）',
        'title_en': 'Junior LLM Evaluation / AI Quality Analyst',
        'direct_tags': [], 'transfer_tags': ['ai-content-operations', 'product-operations'],
        'terms': ['离线评测', '评测', '测试', '质量检查', '输出质量', '失败场景', 'offline evaluation', 'evaluation', 'quality assurance', 'output quality', 'test cases'],
        'why_direct': '事实库中有直接的评测或质量分析工作证据。',
        'why_transfer': '当前可引用的相邻内容质量、资料核验或运营经历可迁移；个人项目证据仅在日期与贡献冲突复核后再纳入。',
        'why_empty': '当前没有可安全引用的评测或相邻质量证据；不能将其表述为已具备正式 LLM 评测经历。',
        'gaps': ['把评测集整理成可复现说明，明确场景覆盖、判分标准、边界和局限。', '补齐标注一致性、评测指标、抽样统计及 SQL/表格分析证据；不表述为机器学习工程能力。'],
        'difficulty': '中高：相邻内容质量与资料核验经历可迁移；个人项目日期和贡献待复核，尚缺正式评测岗位经历及可验证的评测指标。',
    },
    {
        'id': 'product-operations-assistant', 'default_priority': 'P1',
        'preference_labels': ['Product Operations / Assistant'],
        'title_zh': '产品运营专员 / 产品助理',
        'title_en': 'Product Operations Associate / Product Assistant',
        'direct_tags': ['product-operations'], 'transfer_tags': [],
        'terms': ['用户反馈', '需求', '问题归类', '流程图', '操作指南', '产品边界', 'user feedback', 'requirements', 'issue tracking', 'user journey', 'product scope'],
        'why_direct': '事实库中有与产品运营或产品助理职责直接相关的工作证据。',
        'why_transfer': '用户服务、流程跟进或内容运营中的相邻工作证据可迁移；个人项目的贡献与日期待复核后再纳入。',
        'why_empty': '当前没有可安全引用的产品运营或相邻经历证据，需先复核事实库。',
        'gaps': ['补充一个从需求优先级到验收结果的完整案例，并区分个人项目与正式商业产品。', '按岗位要求补充产品指标、实验分析、SQL 或 B2B SaaS 流程证据。'],
        'difficulty': '中：用户运营证据强、产品实践可迁移；正式产品岗位年限和商业化结果仍是主要差距。',
    },
    {
        'id': 'ai-saas-customer-success-implementation', 'default_priority': 'P1',
        'preference_labels': ['AI SaaS Customer Success / Junior Digital Operations'],
        'title_zh': 'AI SaaS 客户成功专员 / 实施支持专员',
        'title_en': 'AI SaaS Customer Success Associate / Implementation Support Associate',
        'direct_tags': [], 'transfer_tags': ['user-operations', 'implementation-support'],
        'terms': ['用户生命周期', '用户服务', '跨团队', '需求沟通', '操作指南', '问题跟进', 'customer lifecycle', 'customer service', 'stakeholder coordination', 'implementation support', 'documentation'],
        'why_direct': '事实库中有与用户服务或实施支持直接相关的工作证据。',
        'why_transfer': '用户沟通、流程跟进或操作资料等相邻职责可迁移到初级 SaaS 支持；不等同于企业 SaaS 上线经验。',
        'why_empty': '当前没有可安全引用的客户支持或实施相关经历证据。',
        'gaps': ['核实岗位是否偏售前销售、续约指标或高级客户组合管理，避免把服务经历夸大为 B2B 客户成功。', '按 JD 补充 SaaS 上线流程、CRM、API/数据导入及客户培训工具经验。'],
        'difficulty': '中：服务与协作是直接证据；企业 SaaS、技术实施和续约指标经验需要逐岗核实。',
    },
    {
        'id': 'ux-research-assistant-operations', 'default_priority': 'P2',
        'preference_labels': ['UX Research / Research Operations'],
        'title_zh': '用户研究助理 / 研究运营协调员',
        'title_en': 'UX Research Assistant / Research Operations Coordinator',
        'direct_tags': [], 'transfer_tags': ['user-operations', 'product-operations'],
        'terms': ['用户反馈', '高频问题', '用户体验', '参与者问题', 'feedback analysis', 'participant questions', 'user experience', 'usability', 'research operations'],
        'why_direct': '事实库中有直接的用户研究或研究运营工作证据。',
        'why_transfer': '用户问题记录、反馈归类或流程文档等相邻职责可迁移到研究支持；不能据此声称做过正式用户研究。',
        'why_empty': '当前没有可安全引用的研究或相邻用户反馈证据。',
        'gaps': ['补齐访谈/可用性测试提纲、样本记录、主题编码和洞察报告等研究方法作品。', '目前没有确认的正式用户研究项目或真实用户研究结果，不能将产品自测称为用户研究。'],
        'difficulty': '中高：有用户问题和反馈处理经验，但正式研究方法、研究交付物和研究项目证据较少。',
    },
]

PRIORITY_ORDER = {'P0': 0, 'P1': 1, 'P2': 2}


def _priority(profile, preferences):
    strategy = preferences.get('job_search_strategy', {}) if isinstance(preferences, dict) else {}
    directions = strategy.get('target_directions', []) if isinstance(strategy, dict) else []
    labels = {str(x).strip().casefold() for x in profile['preference_labels']}
    for direction in directions if isinstance(directions, list) else []:
        if isinstance(direction, dict) and str(direction.get('label', '')).strip().casefold() in labels:
            value = direction.get('priority')
            return value if value in PRIORITY_ORDER else profile['default_priority']
    return profile['default_priority']


def build_report(case):
    case = Path(case).resolve()
    evidence = load_evidence(case)
    entries = usable_entries(evidence)
    preferences = read_json(case, 'search-preferences.json', {})
    if not isinstance(preferences, dict):
        preferences = {}

    ranked = []
    for profile in ROLE_PROFILES:
        facts = []
        work_entries, project_entries = set(), set()
        for entry in entries:
            for bullet in entry.get('bullets', []):
                bullet_tags = set(bullet.get('tags', []))
                text = ' '.join([bullet.get('zh', ''), bullet.get('en', ''), *bullet.get('keywords', [])]).casefold()
                direct = bool(bullet_tags.intersection(profile['direct_tags']))
                transferable = bool(bullet_tags.intersection(profile['transfer_tags']))
                term_hit = any(term.casefold() in text for term in profile['terms'])
                if not (direct or transferable or term_hit):
                    continue
                relationship = 'direct_work_evidence' if entry.get('kind') == 'work' and direct else 'transferable_evidence'
                facts.append({
                    'entry_id': entry['id'], 'entry_title': entry['title_zh'],
                    'kind': entry['kind'], 'bullet_id': bullet['id'],
                    'source_ref': entry['source_ref'], 'relationship': relationship,
                    'excerpt': bullet['zh'],
                })
                (work_entries if entry.get('kind') == 'work' else project_entries).add(entry['id'])
        facts.sort(key=lambda item: (item['kind'] != 'work', item['entry_title'], item['bullet_id']))
        priority = _priority(profile, preferences)
        direct_count = sum(item['relationship'] == 'direct_work_evidence' for item in facts)
        transferable_count = len(facts) - direct_count
        strength = ('strong' if direct_count >= 3 and len(work_entries) >= 2 else
                    'moderate' if work_entries else 'project_evidence_only' if project_entries else 'limited')
        why = (profile['why_direct'] if direct_count else
               profile['why_transfer'] if transferable_count else profile['why_empty'])
        ranked.append({
            'id': profile['id'], 'priority': priority,
            'title_zh': profile['title_zh'], 'title_en': profile['title_en'],
            'why': why, 'evidence_strength': strength,
            'direct_work_evidence_count': direct_count,
            'transferable_evidence_count': transferable_count,
            'evidence': facts[:8], 'gaps': profile['gaps'],
            'difficulty': profile['difficulty'],
            '_rank': (PRIORITY_ORDER[priority], -direct_count, -transferable_count,
                      -len(project_entries), profile['id']),
        })
    ranked.sort(key=lambda item: item['_rank'])
    for item in ranked:
        item.pop('_rank', None)
    withheld_projects = [entry['id'] for entry in evidence.get('entries', [])
                        if entry.get('kind') == 'project' and exclusion_reason(evidence, entry)]
    return {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'method': 'validated_local_evidence_and_private_preferences',
        'model_disclosure': '本报告由本地证据规则生成；未向外部模型发送候选人资料。',
        'evidence_sources': evidence['sources'],
        'roles': ranked[:5],
        'withheld_project_count': len(withheld_projects),
        'withheld_project_note': ('有 ' + str(len(withheld_projects)) +
                                  ' 个个人项目因待确认事实或日期冲突未计入本次定位；确认后可重新生成。'
                                  if withheld_projects else ''),
        'limitations': ['难度是根据当前证据缺口作出的求职判断，不是录用概率。',
                        '正式投递前仍需逐条核对职位要求、毕业资格、地点、薪资和工作许可。'],
    }


def render_markdown(report):
    lines = ['# AI 职业定位（本地证据版）', '',
             '生成时间：' + report['as_of'], '', report['model_disclosure'], '',
             '难度是证据差距判断，不是录用概率。', '']
    for index, role in enumerate(report['roles'], 1):
        lines.extend([f"## {index}. {role['title_zh']} / {role['title_en']}", '',
                      f"优先级：{role['priority']}；证据强度：{role['evidence_strength']}；难度：{role['difficulty']}", '',
                      '适合原因：' + role['why'], '', '经历证据：'])
        lines.extend('- ' + fact['excerpt'] + '（' + fact['source_ref'] + ' · ' + fact['bullet_id'] + '）' for fact in role['evidence'])
        lines.extend(['', '当前缺口：'])
        lines.extend('- ' + gap for gap in role['gaps'])
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--format', choices=('json', 'markdown'), default='markdown')
    args = parser.parse_args()
    result = build_report(args.case)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == 'json' else render_markdown(result))


if __name__ == '__main__':
    main()

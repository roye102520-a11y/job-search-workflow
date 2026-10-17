"""Explainable JD-to-project matching using sourced project profiles.

Repository features are kept separate from candidate evidence. This module
orders relevant evidence; it never estimates hiring probability.
"""
import hashlib
import json
from pathlib import Path

from evidence_quality import exclusion_reason, positive_clauses


FORMAL_RESEARCH_TERMS = (
    'user research', 'ux research', '用户研究', '用户访谈', '深度访谈', 'usability test',
    '可用性测试', '研究招募', '招募参与者', 'research participant', 'research plan',
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile_digest(case):
    """Digest the private matching profile so edits invalidate material reuse."""
    path = Path(case).resolve() / 'project-capability-profiles.json'
    return _sha(path) if path.is_file() else None


def load_project_profiles(case):
    """Return private, source-fresh profiles; stale profiles are not used."""
    path = Path(case).resolve() / 'project-capability-profiles.json'
    if not path.is_file():
        return [], ['未找到项目能力档案；仅使用事实库中可追溯的项目证据。']
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return [], ['项目能力档案无法读取；为避免使用过期内容，本次不使用该档案。']
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or not isinstance(payload.get('profiles'), list):
        return [], ['项目能力档案格式不兼容；本次不使用该档案。']
    source_digests = payload.get('source_digests')
    if not isinstance(source_digests, dict) or not source_digests:
        return [], ['项目能力档案缺少来源摘要；为避免使用无来源描述，本次不使用该档案。']
    stale = []
    for rel, expected in source_digests.items():
        if not isinstance(rel, str) or not isinstance(expected, str):
            stale.append('来源摘要格式错误')
            continue
        source = (Path(case).resolve() / rel).resolve()
        if not source.is_relative_to(Path(case).resolve()) or not source.is_file() or _sha(source) != expected:
            stale.append(rel)
    if stale:
        return [], ['项目能力档案来源已变化（' + '、'.join(stale) + '）；请先复核档案，不使用旧描述。']
    profiles = [p for p in payload['profiles'] if isinstance(p, dict) and isinstance(p.get('id'), str)]
    return profiles, []


def _candidate_evidence(profile, data, entries, capability_ids=None):
    """Resolve profile evidence IDs to safe, source-linked facts.

    Entry IDs remain supported for compatibility with early profile drafts;
    bullet IDs give a narrower, more auditable requirement-to-fact mapping.
    """
    if not profile.get('resume_selectable'):
        return []
    allowed_entry = profile.get('resume_entry_id')
    selected = {}
    for capability in profile.get('capabilities', []):
        if capability.get('strength') == 'repository_feature_only':
            continue
        capability_id = capability.get('id', '')
        if capability_ids is not None and capability_id not in capability_ids:
            continue
        for evidence_id in capability.get('evidence_ids', []):
            if not isinstance(evidence_id, str):
                continue
            if evidence_id in entries:
                entry = entries[evidence_id]
                if entry.get('kind') != 'project' or (allowed_entry and evidence_id != allowed_entry):
                    continue
                bullets = entry.get('bullets', [])
            else:
                entry = entries.get(allowed_entry)
                if not entry or entry.get('kind') != 'project':
                    continue
                bullets = [bullet for bullet in entry.get('bullets', []) if bullet.get('id') == evidence_id]
            if exclusion_reason(data, entry):
                continue
            for bullet in bullets:
                if bullet.get('id') != evidence_id and evidence_id not in entries:
                    continue
                if exclusion_reason(data, entry, bullet):
                    continue
                item = selected.setdefault(bullet.get('id'), {
                    'id': bullet.get('id'), 'entry_id': entry['id'], 'text': bullet.get('zh', ''),
                    'source_ref': entry.get('source_ref', ''),
                    'title': entry.get('title_zh', profile.get('name', '项目')), 'capability_ids': []})
                if capability_id and capability_id not in item['capability_ids']:
                    item['capability_ids'].append(capability_id)
    return list(selected.values())


def fallback_profiles(data):
    """Build a narrow project index from cached, sourced facts when no profile exists."""
    profiles = []
    for entry in data.get('entries', []):
        if not isinstance(entry, dict) or entry.get('kind') != 'project':
            continue
        terms = list(dict.fromkeys(
            keyword for bullet in entry.get('bullets', [])
            for keyword in bullet.get('keywords', []) if isinstance(keyword, str) and keyword
        ))
        profiles.append({'id': entry['id'], 'name': entry.get('title_zh', entry['id']),
                         'source': entry.get('source_ref', ''), 'resume_entry_id': entry['id'],
                         'resume_selectable': True,
                         'candidate_contribution': {'status': 'source_facts_only'},
                         'capabilities': [{'id': 'source_facts', 'strength': 'direct',
                                           'evidence_ids': [entry['id']], 'terms': terms}],
                         'implemented': []})
    return profiles


def match_projects(data, jd, profiles=None, profile_warnings=None, family=None):
    """Recommend up to three projects; zero or one is valid when evidence is thin."""
    profiles = profiles or []
    profile_warnings = profile_warnings or []
    clauses = positive_clauses(jd)
    body = ' '.join(clauses).lower()
    entries = {entry.get('id'): entry for entry in data.get('entries', []) if isinstance(entry, dict)}
    formal_research_requested = any(term in body for term in FORMAL_RESEARCH_TERMS)
    candidates = []
    for profile in profiles:
        matched, direct, transferable, profile_only = [], [], [], []
        matched_terms = []
        score = 0
        for capability in profile.get('capabilities', []):
            terms = [term for term in capability.get('terms', []) if isinstance(term, str) and term]
            hits = [term for term in terms if term.lower() in body]
            if not hits:
                continue
            strength = capability.get('strength', 'transferable')
            record = {'id': capability.get('id', ''), 'strength': strength, 'matched_terms': hits,
                      'evidence_ids': capability.get('evidence_ids', [])}
            matched.append(record)
            matched_terms.extend(hits)
            if strength == 'repository_feature_only':
                profile_only.append(record)
                score += 1
            elif strength == 'direct':
                # Product-design work is transferable to UX research, never proof
                # of interviews, participant recruitment, or formal user studies.
                if family == 'ux-research':
                    record['strength'] = 'transferable'
                    transferable.append(record)
                    score += min(3, len(set(hits)))
                else:
                    direct.append(record)
                    score += min(5, 3 + max(0, len(set(hits)) - 1))
            else:
                transferable.append(record)
                score += min(3, len(set(hits)))
        matched_capability_ids = {m['id'] for m in matched}
        available_evidence = _candidate_evidence(profile, data, entries)
        evidence = _candidate_evidence(profile, data, entries, matched_capability_ids)
        if profile_only:
            # A repository feature without a confirmed personal contribution is
            # visible as potential fit, but cannot make the project CV-selectable.
            direct = [item for item in direct if item['strength'] != 'repository_feature_only']
            transferable = [item for item in transferable if item['strength'] != 'repository_feature_only']
        usable_ids = {value for item in available_evidence for value in (item['entry_id'], item['id'])}
        direct = [item for item in direct if item['evidence_ids'] and set(item['evidence_ids']) & usable_ids]
        transferable = [item for item in transferable if item['evidence_ids'] and set(item['evidence_ids']) & usable_ids]
        eligible = bool(profile.get('resume_selectable') and profile.get('resume_entry_id') in usable_ids and available_evidence)
        threshold = bool(direct or len(transferable) >= 2)
        recommended = bool(eligible and score >= 3 and threshold)
        feature_matches = [feature for feature in profile.get('implemented', [])
                           if isinstance(feature, dict) and feature.get('capability') in matched_capability_ids]
        maps = []
        for clause in clauses:
            clause_matches = [m for m in matched if any(t.lower() in clause.lower() for t in m['matched_terms'])]
            if clause_matches:
                evidence_ids = list(dict.fromkeys(eid for item in clause_matches for eid in item['evidence_ids']))
                maps.append({'requirement': clause[:240], 'capabilities': [m['id'] for m in clause_matches],
                             'evidence_ids': evidence_ids,
                             'source_refs': list(dict.fromkeys(e['source_ref'] for e in evidence
                                                               if e['id'] in evidence_ids or e['entry_id'] in evidence_ids))})
            if len(maps) >= 8:
                break
        gaps = list(profile.get('unverified', []))
        if formal_research_requested and family == 'ux-research':
            gaps.append('个人产品设计和离线评测只作为可迁移证据；目前没有已确认的正式用户访谈、招募或可用性研究记录。')
        if not direct and not transferable:
            gaps.append('本 JD 暂无可确认的候选人项目证据；仓库功能不能替代个人贡献证明。')
        reasons = []
        if direct:
            reasons.append('有直接项目事实对应：' + '、'.join(dict.fromkeys(m['id'] for m in direct)))
        if transferable:
            reasons.append('有可迁移能力对应：' + '、'.join(dict.fromkeys(m['id'] for m in transferable)))
        if profile_only:
            reasons.append('仓库功能与 JD 相关，但个人贡献待确认，不能进入简历')
        if not reasons:
            reasons.append('当前 JD 与已记录项目能力的直接关联不足')
        if not eligible:
            reasons.append('没有可用且贡献已记录的简历事实条目')
        candidates.append({'id': profile['id'], 'name': profile.get('name', profile['id']),
                           'repository': profile.get('repository', ''), 'status': profile.get('status', ''),
                           'score': score, 'recommended': recommended,
                           'resume_entry_id': profile.get('resume_entry_id'), 'resume_selectable': eligible,
                           'contribution_status': (profile.get('candidate_contribution') or {}).get('status', 'unknown'),
                           'matched_capabilities': matched, 'direct_evidence': direct,
                           'transferable_evidence': transferable, 'repository_feature_fit': profile_only,
                           'implemented_matches': feature_matches, 'requirement_map': maps,
                           'evidence': evidence, 'available_evidence': available_evidence,
                           'gaps': list(dict.fromkeys(gaps)),
                           'why': reasons, 'source': profile.get('source', '')})
    candidates.sort(key=lambda item: (-item['score'], item['name'].lower()))
    recommended = [item for item in candidates if item['recommended']][:3]
    locked = [item for item in candidates if item['score'] > 0 and not item['resume_selectable']]
    return {'policy_version': 1, 'score_type': '规则排序分，非录用概率',
            'ux_research_boundary': ('个人产品设计只映射为可迁移能力，不表示正式用户研究经验。' if family == 'ux-research' else ''),
            'profile_warnings': profile_warnings, 'recommendations': recommended,
            'locked_profile_matches': locked, 'candidates': candidates,
            'default_selected_ids': [item['resume_entry_id'] for item in recommended if item['resume_entry_id']],
            'candidate_count': len(recommended)}

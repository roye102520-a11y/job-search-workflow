"""Explainable budget-based selection, never changes the source evidence."""
import re
from evidence_quality import exclusion_reason, positive_clauses


def decisions(data, family, jd, priorities=None, budget=900):
    priorities = priorities or []
    ids = {e['id'] for e in data['entries']}
    if not isinstance(priorities, list) or len(priorities) != len(set(priorities)) or any(not isinstance(i, str) or i not in ids for i in priorities):
        raise ValueError('项目优先级必须是当前事实库中不重复的经历 ID 列表')
    if type(budget) is not int or not 300 <= budget <= 1800:
        raise ValueError('选材篇幅应为 300–1800 字符')
    body = ' '.join(positive_clauses(jd)).lower()
    ranked, candidates = [], []
    for entry in data['entries']:
        for bullet in entry['bullets']:
            denied = exclusion_reason(data, entry, bullet)
            hits = list(dict.fromkeys(k for k in bullet['keywords'] if k.lower() in body))
            text = bullet['zh']
            dims = {
                'jd_relevance': min(12, len(hits) * 3) + (2 if family in bullet['tags'] else 0),
                'evidence_strength': 3 if entry.get('source_ref') else 0,
                'contribution_clarity': 2 if re.search(r'本人|独立|协助|设计|整理|协调|维护|核对|搭建', text) else 0,
                'verifiability': 2 if re.search(r'\d|原始|原型|工单|记录|来源|样本|页面|指南|文档', text) else 0,
                'historical_accuracy': 0 if denied else 2,
                'user_priority': (len(priorities) - priorities.index(entry['id'])) * 20 if entry['id'] in priorities else 0,
                'redundancy_penalty': 0,
            }
            # Legacy family priorities are at most a tiebreaker, not a project cap.
            score = sum(dims.values()) + max(-2, min(2, entry.get('family_priorities', {}).get(family, 0)))
            record = {'id': bullet['id'], 'entry_id': entry['id'], 'title': entry['title_zh'], 'kind': entry['kind'],
                      'source_ref': entry['source_ref'], 'original': text, 'wording': text,
                      'dimensions': dims, 'score': score, 'keyword_hits': hits, 'selected': False,
                      'reason': denied, 'rewrite_reason': '使用已保存的来源表述；只调整选材与顺序，原始事实不改写。',
                      'confirmation': bullet.get('confirmation_status', 'legacy_source_checked')}
            candidates.append(record)
            if not denied:
                ranked.append((entry, bullet, record))
    ranked.sort(key=lambda pair: (-pair[2]['score'], pair[1]['id']))
    chosen, used, tokens = set(), 0, []
    # Preserve employment history with one safe detail per role, then allocate by merit.
    chronological = sorted([e for e in data['entries'] if e['kind'] == 'work'], key=lambda e: e['dates'], reverse=True)
    for entry in chronological:
        available = [p for p in ranked if p[0]['id'] == entry['id']]
        if available:
            best = available[0]; chosen.add(best[1]['id']); used += len(best[1]['zh']) + 35
    for entry, bullet, record in ranked:
        if bullet['id'] in chosen:
            continue
        text_tokens = set(re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,4}', bullet['zh']))
        redundant = any(len(text_tokens & prior) / max(1, len(text_tokens | prior)) > .72 for prior in tokens)
        if redundant:
            record['dimensions']['redundancy_penalty'] = -8
            record['reason'] = '与已选事实表达高度重复；优先保留信息更完整的条目'
            continue
        cost = len(bullet['zh']) + (35 if entry['id'] not in {p[0]['id'] for p in ranked if p[1]['id'] in chosen} else 8)
        # No arbitrary number of projects/bullets. Unrelated projects stay visible in audit.
        relevant = record['dimensions']['jd_relevance'] > 0 or record['dimensions']['user_priority'] > 0
        if entry['kind'] == 'project' and not relevant:
            record['reason'] = '与此 JD 的直接词项关联不足，可手动提高项目优先级'
        elif used + cost > budget:
            record['reason'] = '超过当前篇幅预算；可提高项目优先级或调整篇幅'
        else:
            chosen.add(bullet['id']); used += cost; tokens.append(text_tokens)
    selected = []
    for entry in data['entries']:
        bullets = [p[1] for p in ranked if p[0]['id'] == entry['id'] and p[1]['id'] in chosen]
        if bullets:
            selected.append({**entry, 'bullets': bullets, 'score': max(p[2]['score'] for p in ranked if p[0]['id'] == entry['id'])})
    selected = sorted([e for e in selected if e['kind'] == 'work'], key=lambda e: e['dates'], reverse=True) + sorted([e for e in selected if e['kind'] == 'project'], key=lambda e: (-e['score'], e['id']))
    for record in candidates:
        record['selected'] = record['id'] in chosen
        if record['selected']:
            record['reason'] = '保留工作时间线' if record['kind'] == 'work' and not record['keyword_hits'] else '与 JD 相关且来源可追溯，纳入当前篇幅'
        elif not record['reason']:
            record['reason'] = '优先保留与此岗位更相关的证据'
    # Highlights compete for a separate text budget; at most one from each entry.
    highlights, size = [], 0
    for entry, bullet, record in ranked:
        if bullet['id'] not in chosen or entry['id'] in {e['id'] for e, _ in highlights}:
            continue
        if size + len(bullet['zh']) > 145:
            continue
        highlights.append((entry, bullet)); size += len(bullet['zh'])
    return selected, highlights, {'policy_version': 2, 'budget': budget, 'estimated_used': used,
                                   'priorities': priorities, 'candidates': candidates}

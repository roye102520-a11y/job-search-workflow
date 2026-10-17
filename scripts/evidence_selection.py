"""Explainable budget-based selection, never changes the source evidence."""
import re
from evidence_quality import exclusion_reason, positive_clauses


def decisions(data, family, jd, priorities=None, budget=900, selected_project_ids=None):
    priorities = priorities or []
    ids = {e['id'] for e in data['entries']}
    if not isinstance(priorities, list) or len(priorities) != len(set(priorities)) or any(not isinstance(i, str) or i not in ids for i in priorities):
        raise ValueError('项目优先级必须是当前事实库中不重复的经历 ID 列表')
    if type(budget) is not int or not 300 <= budget <= 1800:
        raise ValueError('选材篇幅应为 300–1800 字符')
    project_entries = {e['id']: e for e in data['entries'] if e.get('kind') == 'project'}
    if selected_project_ids is not None:
        if (not isinstance(selected_project_ids, list) or
                any(not isinstance(value, str) for value in selected_project_ids) or
                len(selected_project_ids) != len(set(selected_project_ids)) or
                any(value not in project_entries for value in selected_project_ids)):
            raise ValueError('本版项目选择必须是事实库中不重复的项目 ID 列表')
        usable_projects = {
            entry_id for entry_id, entry in project_entries.items()
            if not exclusion_reason(data, entry) and any(not exclusion_reason(data, entry, bullet)
                                                        for bullet in entry.get('bullets', []))
        }
        if any(value not in usable_projects for value in selected_project_ids):
            raise ValueError('所选项目包含待确认、冲突或当前不可使用的事实')
    body = ' '.join(positive_clauses(jd)).lower()
    ranked_priorities = list(priorities)
    if selected_project_ids is not None:
        ranked_priorities.extend(value for value in selected_project_ids if value not in ranked_priorities)
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
                'user_priority': (len(ranked_priorities) - ranked_priorities.index(entry['id'])) * 20 if entry['id'] in ranked_priorities else 0,
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
                if (selected_project_ids is not None and entry.get('kind') == 'project'
                        and entry['id'] not in selected_project_ids):
                    record['reason'] = '本次未手动选入简历；原始项目事实仍保留在候选列表'
                    continue
                ranked.append((entry, bullet, record))
    ranked.sort(key=lambda pair: (-pair[2]['score'], pair[1]['id']))
    chosen, used, tokens = set(), 0, []
    # Preserve employment history with one safe detail per role, then allocate by merit.
    chronological = sorted([e for e in data['entries'] if e['kind'] == 'work'], key=lambda e: e['dates'], reverse=True)
    for entry in chronological:
        available = [p for p in ranked if p[0]['id'] == entry['id']]
        if available:
            best = available[0]; chosen.add(best[1]['id']); used += len(best[1]['zh']) + 35
            tokens.append(set(re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,4}', best[1]['zh'])))
    # A checked project gets one evidence bullet before optional extra bullets.
    # This makes the user's project choice meaningful within the same page budget.
    if selected_project_ids is not None:
        for project_id in selected_project_ids:
            available = [p for p in ranked if p[0]['id'] == project_id and p[1]['id'] not in chosen]
            if not available:
                continue
            entry, bullet, record = available[0]
            cost = len(bullet['zh']) + 35
            if used + cost <= budget:
                chosen.add(bullet['id']); used += cost
                tokens.append(set(re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,4}', bullet['zh'])))
            else:
                record['reason'] = '已勾选但超出当前篇幅预算；请缩短其他内容或提高篇幅预算'
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
        relevant = (record['dimensions']['jd_relevance'] > 0 or record['dimensions']['user_priority'] > 0 or
                    (selected_project_ids is not None and entry['id'] in selected_project_ids))
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
    return selected, highlights, {'policy_version': 3, 'budget': budget, 'estimated_used': used,
                                   'priorities': priorities,
                                   'selected_project_ids': selected_project_ids,
                                   'selection_mode': 'manual' if selected_project_ids is not None else 'automatic_legacy',
                                   'candidates': candidates}

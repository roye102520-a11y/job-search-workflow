"""Evidence-led JD analysis and a seven-day practice plan for the local studio."""
import re


TRAINING_RULES = {
    ('responsibility', 1): {
        'refs': ['yantu-segmentation', 'yantu-coordination', 'huohua-feedback-loop'],
        'assessment': '有学习问题识别、分层计划和跟进经验，能够迁移到培训需求诊断。',
        'gap': '尚无面向企业员工及合作伙伴设计培训体系、实施多批次培训并评估组织效能的直接证据。',
        'action': '选一个生活服务商家培训场景，写需求访谈提纲、能力地图、课程路径和效果评估方案。',
        'proof': '培训需求诊断与体系方案（含目标、对象、课程、评估指标）。',
    },
    ('responsibility', 2): {
        'refs': ['huohua-feedback-loop', 'mirror-interactive-delivery'],
        'assessment': '有跨方问题跟进和独立项目交付的相关经历。',
        'gap': '内外训项目的立项、预算/资源、里程碑、风险和结果复盘记录不足；AI 优化项目管理流程尚无具体案例。',
        'action': '把第 1 项方案写成项目章程、RACI、排期、风险表和周报，并用 AI 辅助汇总后人工校验。',
        'proof': '一页项目章程、排期与风险台账、一次 AI 辅助周报示例。',
    },
    ('responsibility', 3): {
        'refs': ['huohua-operation-guides', 'angli-structured-documents'],
        'assessment': '有把高频问题整理为操作指南、把非结构化资料转为可复用内容的经历。',
        'gap': '尚无可核验的业务标杆访谈、案例萃取过程及向团队推广方法论的记录。',
        'action': '选一个真实且可公开的业务案例，按背景、动作、判断、结果、适用边界整理成案例卡。',
        'proof': '一张带来源和适用边界的经验萃取案例卡。',
    },
    ('responsibility', 4): {
        'refs': ['huohua-operation-guides', 'angli-qa-versioning', 'mirror-offline-evaluation'],
        'assessment': '有图文指南、问答库、版本管理和 AI 输出质量评测经验。',
        'gap': '尚无企业培训课件/题库的落地效果，以及面向业务团队推广 AI 工具的实践证据。',
        'action': '制作一套微课、案例库和 10 道题；用 AI 起草后逐项核对来源、错误和可用性。',
        'proof': '课件、案例/题库、人工核验记录及 AI 工作流说明。',
    },
    ('responsibility', 5): {
        'refs': ['yantu-segmentation', 'huohua-lifecycle'],
        'assessment': '有持续跟踪学习计划和维系学员参与的相关经历。',
        'gap': '团队学习文化、参与机制和员工自驱提升尚无直接实践或结果记录。',
        'action': '为目标团队设计四周学习机制，说明参与触发、同伴分享、反馈和衡量方式。',
        'proof': '学习氛围运营日历与指标口径。',
    },
    ('requirement', 1): {
        'refs': ['person.education', 'mirror-interactive-delivery', 'huohua-feedback-loop'],
        'assessment': '本科学历有记录，也有个人项目交付和运营问题跟进经历。',
        'gap': '“至少一个项目管理实操”需要明确项目身份、本人决策、计划、协作和结果；现有材料未充分证明完整项目管理责任。',
        'action': '选一个最能说明推进能力的真实项目，补齐项目目标、角色、计划、取舍、里程碑和结果证据。',
        'proof': '一页项目案例及可追溯的原始材料清单。',
    },
    ('requirement', 2): {
        'refs': ['yantu-coordination', 'huohua-feedback-loop'],
        'assessment': '学习数据诊断、反馈归类能支持学习能力与业务问题意识。',
        'gap': '抖音生活服务、短视频和直播运营的实际操作记录未见证据；“优先”不能写成已具备。',
        'action': '拆解 3 个公开生活服务商家案例，观察短视频内容、直播承接、转化路径与复盘指标。',
        'proof': '3 份案例拆解与一张短视频/直播运营指标图；标注为研究练习。',
    },
    ('requirement', 3): {
        'refs': ['huohua-lifecycle', 'yantu-coordination'],
        'assessment': '协调教学团队、家长、学员的经历支持沟通与推进能力。',
        'gap': '公众表达、面对业务团队授课及正式培训控场暂无直接证据；时间管理需具体案例。',
        'action': '围绕培训方案做一次 10 分钟试讲，录像或记录反馈，并准备一个多方协调的 STAR 事例。',
        'proof': '试讲录屏/讲稿、反馈表及协作案例。',
    },
    ('requirement', 4): {
        'refs': ['huohua-operation-guides', 'angli-qa-versioning'],
        'assessment': '流程图、Office/WPS 与 AI 内容处理有记录。',
        'gap': 'PPT、思维导图及主流 AI 工具的独立熟练度没有可核验的具体样本。',
        'action': '用实际工具制作培训流程脑图与 8–12 页课件，保存可编辑源文件和制作说明。',
        'proof': '可编辑脑图、PPT 与工具使用记录。',
    },
    ('requirement', 5): {
        'refs': ['mirror-interactive-delivery', 'huohua-feedback-loop'],
        'assessment': '个人应用持续迭代和一线问题闭环能够说明适应变化与主动探索。',
        'gap': '创业精神、开放风格和培训创新是行为判断，现有材料不足以直接证明；需具体取舍与反馈案例。',
        'action': '准备两个真实事例：一次需求变化后的方案调整，一次培训/学习方式创新的设计与验证。',
        'proof': '两张可追问的 STAR 故事卡。',
    },
    ('requirement', 6): {
        'refs': ['angli-qa-versioning', 'mirror-offline-evaluation', 'huohua-operation-guides'],
        'assessment': 'AI 问答整理、质量检查和学习资料制作是较强的相邻证据。',
        'gap': '“AI+培训”在真实业务团队中的部署、使用率或效率效果尚未核实。',
        'action': '用同一培训主题做人工版与 AI 辅助版，记录用时、修改点、错误率和试用反馈。',
        'proof': 'AI+培训流程卡和有原始记录的前后对比；无实测则不声称提效。',
    },
}

TRAINING_FIT = {
    ('responsibility', 1): '中等相关', ('responsibility', 2): '较弱相关',
    ('responsibility', 3): '中等相关', ('responsibility', 4): '较强相关',
    ('responsibility', 5): '较弱相关', ('requirement', 1): '中等相关',
    ('requirement', 2): '较弱相关', ('requirement', 3): '中等相关',
    ('requirement', 4): '中等相关', ('requirement', 5): '中等相关',
    ('requirement', 6): '较强相关',
}

TRAINING_PLAN = [
    ('盘点真实证据', '核对学历、项目角色及奶茶店 SOP 的身份与时间；列出可展示原件和未证实项。', '证据清单与项目事实卡'),
    ('理解业务场景', '观察 3 个公开生活服务商家案例，分别记录短视频内容、直播承接、用户路径及可见指标。', '3 份标注来源的案例拆解'),
    ('建立运营框架', '画出内容曝光到到店/核销的假设漏斗；为短视频和直播各写一张复盘模板。', '运营指标图与两张复盘模板'),
    ('设计培训项目', '以商家伙伴入门为题，写需求诊断、学习目标、课程路径、项目排期、风险与效果评估。', '项目章程、课程大纲和评估表'),
    ('制作学习资源', '完成 8–12 页课件、一个案例卡及 10 道题；用 AI 辅助起草，逐条核验并保留修改记录。', 'PPT、案例/题库和 AI 核验表'),
    ('试讲与反馈', '进行一次 10 分钟试讲；能找到真实听众就收集反馈，找不到则录屏自评并如实标注。', '试讲记录、反馈或自评、修订清单'),
    ('整合与复盘', '完成一页岗位项目作品说明，梳理仍缺真实业务落地的部分，准备 2 个 STAR 事例。', '作品说明、两张故事卡和下一步实践清单'),
]


def split_points(jd):
    """Preserve each numbered JD point, including multiline content."""
    text = jd.replace('\r\n', '\n')
    heading = None
    points = []
    for raw in text.splitlines():
        line = raw.strip().strip('*# ')
        if not line:
            continue
        if re.search(r'^(?:职位描述|岗位职责|工作职责)', line):
            heading = 'responsibility'
            line = re.sub(r'^(?:职位描述|岗位职责|工作职责)\s*\**\s*', '', line)
        elif re.search(r'^(?:职位要求|任职要求|岗位要求)', line):
            heading = 'requirement'
            line = re.sub(r'^(?:职位要求|任职要求|岗位要求)\s*\**\s*', '', line)
        if not line:
            continue
        chunks = re.split(r'(?<!\d)(?=\d{1,2}[、.．](?!\d))', line)
        for chunk in chunks:
            chunk = chunk.strip()
            match = re.match(r'^(\d{1,2})[、.．]\s*(.*)$', chunk)
            if match and heading:
                points.append({'section': heading, 'number': int(match.group(1)), 'text': match.group(2).strip()})
            elif points:
                points[-1]['text'] += ' ' + chunk
    return [point for point in points if point['text']]


def _evidence_index(evidence):
    index = {}
    person = evidence['person']
    if '本科' in person.get('education_zh', ''):
        index['person.education'] = {'id': 'person.education', 'text': person['education_zh'], 'source': 'resume-evidence.json#person.education'}
    for entry in evidence['entries']:
        for bullet in entry['bullets']:
            index[bullet['id']] = {'id': bullet['id'], 'text': bullet['zh'], 'source': entry['source_ref']}
    return index


def _training_jd(jd, points):
    return ('培训' in jd and '抖音' in jd and '生活服务' in jd
            and len(points) >= 8 and any(p['section'] == 'requirement' for p in points))


def analyze(jd, evidence):
    if not isinstance(jd, str) or not jd.strip():
        raise ValueError('请先粘贴完整 JD 正文')
    if not isinstance(evidence, dict) or not isinstance(evidence.get('person'), dict) or not isinstance(evidence.get('entries'), list):
        raise ValueError('事实缓存格式不完整')
    points = split_points(jd)
    if not points:
        raise ValueError('请保留 JD 中的“职位描述/职位要求”和编号，以便逐点分析')
    index = _evidence_index(evidence)
    training = _training_jd(jd, points)
    items = []
    for point in points:
        rule = TRAINING_RULES.get((point['section'], point['number'])) if training else None
        refs = [index[ref] for ref in rule['refs'] if ref in index] if rule else []
        items.append({**point, 'status': 'related' if refs else 'unverified',
                      'fit': TRAINING_FIT.get((point['section'], point['number']), '待核实') if refs else '待核实',
                      'assessment': rule['assessment'] if refs else '当前没有足够的直接证据，需要进一步核实。',
                      'evidence': refs,
                      'gap': rule['gap'] if rule else '现有事实缓存不能完整证明这一条，不能把关键词相似当作符合。',
                      'action': rule['action'] if rule else '补充一份真实项目事例或完成针对这一条的可展示练习。',
                      'proof': rule['proof'] if rule else '带来源和个人贡献的案例或作品。'})
    if training:
        plan = [{'day': day, 'focus': focus, 'task': task, 'deliverable': deliverable}
                for day, (focus, task, deliverable) in enumerate(TRAINING_PLAN, 1)]
    else:
        priorities = [item['text'][:42] for item in items if item['status'] == 'unverified'][:3]
        while len(priorities) < 3:
            priorities.append('项目证据与面试表达')
        focuses = ['核对现有事实与硬条件', '研究岗位业务与典型案例', priorities[0], priorities[1], priorities[2], '做一次演练并收集反馈', '整合作品与复盘']
        plan = [{'day': day, 'focus': focus, 'task': '围绕该主题学习并制作可核验样本；练习与真实工作成果分开记录。', 'deliverable': '一份带来源、个人动作和待验证项的记录'}
                for day, focus in enumerate(focuses, 1)]
    return {'items': items, 'plan': plan, 'summary': {'related': sum(i['status'] == 'related' for i in items),
            'unverified': sum(i['status'] == 'unverified' for i in items), 'total': len(items)},
            'method': '逐条证据初筛；相关经历不等于直接满足；无证据不等于不具备；七天练习不等于真实岗位经验。'}

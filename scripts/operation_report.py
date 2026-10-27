"""Human-readable summaries of recorded facts, never inferred server success."""
from collections import Counter
from pathlib import Path


def authorization_matches(plan):
    a = plan.get('authorization') or {}
    return (isinstance(a, dict) and a.get('action') == 'complete-upload'
            and a.get('runId') == plan['runId'] and a.get('context') == plan['context']
            and a.get('source') in ('explicit-request', 'post-upload-confirmation')
            and all(isinstance(a.get(k), str) and a[k].strip() for k in ('userStatement', 'evidenceRef')))


def summarize(plans):
    if not plans or len({p['runId'] for p in plans}) != len(plans):
        raise ValueError('计划为空或重复；不能重复计数')
    project = lambda p: tuple(str(p['context'][k]).rstrip('/') for k in ('site', 'WID', 'OrgId'))
    if len({project(p) for p in plans}) != 1 or len({(p['mode'], p['expectedStatus']) for p in plans}) != 1:
        raise ValueError('汇总必须是同项目同阶段')
    scopes = [(p['context']['unit'], p['context']['profession']) for p in plans]
    if len(set(scopes)) != len(scopes):
        raise ValueError('计划范围重叠；先选择本范围的最终计划，不能静默累加')
    totals = dict(drawings=0, updated=0, added=0, reusedDrawings=0, directoryTargets=0,
                  cancellationTargets=0, cancellationFiles=0, otherMaterials=0, reusedMaterialTargets=0,
                  legacyVerifiedTargets=0)
    professions, states, details, notices, submissions = {}, Counter(), [], [], []
    cancel_files = set()
    for p in plans:
        c = p['context']
        prof = professions.setdefault(c['profession'], dict(drawings=0, updated=0, added=0, reused=0))
        notices.extend(p.get('blockers', []))
        notices.extend(p.get('warnings', []))
        has_directory = any(i['kind'] == 'directory' and i['status'] == 'verified' for i in p['items'])
        if not has_directory:
            notices.append(f"{c['unit']}/{c['profession']}：目录未更新，建议提供新版目录；有增补/取消时须补齐覆盖目录")
        if p.get('finish'):
            state = '已提交成功'
        elif p.get('completeRequested') is False or p.get('taskLimit') in ('inspect', 'trial', 'partial', 'no-submit'):
            state = '按用户限制未提交'
        elif p.get('blockers') or any(i['status'] != 'verified' for i in p['items']):
            state = '提交条件受阻'
        elif not authorization_matches(p):
            state = '文件已核实，尚待用户确认完成上传'
        else:
            state = '已记录授权，尚未提交；须先运行提交前检查'
        submissions.append(dict(runId=p['runId'], unit=c['unit'], profession=c['profession'],
                                state=state, serverState=(p.get('finish') or {}).get('serverState')))
        for i in p['items']:
            states[i['status']] += 1
            result = i.get('result') or {}
            reused = bool(i.get('reusedFrom')) or result.get('executionSource') == 'recovered'
            details.append(dict(runId=p['runId'], itemId=i['itemId'], unit=c['unit'], profession=c['profession'],
                originalName=i.get('originalName', ''), uploadName=(Path(i.get('path', '')).name if i['action'] == 'cancel' else i.get('uploadName', '')),
                path=i.get('path', ''),
                code=i.get('uploadCode', i.get('originalCode', '')), name=i.get('name', ''),
                action=i['action'], kind=i['kind'], status=i['status'], reused=reused,
                BPID=i.get('BPID'), VSID=result.get('VSID'), evidenceRef=result.get('evidenceRef'),
                executionSource=result.get('executionSource', 'legacy-unspecified'),
                issues=i.get('issues', []) + [result[k] for k in ('error', 'reason') if result.get(k)]))
            if i['status'] != 'verified':
                continue
            if reused:
                if i['kind'] == 'drawing' and i['action'] != 'cancel':
                    totals['reusedDrawings'] += 1
                    prof['reused'] += 1
                else:
                    totals['reusedMaterialTargets'] += 1
            elif result.get('executionSource') != 'uploaded':
                totals['legacyVerifiedTargets'] += 1
            elif i['action'] == 'cancel' or i['kind'] == 'cancellation':
                totals['cancellationTargets'] += 1
                cancel_files.add((str(Path(i.get('path', '')).resolve()).casefold(), i.get('sha256')))
            elif i['kind'] == 'directory':
                totals['directoryTargets'] += 1
            elif i['kind'] == 'drawing':
                key = 'added' if i['action'] == 'add' else 'updated'
                totals['drawings'] += 1
                totals[key] += 1
                prof['drawings'] += 1
                prof[key] += 1
            else:
                totals['otherMaterials'] += 1
    totals['cancellationFiles'] = len(cancel_files)
    return dict(runIds=[p['runId'] for p in plans], operationSummary=totals,
                byProfession=professions, statusCounts=dict(states), details=details,
                notices=list(dict.fromkeys(notices)), submissions=submissions)


def markdown(report):
    s = report['operationSummary']
    state_labels = dict(verified='已核实', failed='失败', unknown='待核查', processing='处理中', planned='未执行', blocked='受阻')
    lines = [f"本次成功上传 {s['drawings']} 张图纸，其中替换原图 {s['updated']} 张（保留历史版本），新增 {s['added']} 张。",
             '；'.join(f"{p}专业 {v['drawings']} 张" for p, v in report['byProfession'].items()) + '。',
             f"另上传目录 {s['directoryTargets']} 项，取消单 {s['cancellationFiles']} 份、关联 {s['cancellationTargets']} 个目标，其他材料 {s['otherMaterials']} 项。",
             f"复用此前已核实结果：图纸 {s['reusedDrawings']} 张、材料 {s['reusedMaterialTargets']} 项，未计入本次上传。", '',
             f"旧回执未标明执行来源：{s['legacyVerifiedTargets']} 项，保留已核实状态但不计入本次上传。", '',
             '状态统计：' + '；'.join(f'{state_labels.get(k, k)} {v}' for k, v in report['statusCounts'].items()), '']
    for x in report['submissions']:
        lines.append(f"- {x['unit']}/{x['profession']}：{x['state']}" + (f"，系统状态：{x['serverState']}" if x['serverState'] else ''))
    lines += ['', '提示：'] + ['- ' + n for n in report['notices']] if report['notices'] else []
    lines += ['', '| 单体/专业 | 原文件 → 上传名 | 实际文件路径 | 图号/图名 | 类型/动作 | 结果 | 版本/证据 | 问题 |',
              '|---|---|---|---|---|---|---|---|']
    escape = lambda v: str(v or '').replace('|', '\\|').replace('\n', '<br>')
    labels = dict(drawing='图纸', directory='目录', cancellation='取消单', material='其他材料',
                  update='替换原图', add='新增', cancel='取消', auto='待分类', verified='已核实',
                  failed='失败', unknown='待核查', processing='处理中', planned='未执行', blocked='受阻')
    for d in report['details']:
        cells = [f"{d['unit']}/{d['profession']}", f"{d['originalName']} → {d['uploadName']}", d['path'],
                 f"{d['code']} {d['name']}", f"{labels.get(d['kind'], d['kind'])}/{labels.get(d['action'], d['action'])}",
                 labels.get(d['status'], d['status']) + ('（复用）' if d['reused'] else ''),
                 f"BPID={d['BPID'] or '未确认'} VSID={d['VSID'] or '未产生/未确认'} {d['evidenceRef'] or ''}", '；'.join(map(str, d['issues']))]
        lines.append('| ' + ' | '.join(escape(x) for x in cells) + ' |')
    return '\n'.join(lines) + '\n'

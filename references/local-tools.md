# 本地工具与数据契约

均用 Python 标准库；`uv run scripts/upload_plan.py --help`。路径示例为相对技能目录的命令，实际任务将脚本替换为绝对路径；项目数据使用用户工作区。

## 1. 快照与请求

一个快照/计划限定一个单体与专业；每次从实际页面采集，不复制示例工程值。

```json
{
  "context": {"site":"http://example.invalid","WID":"工程ID","OrgId":"设计单位ID","unit":"单体ID或唯一名称","profession":"建筑"},
  "complete": true,
  "rows": [{"BPID":"101","code":"A-1.1","fullName":"首层平面图","BGID":"55",
    "versions":[{"VSID":"901","version":2,"status":"通过"}]}]
}
```

`complete` 只有实际核对请求与分页/总数后设 true。BGID/versions 缺字段保留缺失，不能填造空值。API data[0]/data[1] 用 collect.js 规范化；非该结构需按实际响应适配，不猜值。context 可附 WHID，workstatus 在浏览器执行时还须逐次检查。

请求示例（kind=directory 的目录成品必须由用户提供）：

```json
{
  "mode":"change",
  "expectedStatus":"变更",
  "completeRequested":true,
  "files":[
    {"path":"D:/本次图纸/A-1.1_首层平面图.pack","action":"update"},
    {"path":"D:/本次图纸/A-2.1_新增详图.pack","action":"add"},
    {"path":"D:/本次图纸/取消变更单.pdf","action":"cancel","kind":"cancellation","BPID":"102","code":"A-3","name":"原图名称","matchConfirmed":true},
    {"path":"D:/本次图纸/A-00_图纸目录.pack","action":"update","kind":"directory","directoryFor":["A-2.1","102"]}
  ]
}
```

mode 为 initial/change/completion；expectedStatus 填实际页面该阶段版本状态，竣工为已知“竣工”，不能凭示例猜其他状态。action 默认 auto，已有记录更新、初次无对应可新增；变更/竣工无对应必须有明确 add。取消一份单对多图则写多条显式目标。

`code/name` 从第一个下划线前后解析；不符合命名或图名中有歧义时清单明确指定。`BPID` 固定已有记录；`matchConfirmed=true` 只在实际核对过图号/图名差异时使用。相似度候选绝不自动确认。`directoryImpact=true` 标记更新也影响目录信息的情形。

## 2. 规划和改名

```powershell
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" sync "D:/项目资料/snapshot.json"
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" plan "D:/项目资料/snapshot.json" "D:/项目资料/request.json"
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" rename <返回的runId>
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" report <runId>
```

plan 输出每项状态与总 blockers/warnings；blocked 项不执行。某些缺目录导致收尾 blocker，不阻止其他 planned 项已获授权的上传。rename 会直接改成品名，先查看计划，冲突不覆盖。取消材料不原地改名。文件更改后重新规划；原计划已经发过请求时先 record 回读证据，不能靠新建计划忘掉旧上传事实。

## 3. 记录真实回读

对路径 A/原生上传或恢复后的图纸，将实际网络/页面结果规范化后 record；路径 B 的结果含同样信息，按实际快照汇总。`evidenceRef` 指本次保存的网络/页面证据位置，不能填造。

```json
{
  "snapshot": {"context":{},"complete":true,"rows":[]},
  "items":[{"itemId":"计划项ID","state":"verified","BPID":"101","VSID":"实际新版ID",
    "fileSha256":"计划中的文件哈希","processing":"success","evidenceRef":"本次实际证据文件"}]
}
```

将上例 snapshot 替换为真实完整结构，不直接运行空示例。state 可为 verified/failed/unknown/processing；后三者记录 reason。verified 要求目标、文件、VSID、实际阶段及 PACK 解压成功。与 before 相同 VSID 时必须另给 `replacementEvidence` 说明服务器确实替换内容，否则不能把旧版当新上传。

```powershell
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" record <runId> "D:/项目资料/readback.json"
```

record 不发上传请求；未知项先从服务器查结果，确定未落版本才重试。缺件补齐后生成新的完整计划，在请求增加 `"reuseVerifiedFrom":["原runId"]`，并提供最新完整快照。只有原批次 verified、相同范围和阶段、相同文件哈希、同 BPID 且对应版本仍存在的项才自动纳入已满足项；只派发 planned 项。已上传增补项可保留 action=add，由旧回执证明其来源。已完成上传的批次不能作为后来新任务的免传依据。未核实的 unknown/failed 不能靠重建计划变成成功；先回读补记。

## 4. 记录完成上传

页面收尾已实际执行并成功回读后才 `finalize`。收尾请求可能覆盖多个专业，代理先保证按钮整体范围完成，而不只核验一个专业的计划。

回执：`{"accepted":true,"serverState":"实际回读状态","evidenceRef":"真实收尾证据路径","snapshot":实际回读快照}`。

```powershell
uv run scripts/upload_plan.py --project "D:/项目资料/upload-state" finalize <runId> "D:/项目资料/finish.json"
```

有 blocker、非 verified 项、竣工缺项或未获成功证据时拒绝记录完成。用户限定部分/试传时 completeRequested=false，finalize 拒绝整批收尾。命令只记录结果，不能替代点击“完成上传”。

## 5. 本地文件与证据服务

只有路径 B 或浏览器无法可靠下载证据时才启动。--origin 为真实站点源（无尾斜杠），令牌放在图纸目录之外，两项服务可共用同一运行令牌文件。

```powershell
uv run scripts/cors_server.py --base "D:/本次图纸" --port 8765 --origin "http://实际站点" --token-file "D:/项目资料/run/token.txt" --allow "D:/项目资料/run/allowed.json"
uv run scripts/receive_server.py --out "D:/项目资料/run/evidence" --port 8766 --origin "http://实际站点" --token-file "D:/项目资料/run/token.txt"
```

allowed.json 是本次可上传文件的绝对路径 JSON 数组，改名后用实际路径生成。未提供 --allow 时仅暴露 base 内文件，仍不列目录；优先提供 allow。后台启动用隐藏窗口，记录进程号，结束关闭本次服务。

浏览器通过 `X-Upload-Token` 或 `?token=` 传令牌。读取文件的路径按每段编码一次；不要将冒号/反斜杠作为 URL 相对路径。文件服务返回 `X-Content-SHA256`。接收服务 `POST /事件名` 收 JSON 对象/数组，最大 8MB，每次落到唯一文件并返回文件名；事件名只用中文/字母数字/下划线/短横线，不传路径。`GET /ping` 检查连通。

```javascript
async function persist(event) {
  const r = await fetch('http://127.0.0.1:8766/upload_event', {
    method:'POST', headers:{'Content-Type':'application/json','X-Upload-Token':runtimeToken},
    body:JSON.stringify(event)
  });
  if (!r.ok) throw new Error('Evidence persistence failed');
  return r.json();
}
```

令牌仅用于本地运行，不入项目 Git、不写日志或最终报告。跨域/本地网络限制导致失败时改原生或人工路径，不关闭浏览器安全设置。

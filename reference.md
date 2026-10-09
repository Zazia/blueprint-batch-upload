# reference.md — JGTGL 图纸系统批量上传技术参考

## 0. 路径 A：图号对齐 + "上传图纸"批量上传

SKILL.md 路径 A 的技术细节。核心事实（用户实测）：页面"上传图纸"按钮一次多选后，系统按文件名中的图号自动对应已有记录并上传为新版；**图号含 `.` 的文件识别有误**，须回退路径 B 逐条注入。

### 0.1 系统图纸列表导出（浏览器注入）

列表几百条时 browser_evaluate 返回值会被截断，用页面内生成 TSV 下载绕过：

```javascript
(function() {
  const rows = document.querySelectorAll('tr.editTR');
  const lines = ['序号\t图号\t图名'];
  rows.forEach(tr => {
    const g = n => { const el = tr.querySelector('div[name="' + n + '"]'); return el ? el.textContent.trim() : ''; };
    lines.push([g('orderNum'), g('code'), g('fullName')].join('\t'));
  });
  const blob = new Blob(['\ufeff' + lines.join('\n')], {type: 'text/tsv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'blueprint_list.tsv';
  a.click();
})();
```

注意：

- `\ufeff` BOM 必加，否则中文乱码
- 下载文件落在浏览器临时目录（形如 `<uuid>.tmp`，无扩展名），按修改时间搜索、验证内容后复制到工作区
- 若单元格内含制表符导致列错位，改用 `%%%` 等明确分隔符重新导出
- 切专业 radio 不刷新页面，但列表是 AJAX 重载，导出前需等列表加载完成

### 0.2 图号对齐匹配策略（Python 改名脚本要点）

输入：系统 TSV（序号/图号/图名）+ 本地文件夹（`图号_图名.pack`）。多轮匹配，全局择优：

1. **图号精确匹配**：规范化后相等（去首尾空格、全半角、大小写）；同一图号对应多条记录/文件时，按图名相似度全局择优分配
2. **图名匹配**：图号对不上的剩余文件，按规范化图名相等匹配
3. **模糊匹配兜底**：相似度 ≥ 0.75 才收。低于阈值宁可留未匹配人工处理（实测 0.6 阈值会把"平台栏杆详图"误配到"铁艺栏杆详图"）

流程：干跑 → 输出报告（改名计划 / 可疑配对 / 未匹配清单）→ 人工核查 → `--execute` 执行 → 抽查验证。

**"将错就错"原则**：系统图号栏录入错误（序号当图号、图号拼进图名、图名地点张冠李戴）一律以系统为准改名本地文件，上传匹配只认系统存的图号。例：系统把序号 `88` 误录为图号，本地 `Z3P4.4_上塘街39~47号更换提升铸铁井盖平面图.pack` 改名为 `88_上塘街39~47号更换提升铸铁井盖平面图.pack`。

### 0.3 分流规则

文件名第一个 `_` 之前的图号部分含 `.` → 走路径 B。实例：园林专业 269 文件中 139 个含点（园建 114 + 绿化 25），其余 130 个可一次多选批量上传。

## 1. 页面结构

页面标题"上传竣工图"，主要区域：

| 区域 | 说明 |
|------|------|
| 工程信息（#tbWork） | 工程编码、名称、单体 |
| 专业选择（#rdg_profession） | radio 组，`input[name="profession1"][value="建筑|给排水|电气|海绵城市|园林"]`，切换后 AJAX 重载列表 |
| 图纸清单（#pdfList） | `tr.editTR` 行集合，每专业几百条 |

### 行 DOM 结构

```html
<tr class="editTR" mode="upload">
  <td><select name="type">…</select></td>          <!-- 图纸类型 -->
  <td><div name="orderNum" contenteditable>…</div></td>  <!-- 序号 -->
  <td><div name="code" contenteditable>YM-1.3</div></td>  <!-- 图号 -->
  <td><div name="fullName" contenteditable>图纸目录四</div></td> <!-- 图名 -->
  <td class="versions">
    <a class="btnView" vsid="…" status="通过" version="12">第12版竣工<span class="filesize">5MB</span></a>
    <!-- 上传中动态追加: <a status="待上传|已上传|上传失败">…</a> -->
  </td>
  <td class="action">
    <a class="btnUploadNewVersion" onclick="uploadPDF.uploadNewVersion(this)">上传新版</a>
    <a onclick="uploadPDF.deleteBlueprint(this)">删除</a>
  </td>
</tr>
```

jQuery 数据：`tr.data('data')` 存完整记录对象（含 `BPID`、`WID`、`code`、版本数组 `xml`）。

### 选择器速查

| 用途 | 选择器 |
|------|--------|
| 图纸行 | `tr.editTR` |
| 图号 | `div[name="code"]`（取 textContent.trim()） |
| 图名 | `div[name="fullName"]` |
| 上传新版按钮 | `.btnUploadNewVersion` |
| 版本链接 | `td.versions a[vsid]`（最后一个为最新版） |
| 上传状态 | 行内 `a[status]`，取 status 属性和 title |

## 2. 上传链路（点击"上传新版"原流程）

```
uploadPDF.uploadNewVersion(btn)
  ├─ 找该行最新版本 a[vsid]:last
  ├─ 若状态为"通过" → jConfirm 确认框
  ├─ 动态创建 input[type=file] accept=".{原扩展名},.pack" 并 .click()  ← 系统对话框，自动化死路
  └─ 选到文件后 → _saveAndupload(btn, file, a)

uploadPDF._saveAndupload(btn, file, link)
  ├─ BPID = tr.data('data').BPID；行内追加"待上传"进度条
  ├─ cos.uploadFile(成功回调, 失败回调, 进度回调, cos.bucket, cos.region, file, …)
  │    └─ POST /mycos/upload.do（FormData: uid, sign, filename, file）→ 返回 {url}
  ├─ 成功后 POST /api/procHandler?procname=blueprintVersion_add_jgt
  │    参数: {BPID, url, fileSize, workstatus}   ← wstatus 为页面全局变量
  ├─ 数据库成功 → 删除同版本旧记录、更新 UI 为"已上传"、记录 vsid/version
  └─ ext == 'pack' → POST /unpack/unpack.do（读 Config.GetValue("中望解压程序地址")）
       参数: {packPath, unpackPath}
```

PDF 文件在上传前还有 `checkSign` 验章（FileReader 读内容查 `/Sig`、`/Encrypt`），.pack 不走验章。

关键接口：

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/sv?ns=upload&act=read_blueprint_and_version` | POST | 读取图纸列表+版本 |
| `/mycos/upload.do` | POST | COS 文件存储上传 |
| `/api/procHandler?procname=blueprintVersion_add_jgt` | POST | 保存版本记录 |
| `/unpack/unpack.do` | POST | 解压 .pack |

COS 返回 url 形如 `/cosfile/2026/08/<WID>/<hash>.pack`。

## 3. 完整注入脚本（可直接复制）

分两次 browser_evaluate 注入（或合并为一次）。

### 3.1 修复版 _saveAndupload（覆盖页面 bug）

```javascript
(function() {
  uploadPDF._saveAndupload = function(btn, file, link) {
    if (!file) return;
    var me = this,
        btn = $(btn),
        ext = file.name.split('.').pop().toLowerCase(),
        tr = btn.closest('tr'),
        td = tr.find('td.versions:first'),
        _data = tr.data('data'),
        fileSize = (file.size / 1024).toFixed(0) + ' KB',
        BPID = _data.BPID;

    var progressWraper = $('<a status="待上传"><i>待上传</i>(' + fileSize + ')<b title="删除文件" class="deleteBtn">×</b></a>');
    td.append(progressWraper);
    var $progress = $('<div class="progress"></div>');
    progressWraper.append($progress);

    var params = {convert2svg: '1'};
    var _filename = cos.region;

    cos.uploadFile(function (result) {
      var obj = JSON.parse(result.target.response);
      var url = obj.url || obj.data || null;
      if ((obj.errcode !== 0 && typeof obj.success != 'undefined' && !obj.success) || url == null) {
        progressWraper.attr('url', url).attr('status', '上传失败').find('i').text('上传失败');
        return;
      }
      $.post('/api/procHandler?procname=blueprintVersion_add_jgt', {
        BPID: BPID, url: url, fileSize: file.size, workstatus: wstatus
      }, function (res) {
        if (res.errcode === 0) {
          var data = res.data[0];
          $(link).closest('td').find('a[version="' + data.version + '"]').remove();  // 原版 bug：link.closest(...).find(...)
          progressWraper.attr('url', url).attr('status', '已上传').find('i').text('已上传');
          progressWraper.attr('vsid', data.VSID).attr('version', data.version);
          if (ext == 'gdb' || ext == 'GDB') {
            me.sendToBIM(me.WID, me.WNAME, workInfo['ITEMID'], data.VSID);
          }
          if (ext == 'pack') {
            var unpackPath = url.substring(1, url.lastIndexOf("/") + 1) + _data.WID + url.substring(url.lastIndexOf("/"), url.length - 5);
            var packPath = url.substring(1);
            $.post(Config.GetValue("中望解压程序地址"), {
              packPath: packPath, unpackPath: unpackPath
            }, function (res) { if (!res.success) { jAlert(res.message); } })
          }
        } else {
          progressWraper.attr('url', url).attr('title', res.errmsg).attr('status', '上传失败').find('i').text('上传失败');
        }
      });
    }, function (result) {
      progressWraper.attr('status', '上传失败').attr('title', result ? result.message : '').find('i').text('上传失败');
    }, function (curr, sha1) {
      $progress.width((curr * 100 || 0) + '%');
    }, cos.bucket, _filename, file, 0, taskReady, params);
  };
})();
```

### 3.2 辅助函数（必须挂 window）

```javascript
window.uploadBlueprintByCode = async function(code, localUrl, displayName) {
  const resp = await fetch(localUrl);
  if (!resp.ok) throw new Error('File not found: ' + localUrl);
  const blob = await resp.blob();
  const file = new File([blob], displayName + '.pack', {type: 'application/octet-stream'});

  const rows = document.querySelectorAll('tr.editTR');
  let targetRow = null;
  for (let i = 0; i < rows.length; i++) {
    const codeDiv = rows[i].querySelector('div[name="code"]');
    if (codeDiv && codeDiv.textContent.trim() === code) { targetRow = rows[i]; break; }
  }
  if (!targetRow) throw new Error('Row not found for code: ' + code);

  const btn = targetRow.querySelector('.btnUploadNewVersion');
  if (!btn) throw new Error('Upload button not found for: ' + code);

  const versions = targetRow.querySelectorAll('td.versions a[vsid]');
  const lastA = versions.length > 0 ? versions[versions.length - 1] : null;

  uploadPDF._saveAndupload(btn, file, lastA);
  return {success: true, code, fileName: file.name, size: file.size};
}
```

### 3.3 状态查询（验证用）

```javascript
window.checkUploadStatus = function(code) {
  const rows = document.querySelectorAll('tr.editTR');
  for (let i = 0; i < rows.length; i++) {
    const codeDiv = rows[i].querySelector('div[name="code"]');
    if (codeDiv && codeDiv.textContent.trim() === code) {
      return [...rows[i].querySelectorAll('td.versions a')].map(a => ({
        text: a.textContent.trim(), status: a.getAttribute('status'),
        version: a.getAttribute('version'), title: a.getAttribute('title')
      }));
    }
  }
  return null;
}
```

## 4. 批量编排：分段循环模式（推荐）

单次 evaluate 有超时限制，逐个文件驱动又费 token（每文件 2+ 次交互）。正确做法：**每段注入一个自循环脚本处理 15-20 个文件，agent 只在段间交互**。

### 4.1 分段循环脚本（每段注入一次）

```javascript
// tasks: [{code, url, name}]，本段 15-20 条。前置：已注入 3.1 修复版 _saveAndupload
window.__batchStatus = {running: false, current: 0, total: 0, results: []};

window.runBatch = async function(tasks) {
  const S = window.__batchStatus;
  S.running = true; S.total = tasks.length;
  for (const t of tasks) {
    S.current++;
    try {
      await window.uploadBlueprintByCode(t.code, t.url, t.name);
    } catch (e) {
      S.results.push({code: t.code, ok: false, reason: e.message}); continue;
    }
    // 等待该行状态从"待上传"变为终态
    for (let i = 0; i < 36; i++) {              // 最多 180 秒
      await new Promise(r => setTimeout(r, 5000));
      const vs = window.checkUploadStatus(t.code);
      const last = vs && vs[vs.length - 1];
      if (last && last.status === '已上传') { S.results.push({code: t.code, ok: true}); break; }
      if (last && last.status === '上传失败') { S.results.push({code: t.code, ok: false, reason: last.title}); break; }
    }
    await new Promise(r => setTimeout(r, 3000)); // 条间隔，减轻服务器压力
  }
  S.running = false;
  return 'batch done';
};

window.runBatch(tasks);  // 不 await，evaluate 立即返回
```

### 4.2 agent 段间交互流程

```
每段（15-20 个文件）:
  1. evaluate（注入）: 传入本段 tasks 数组，启动 runBatch
  2. 等待 5-10 分钟（段长 × 每文件 20-60 秒）
  3. evaluate: 读取 window.__batchStatus
     - running=false → 本段完成，记下 results，进入下一段
     - running=true → 继续等待，再读
     - 读取失败/页面刷新 → 检查页面，重新注入后从断点续传（跳过 results 里已成功的）
```

### 4.3 断点续传

循环脚本用 `window.__batchStatus.results` 记录进度。页面意外刷新时：重新注入 3.1 + 3.2 脚本 → 查已成功的图号 → 构造剩余任务的 tasks 数组 → 重新 runBatch。

### 4.4 备选：逐条模式（仅调试单文件时用）

```
对单个文件:
  1. url = urlencode(f"http://127.0.0.1:{port}/{folder}/{code}_{name}.pack")
  2. evaluate: await window.uploadBlueprintByCode(code, url, name)
  3. 轮询 window.checkUploadStatus(code) 直到终态（已上传/上传失败/3 分钟超时）
```

批量任务禁止用此模式（token 消耗约为分段循环的 3-5 倍）。

## 5. 排障

| 症状 | 原因 | 处理 |
|------|------|------|
| 卡在"待上传"100% | 页面 bug：`link.closest('td').find()` 原生 DOM 无 jQuery 方法 | 注入修复版（3.1），改 `$(link)` |
| evaluate 里函数未定义 | 未挂 window 或页面刷新过 | 重新注入全部脚本 |
| fetch 本地文件失败 | CORS 服务未启动 / URL 未编码 | 重启服务，中文和括号做 URL 编码 |
| "上传失败" | 读行内 `a[title]` 属性；查网络请求 | COS 返回错误看 upload.do 响应体 |
| 找不到图号行 | 专业没切换 / 图号空格 | 切 radio 重载列表；code 取 trim 后比对 |
| 403 Forbidden（直接 curl 页面） | 需登录态 | 必须用已登录的浏览器会话，不能裸 HTTP 请求页面 |

## 6. "完成上传"校验链路与 BGID 竣工规则（2026-08-26/27 实测）

按钮：`<button onclick="uploadPDF.jgtCompleteUpload()">完成上传</button>`（uploadBlueprint.js）。两步链路：

```
点击"完成上传"
 ├─ POST /pdfseal/pdfseal.ashx?method=checkCanSealJGT   参数 {WID, WHID}
 │    ├─ success=false → jAlert(res.message)
 │    ├─ data 非空 → jAlert("图纸验证失败，还有图纸未上传新版pack文件或pack文件解压失败…"+files)
 │    └─ data 为空（通过）↓
 └─ POST /api/procHandler?procname=blueprint_uploadComplete_jgt   参数 {WID, WHID}（真正提交）
      ├─ errcode != 0 → jAlert(res.errmsg)   ← "还有变更图纸未上传竣工图纸，不能完成上传"来自这里（服务端，页面JS无此文案）
      └─ errcode == 0 → "已完成上传"并跳转
```

**核心规则（BGID 判据，推翻早期"版本链判据"）**：服务端校验的是图纸记录的隐藏字段 `BGID`（变更单 ID，在 `read_blueprint_and_version` 响应 `data[0]` 图纸记录里，`null` = 未圈进任何变更单）——**凡 BGID 非空的图纸，版本数组里必须存在 status='竣工' 的记录，否则提交被拒（errcode 503）**，与版本链里有没有"变更"版无关。按版本链排查必漏判：实测 623 张中 172 张 BGID=21631 且无竣工版，其版本链里从未出现"变更"版（只有通过/整改），页面表格毫无异常标记。页面 JS 佐证（`createRow`）：`if(data.BGID!=null && data.xml[data.xml.length-1].status!='变更'){ isBG=true }`，isBG 时操作列"上传新版"下追加"(图纸已变更必须上传)"。铁证：建筑 12 张 BGID 图从 v2·通过直跳 v7·竣工（从无变更版）即不再阻断。诊断方法：抓接口原始响应，按"BGID 非空 且 版本数组中无 `status=='竣工'`"筛选，逐专业汇总。

**BGID 圈选机制（为何会大面积卡"完成上传"）**：BGID 在变更单登记/关联图纸时写入 BPID 记录（**图纸目录级字段，非版本级**），圈选与是否实际出过"变更"版完全解耦。典型根因：变更阶段建设单位为省事**全选/多选图纸**，设计单位只对部分图纸上传了变更版——变更阶段系统不校验"圈选数=变更版数"，到竣工图阶段 `blueprint_uploadComplete_jgt` 只认 BGID 非空+无竣工版就全拦，报错还不指名图号。实测该项目共 7 个 BGID：其中 6 个"圈选数=变更版数=竣工版数"（圈得准或已补齐），唯独 21631 圈 374 张、实际出过变更版仅 186 张，缺竣工的 172 张中**出过变更版的恰好 0 张**（全是"圈了但没改"的陪绑）；分专业看海绵城市 61/62 张被圈、0 张实际变更过，即"整个专业被全选"。诊断统计法：五专业接口原始响应按 BGID 聚合，输出"圈选/出过变更版/有竣工版/缺竣工"四列交叉表——若"缺竣工且出过变更版"≈0，即可定性为"圈多了"而非"漏传了"。

**数据导出技巧**：blob+`a.click()` 下载大多不落地（5 次仅 1 次成功）；可靠方式是本地起接收服务器（如 `receive_server.py`，端口 8766，CORS `*`），页面 JS 收集 `tr.editTR` 后 `fetch('http://127.0.0.1:8766/prof_'+encodeURIComponent(专业名), {method:'POST', body: JSON})` 直接收文件。切专业后必须等 `tr.editTR` 行数稳定再收集（轮询 2 次不变）。

**接口原始响应抓取（拿隐藏字段的唯一途径）**：DOM 导出拿不到 BGID 这类字段，须拦截 AJAX：注入 `$(document).ajaxComplete(function(e, x, s){ if(/read_blueprint_and_version/.test(s.url)) fetch('http://127.0.0.1:8766/api2_'+encodeURIComponent(curProf), {method:'POST', body: JSON.stringify({url: s.url, response: x.responseText})}) })`，切专业触发请求即落盘。注意 responseText 是字符串，解析时再 `JSON.parse`；`data[0]` 为图纸记录数组（含 BPID/BGID/code/fullName），`data[1]` 为版本记录数组（含 BPID/version/status），按 BPID 关联。

**BGID 排障要点**：① 图纸记录字段仅 BPID/BGID/code/fullName/profession/orderNum/type/fileSize/subName/WID/OrgId/JointProfession/scale/status 等，**只有 BGID 数值，没有变更单名称/日期**——要定位具体是哪份变更单，须去变更单管理页面查或问图审机构；从圈图范围反推也可（如 25533≈路灯改造批次）。② 变更单文件本身也可能被当作一张图登记上传（如电气"X34 设变单"），可反查变更单实体。③ 同一张图纸目录只能挂一个 BGID，多份变更单先后圈同一批图时各圈各的（实测建筑专业同一批目录被 21631/25533/26055/26461 四张单先后圈过）。

**缺竣工版的两种修复路径**：① **后台清 BGID**（最快）：联系图审机构清除错误圈定图纸的 BGID 关联，适合"圈了但没改"的大批量（如整个海绵专业 61 张，本地根本没有竣工图文件可传）。② **按现行批准版补传竣工版**：当前竣工阶段 workstatus 下 `blueprintVersion_add_jgt` 会自动把新版本标"竣工"，每张传一次即可，无需设计院重新出图（内容=现行最新通过版）——合规性需与图审机构事先确认。补传可用本技能路径 A/B，缺文件时可先从系统下载现行版再回传。

**排障补充**：browser_use 子代理 resume 后可能返回陈旧摘要（不执行新任务），要以副作用（如接收服务器落盘文件）验证实际执行情况；专业行数参考：建筑136/给排水35/电气34/海绵城市62/园林356（同一 WID）。代理导出数据时会把专业名标错（曾把电气数据标成建筑），务必核对 url 字段和图号前缀。

## 7. 已验证案例

- 系统：`http://120.197.38.55/JGTGL/uploadBlueprint.html?WID=<wid>&WHID=<whid>&OrgId=<orgid>`
- 文件大小 5.5MB / 6.5MB / 13.2MB 三档均成功
- 成功标志：行内绿色"已上传(XXXX KB)"，三个接口（upload.do / blueprintVersion_add_jgt / unpack.do）均 200
- 图号对齐（2026-08 实测）：建筑专业 111/111、园林专业 268/269 匹配成功（1 个文件系统无对应记录，保留原名），园林改名 152 个
- "上传图纸"按图号自动对应新版、含点图号识别有误：用户实测结论，含点文件回退路径 B 逐条注入

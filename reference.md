# JGTGL 上传技术参考

原技能的竣工上传经验继续沿用；原始完整版本已保存在 Git 基线 `1932a7e`。旧的固定 `.pack` 辅助函数、只在 window 保存进度和“超时后直接重传”的循环已由当前工具替代，不再复制旧循环。

## 1. 页面与已验证链路

| 对象 | 位置 |
|---|---|
| 图纸行 | `tr.editTR`；jQuery `$(tr).data('data')` 中有 BPID/WID/code 等 |
| 图号/图名 | `div[name="code"]`、`div[name="fullName"]` |
| 新版入口 | `.btnUploadNewVersion` |
| 版本 | `td.versions a[vsid]`，status/title 是状态/错误线索 |
| 专业 | `input[name="profession1"]`，如 value="园林" |
| 列表/版本 | `/api/sv?ns=upload&act=read_blueprint_and_version`；已验证响应 data[0] 为目录、data[1] 为版本，按 BPID 关联 |
| 存储 | `/mycos/upload.do`，由页面 `cos.uploadFile` 调用 |
| 保存版本 | `/api/procHandler?procname=blueprintVersion_add_jgt`：BPID/url/fileSize/workstatus |
| PACK 解压 | 页面 `Config.GetValue("中望解压程序地址")` 对应解压接口，packPath/unpackPath |

列表 AJAX 重载后再导出。专业切换不改变页面 URL；不要用某个全局当前专业变量给晚到响应贴标签。版本最后一项是历史常见布局，核验仍以实际 VSID 绑定，不能只检查最后一个绿字。

只读采集脚本：[collect.js](scripts/browser/collect.js)。`visible(context)` 永远返回 complete=false；`normalize(context, rawResponse, false)` 合并原始数组。代理核对请求、单体专业、分页/总数后才将 complete 设为 true。`captureOnce` 需提供根据实际请求参数写的匹配函数，固定一次请求上下文，不抓取其他专业。不要由 DOM 缺少 BGID 推断其为 null。

## 2. 路径 A：批量上传

按系统图号命名为 `图号_图名.pack`，无点图号优先页面“上传图纸”批量多选。系统按图号对应已有记录挂新版。初次/增补同一入口建立新记录；执行前必须把新增与更新分开，确认新增图号不与现有记录冲突。

保留人工一次多选的直接路径，若自动化能处理文件输入即可使用原生能力。混合文件先 A 后 B，用清单分流，无需移动源文件夹。上传后逐项核对系统结果，抽查不能替代全量记录对账。

## 3. 路径 B：精确 BPID 上传 PACK 新版

适用已有图纸、含点图号或全自动逐项上传。先读 [本地工具](references/local-tools.md) 启动带运行令牌的文件服务与接收服务。没有工具允许的 JS 执行能力时转原生入口。

加载 [upload.js](scripts/browser/upload.js)。该文件保留 COS→版本保存→PACK 解压链路和 `$(link).closest(...).find(...)` 修复，新增 BPID/上下文检查、解压终态、超时未知和持久化回调。它不覆盖页面原函数，不做新增、PDF、取消材料或签章。PDF 仍走原生入口以保留文件类型/验章处理。

配置时给出三项真实适配函数：

- `getContext()`：从当前页面/URL/已观察表单取 site/WID/OrgId/unit/profession/workstatus；不能返回一个永不变化的常量冒充当前状态。
- `persist(event)`：POST JSON 到接收服务，每次 await 响应成功；失败停止派发，避免丢失上传事实。
- `readBack()`：重新从实际列表响应取得规范化快照，包含实际版本 status/VSID。不能把上传前数据返回充当回读。

```javascript
const adapter = BlueprintUpload.jgtglAdapter({getContext, persist, readBack});
window.blueprintRunner = BlueprintUpload.createRunner(adapter);
// tasks 从 plan.json 的 planned 更新项生成，补 url、expectedStatus。
// context 是启动时已核对的 getContext() 结果，runId 来自计划。
window.blueprintRunner.run(tasks, {runId, context, timeoutMs:180000});
// 不挂起浏览器工具数分钟；分段读取：
window.blueprintRunner.status();
// 停止只是不派发下一项，不能声称撤销已发服务器请求：
window.blueprintRunner.stop();
```

URL 每段路径分别编码一次，用查询参数 token 或 X-Upload-Token 头传运行令牌。HTTP 站点可能没有 WebCrypto；脚本读取本地受保护服务提供的文件哈希头比较，不检查 PACK 内部。

每段约 15–20 项，按实际文件大小调整。出现 unknown、上下文变化或持久化失败就停止；页面刷新后函数丢失，先回读已发项再重新加载。超时不表示请求已撤销，可能存在晚到保存结果，不立即再次派发同 BPID。

## 4. 完成上传和 BGID

原竣工链路：页面 `uploadPDF.jgtCompleteUpload()` 先调用 `checkCanSealJGT`（WID/WHID），成功且 data 无阻塞后调用 `blueprint_uploadComplete_jgt`。优先使用页面按钮/原函数维护本身流程；不要并行或跳过前一步直接提交。

- “图纸验证失败，还有图纸未上传新版pack文件或pack文件解压失败…”：根据接口给出的文件逐项定位。
- “还有变更图纸未上传竣工图纸”：从接口目录找 BGID 非空且版本无 status='竣工' 的图；没有变更版也必须补。结合已知曾勾选记录，不能把缺字段当作无关联。
- 取消单上传到原图，不清除 BGID。系统未接受其本阶段结果时仍属阻塞，不凭本地 cancelled 状态免除上传。
- 缺成品输出具体图号/图名；现行批准版确为本次所需内容时可按已知经验补传，不要求读取包内；不为了消报错随意替代内容。

初次及变更上传使用实际页面的原生收尾入口；不假设它们也调用上述竣工接口。收到成功响应后必须回读状态并保存证据，未知/失败不记录为完成。

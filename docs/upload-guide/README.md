# 公众号介绍稿与流程图片

正文源文件为 [usage-walkthrough.md](../usage-walkthrough.md)，共八个真实需求情境。打开 [index.html](index.html) 看图文预览，[body.html](body.html) 为独立的行内样式正文。标题可直接使用“图都画完了，怎么还在跟‘上传’较劲？”；短标题可用“审图上传，别再跟一个点号较劲”。

## 图片规格与内容

十张 PNG 均为 1080×1440、3:4 竖图。主标题 54px，阶段标题 42px，框内文字 40px，阶段位置、箭头和间距一致。每图四个阶段，先看阶段标题，再看框内判断条件与动作。不是将不同宽高的图硬缩成同一张图片；所有图片由同一版式直接生成。

总体流程将原说明的“形成报告”和“授权提交”合并为一个展示阶段，执行逻辑未改变。分组内的三行是动作或条件规则，不表示所有条件都会依次发生。分组之间的箭头表示阅读与处理阶段的先后；阻塞时按框内说明停止对应动作。

| 图 | 用途 |
|---|---|
| [00 总体](assets/00-overview.png) | 四阶段大体流程 |
| [01 首次上传](assets/01-initial.png) | 外层预检、命名和首传建档 |
| [02 变更上传](assets/02-change.png) | 原图对应、动作判断与执行入口 |
| [03 项目接手](assets/03-handover.png) | 从系统当前状态建立账本 |
| [04 增补与取消](assets/04-add-cancel.png) | 新增、取消材料、正式目录 |
| [05 竣工上传](assets/05-completion.png) | 勾选必传集合和剩余缺项 |
| [06 中断恢复](assets/06-resume.png) | 查事实、分流、补传和累计报告 |
| [07 限定范围](assets/07-limited.png) | 预检、试传、指定专业和不提交 |
| [08 报告与提交](assets/08-report-submit.png) | 动作统计、整体范围、确认及回读 |
| [09 预留接口](assets/09-interfaces.png) | 两个未来接口的职责边界 |

主文章使用前九张，接口图用于接口文档及后续补充介绍。后续贴图版可直接复用这些图，按发布平台另写简短引导；本次未另行制作贴图版全文、封面或平台发布内容。

## 编辑与重新生成

[diagrams.json](diagrams.json) 是十张图的统一文案源；[build.cjs](build.cjs) 生成 PNG、SVG、分阶段 Mermaid 源、正文 HTML 和本地预览。SVG 和 Mermaid 源在 sources/。发布使用 PNG，无需公众号支持 SVG 或 Mermaid。

复用已安装的 Node.js、Playwright 和 Chrome。将 NODE_PATH 指向实际包目录，CHROME_PATH 可指定浏览器可执行文件，不需要新下载绘图库：

```powershell
$env:NODE_PATH = '<已安装依赖>/node_modules'
$env:CHROME_PATH = '<Chrome 可执行文件路径>'
node docs/upload-guide/build.cjs
```

如果改文案，先改 Markdown 与 diagrams.json 中对应内容，再生成；不要单独编辑生成的 PNG。Python 环境仍遵循项目指南，安利使用 uv；本制图步骤只使用 Node.js。

生成程序逐张检查 SVG 文本边界，拒绝文字越界，并固定图片尺寸和字号；结果在 [validation.json](validation.json)。本轮目视检查代表图，不对微信公众号实际粘贴效果作已验证声明。

## 公众号使用

推荐打开 index.html，点击“复制正文”，粘贴到公众号图文编辑器；随后把 assets/ 中对应 PNG 上传并替换正文里的本地图片，再检查手机预览。复制按钮依赖浏览器能力，失败时选中正文后按 Ctrl+C。本地路径不会变成公众号已托管的图片。

如更习惯 Word，可后续另行导出 DOCX 并使用公众号后台支持的导入方式。本轮不生成 Word、不连接公众号 API、不代发布。

制作时已使用公众号技能建立文章目录。其注入命令在当前 Windows 环境退出码为 1 且无诊断，遂采用本项目生成器输出独立预览，未读取或修改技能模板脚本。正文仍遵循单列、行内样式和 PNG 插图约定。

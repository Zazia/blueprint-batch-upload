# blueprint-batch-upload

面向 JGTGL 图纸管理系统的设计单位上传技能，覆盖初次上传、变更上传和竣工图上传，默认推进到对应页面“完成上传”。执行入口为 [SKILL.md](SKILL.md)。

**2026-10-27 需求更正（尚未同步实现）：点击“完成上传”须先由用户确认，除非已有明确授权该按钮动作。** 上述默认行为及当前技能正文仍是旧实现描述，不能当作新授权规则。查看 [情境、流程图、操作报告与常见坑点](docs/usage-walkthrough.md)；本轮仅整理介绍，未改执行逻辑。

## 当前工作范围

2026-10-14：依据设计 v0.3 完成技能及本地工具升级。原设计文件保持原样，其中“尚未实施”等文字保留为设计阶段记录；实际实施和验证状态见 [实施记录](docs/implementation.md)。

- 直接改成品包名，保存跨版本映射，不读取或同步包内内容，不重新整理图纸文件夹。
- 从系统快照建立初次或棕地项目账本，规划更新、增补和取消，检查新版目录/取消材料缺项。
- 保留原批量路径 A、精确 BPID 路径 B 与竣工必传经验，补充状态持久化、超时核查和中断恢复。
- 初次、增补、PDF/取消材料及各阶段收尾使用实际页面原生入口；本地工具负责预检、改名、对账，不独立登录或提交系统。

本轮通过离线测试，未操作生产工程；原技能竣工实测经验继续沿用。新增流程还需在实际授权上传任务中核对页面和服务器结果，不能把本地验证当成在线成功。

## 文档入口

- [技能效用介绍：真实情境、流程图与完成报告](docs/usage-walkthrough.md)
- [两个预留接口：图纸前置处理、变更动作识别](docs/reserved-interfaces.md)
- [工作约定](AGENTS.md)
- [需求与现状分析](docs/requirements.md)
- [技能完善设计](docs/design.md)
- [图纸目录管理与棕地接手设计](docs/catalog-management-design.md)
- [任务清单](docs/tasks.md)
- [阶段计划](docs/plan.md)
- [资料索引与依据](docs/sources.md)
- [准备图纸技能预留设计](docs/prepare-blueprints-design.md)
- [升级实施与验证记录](docs/implementation.md)
- [本地工具与数据格式](references/local-tools.md)

## 运行环境

**安利使用 uv**：本项目统一通过 uv 管理 Python 版本、环境和依赖，不使用 pip、venv、poetry 或 conda。

Python 3.10+，脚本仅使用标准库；本次在 Python 3.12 验证。执行前阅读技能说明，按真实快照和文件清单规划：

```powershell
uv run --python 3.12 scripts/upload_plan.py --help
uv run --python 3.12 scripts/upload_plan.py --project "D:/项目资料/upload-state" sync "D:/项目资料/snapshot.json"
uv run --python 3.12 scripts/upload_plan.py --project "D:/项目资料/upload-state" plan "D:/项目资料/snapshot.json" "D:/项目资料/request.json"
```

按返回 runId 执行 rename/report/record/finalize，数据格式及服务命令见 [本地工具](references/local-tools.md)。文件服务和证据接收服务均已参数化，启动时须指定实际站点、目录及运行令牌，不再使用历史机器路径。业务图纸、登录信息、抓包内容和运行输出不进入 Git。

离线回归测试：

```powershell
uv run --python 3.12 python -m unittest discover -s tests -v
node --test tests/browser.test.cjs
```

浏览器脚本的本地测试需支持 node:test、File 和 Blob 的 Node.js 20+；实际上传在授权的浏览器会话执行，不依赖 Node 连接生产站点。

## 版本管理

原始技能基线 `1932a7e`、设计 v0.3 `cdf3d36`；本轮升级使用 `codex/skill-upgrade` 分支。实施前建立记录，验证后单独提交。只使用本地仓库，不配置远端或推送。

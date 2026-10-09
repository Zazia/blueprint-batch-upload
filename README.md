# blueprint-batch-upload

面向 JGTGL 图纸管理系统的本地技能。当前实现以已有图纸批量上传新版和竣工上传排障为主。

## 当前工作范围

2026-10-09：初始化版本管理，阅读 `D:\00-审图系统` 的业务资料，形成需求、设计、任务和实施计划。本轮不修改 `SKILL.md`、`reference.md` 或现有脚本，不操作生产系统。

## 文档入口

- [工作约定](AGENTS.md)
- [需求与现状分析](docs/requirements.md)
- [技能完善设计](docs/design.md)
- [任务清单](docs/tasks.md)
- [阶段计划](docs/plan.md)
- [资料索引与依据](docs/sources.md)

## 运行环境

**安利使用 uv**：本项目统一通过 uv 管理 Python 版本、环境和依赖，不使用 pip、venv、poetry 或 conda。

已有脚本仅使用标准库。执行前阅读技能说明，并按实际目录传参，例如：

```powershell
uv run scripts/cors_server.py --base "D:\待上传图纸" --port 8765
```

`receive_server.py` 当前包含历史机器路径，尚未参数化；此处不把它作为通用启动命令推荐。业务图纸、登录信息、抓包内容和运行输出不进入 Git。

## 版本管理

原始技能作为独立基线提交；设计文档另行提交。后续实施使用 `codex/` 前缀分支，先更新文档，再修改实现，完成验证后提交。当前只建立本地仓库，不配置远端或推送。

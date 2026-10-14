# 9. SDK 确定性校验清单（测试工程师 P3 必检）

> 供 P3 独立验证使用。本清单是**确定性规则**（安装、版本、import 写法、配置格式），属于「三件事分工宪法」中允许脚本化/清单化的「结构与格式校验」，与 LLM 负责的对抗性用例设计（§8.1）互补，不互相替代。
> 规则来源：CodeBuddy Agent SDK 官方文档与官方验证实践。SDK 若有版本更新，以官方文档为准更新本清单（走技能进化协议 §7）。

## 9.0 适用判定

- 交付物**使用了 CodeBuddy Agent SDK**（TS 包 `@tencent-ai/agent-sdk` 或 Python 包 `codebuddy-agent-sdk`）→ 本清单**必检**，每条给出 通过/不通过 + 执行证据。
- 交付物**未使用该 SDK**（自研 harness、其他框架）→ 本清单记 **N/A**，写一行「未使用 CodeBuddy Agent SDK」即可，不得虚构检查结果。

## 9.1 TypeScript 项目（逐条判定）

| # | 检查项 | 通过标准 | 证据要求 |
|---|---|---|---|
| T1 | SDK 已安装 | `package.json` dependencies 含 `@tencent-ai/agent-sdk`，且 `node_modules/` 中实际存在 | 贴 `npm ls @tencent-ai/agent-sdk` 输出 |
| T2 | SDK 版本 | `>= 0.1.0` | 同上，版本号可见 |
| T3 | ES Modules | `package.json` 含 `"type": "module"` | 贴 package.json 相关行 |
| T4 | Node 版本 | `>= 18.0.0`（对照 `node -v` 实测值与 `engines` 字段如有） | 贴 `node -v` 输出 |
| T5 | import 写法 | `import { query } from '@tencent-ai/agent-sdk'`；不使用默认导入或错误命名导入 | grep 全仓库 import 语句，贴结果 |
| T6 | 会话 API 用法 | 多轮对话使用 `unstable_v2_createSession()`；简单问答用 `query()`；不得自造轮子重写会话管理 | 贴调用处代码行 |
| T7 | tsconfig 兼容 | `module`/`moduleResolution` 支持 ES Modules（如 `NodeNext`/`Bundler`），`target >= ES2020` | 贴 tsconfig.json |
| T8 | 鉴权配置 | API key 经 `.env`（`CODEBUDDY_API_KEY`）注入，`.env.example` 存在且 `.gitignore` 排除 `.env` | 贴文件列表与相关行 |

类型检查必须真跑：`npx tsc --noEmit`（退出码 0），输出贴入报告。

## 9.2 Python 项目（逐条判定）

| # | 检查项 | 通过标准 | 证据要求 |
|---|---|---|---|
| P1 | SDK 已安装 | `pip show codebuddy-agent-sdk` 可见（或 poetry/uv lock 中存在） | 贴命令输出 |
| P2 | Python 版本 | `>= 3.10` | 贴 `python3 --version` 输出 |
| P3 | import 写法 | 按官方文档的包名与符号导入，无拼写偏差 | grep import 语句 |
| P4 | 鉴权配置 | API key 经环境变量/.env 注入，`.env.example` 存在且 `.gitignore` 排除 `.env` | 贴相关文件 |
| P5 | 语法验证 | `python3 -m py_compile <入口文件>` 退出码 0 | 贴命令与输出 |

## 9.3 判定与处理

- 任一条**不通过** = 缺陷级问题（T1/P1 装不上、T5/P3 导入失败则升为**阻断**），计入测试报告问题清单，只报不改。
- 本清单**全绿不等于测试通过**：它只兜住确定性底线，对抗性验证（边界/异常/依赖失效，§8.1）仍须完整执行。

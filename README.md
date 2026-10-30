# GPT Web Stand-in · 6 Pro

让 Codex 将有明确边界的研究、复杂分析或方案复核自动委派给 ChatGPT 网页 6 Pro，等待并保存完整回答，核验关键证据后继续原任务。

当前为早期版本。运行中的宿主负责浏览器操作，本仓库提供可独立安装的 Skill 和本地记录助手。它不提供独立后台服务，也不保证每次隐式触发或任意网页状态下都无需人工介入。

## 工作方式

```text
Codex 选择 Skill
  → 整理问题并冻结材料
  → 宿主浏览器工具确认网页 6 Pro 并发送
  → 等待并收取同一会话的完整回答
  → 检查来源和材料版本
  → 记录采纳理由并继续原任务
```

Python 助手保存请求身份、材料快照、发送保留、观察和答案。它不控制浏览器、不调用 ChatGPT 网络接口，也不提供 `consult` 执行命令。任务记录可以在后续 Codex 回合中帮助恢复；没有常驻 worker 或自动唤醒功能。

## 依赖与兼容性

| 部分 | 要求及当前验证范围 |
|---|---|
| 宿主 | 支持加载 Skill、执行本地命令，并提供可操作实际网页的浏览器或 Computer Use 工具；只安装本仓库不会获得这些工具 |
| ChatGPT | 用户自己的可用登录态，并能在网页明确选择 6 Pro；不附带账号、订阅或凭据 |
| 本地助手 | Python 3.9+ 标准库；使用 `fcntl` 和 POSIX 文件能力，面向 macOS/Linux；原生 Windows 不支持 |
| 已实测的网页路线 | macOS 上运行中的 Codex，通过 `cua_repl` 原生 Chrome accessibility 完成纯文本咨询 |
| Linux 本地记录 | 已在 Ubuntu 24.04 / Python 3.12 运行离线记录测试；进程中断与重新读取范围见 [VALIDATION.md](VALIDATION.md) |
| 其他宿主浏览器路线 | 尚未实际验证；本地记录测试通过不等于浏览器会话恢复或端到端兼容 |
| 可选外部执行器 | 不依赖 Oracle、额外 MCP 服务、API key 或其他仓库代码 |

UI 布局和模型名称需要按当前可见页面确认。内置浏览器曾发生导航超时；宿主与用户允许时，可在任何发送尝试之前切换另一条可用 UI 路线。发送状态不确定时恢复原会话，不能换聊天重复发送。

## 本地安装与使用

需要安装的是 `skills/web-stand-in/` 整个目录，其中 5 个文件自包含，不需要仓库的测试或调研材料。

在 Codex 中，可让 `$skill-installer` 从 [zacksomething/web-stand-in](https://github.com/zacksomething/web-stand-in) 的 `skills/web-stand-in` 路径安装：

> 使用 $skill-installer，从 GitHub 仓库 zacksomething/web-stand-in 安装 skills/web-stand-in。

手动安装可将该目录放到目标项目的 `.agents/skills/` 或宿主配置的个人 Skill 目录；当前官方文档列出的用户目录是 `~/.agents/skills/`。已有同名 Skill 时先检查，避免覆盖或重复安装。目录发现和安装方式见 [OpenAI 官方文档](https://developers.openai.com/zh-Hans/docs/build-skills)。

安装后给 Codex 一个任务，例如：

> 使用 $web-stand-in，把这个方案中最需要独立审查的问题交给网页 6 Pro，核验推荐意见后继续完成修改。

`allow_implicit_invocation: true` 允许宿主在匹配任务中自行选用；是否触发由宿主判断。调用必须有可用浏览器工具、模型选项及任务授权。登录失效、验证码或缺少必要能力时，保留任务并报告具体障碍。

这是 GitHub Skill 源码仓库结构，尚未打包为可从插件目录安装的插件。官方建议用插件分发可复用技能；添加插件元数据也不会自动补齐本仓库未提供的浏览器控制器或后台执行器。[分发说明](https://developers.openai.com/zh-Hans/docs/build-skills#使用插件分发技能)

## 验证

从仓库根目录运行，不需要网络或 ChatGPT 账号：

```sh
python3 -B -m unittest discover -s tests -p 'test_task_record*.py' -v
```

详细范围见 [VALIDATION.md](VALIDATION.md)。Linux GitHub Actions 在 push、pull request 或手动触发时运行同一套测试，覆盖 Python 3.9 与 3.13；工作流配置不代表对应运行已经通过。

这里区分三个层次：

| 层次 | 当前证据与边界 |
|---|---|
| 本地记录助手在 Linux 运行 | 离线测试验证锁、原子替换、重复发送保护、损坏记录拒绝和新进程读取已有状态；不接触浏览器 |
| 浏览器宿主恢复原会话 | 仍需实测宿主退出重启、登录态、会话与回答绑定，以及回收完整回答；记录文件本身不能完成这些动作 |
| Mac 关机后云端持续工作 | 尚未验证；没有独立后台执行器。本次测试未连接 ECS，也未证明云端网络可达、任务持续调度或自动唤醒 |

## 仓库内容与运行数据

```text
README.md
LICENSE
VALIDATION.md
.gitignore
skills/web-stand-in/
  SKILL.md
  agents/openai.yaml
  references/browser-workflow.md
  references/task-records.md
  scripts/task_record.py
tests/test_task_record*.py
.github/workflows/local-records.yml
```

运行记录默认存放在任务项目的 `.web-stand-in/`，或用户指定的输出目录。记录会包含本机来源路径、所选材料和网页回答，应留在任务环境。本仓库仅收录上述维护文件，不包含真实会话链接、浏览器状态、账号数据或本地运行目录。若使用其他输出目录，维护者需相应更新忽略规则并检查提交内容。


## 许可证

采用 [MIT License](LICENSE)。当前版本提供 Skill 源码与本地记录助手，不附带插件安装清单或后台服务。

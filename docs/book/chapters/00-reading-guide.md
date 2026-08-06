# 如何使用本书

本书面向已经会使用 Git、终端和至少一种 Agent 开发工具的外部开发者。你不需要先读
LoopX Kernel 源码，也不需要理解所有 CLI 子命令。

## 你会完成什么

全书先用六章建立一套控制面心智模型，再进入两条实践主线：

```text
控制面基础
├── 接入现有 Git 项目
└── 开发者贡献
    ├── Control Plane、Capability 与 Domain State
    ├── Provider、Host/Runner、Projection、Docs 与 fixtures
    └── Extension 与独立 package lifecycle
```

基础篇依次覆盖：

1. 为什么一次 Session 不足以承载长程任务；
2. 普通会话、Host Goal 与 LoopX 分别拥有哪一层状态；
3. canonical state、workbench、event 与 read-only projection；
4. Todo 工作图、Gate、claim、lease、authority 与 Peer 协作；
5. 一轮受治理的 Turn 如何决定、执行、验证和写回；
6. retry、replan、self-repair、terminal closure 与运行边界。

完成基础篇后：

- 只想管理自己的项目，从[连接你的 Git 项目](./05-connect-existing-project.md)开始；
- 想给 LoopX 做任何公开贡献，从[开发者贡献地图与协议入口](./source-protocol-map.md)开始；
- 已经确定需要独立安装、启停和升级的 Provider/package，再进入
  [选择正确的放置位置](./08-extension-placement.md)。

项目接入与开发者贡献共享基础模型，但没有先后依赖。Extension 是开发者贡献中的一种交付和
lifecycle 选择，不是所有贡献的默认终点。

## 章节如何组织

每章优先回答四个问题：

1. 读者此时要解决什么问题；
2. 成功后能观察到什么；
3. 哪些概念足以解释这些行为；
4. 正常路径失败时从哪里恢复。

命令片段会标明其性质：

- **可直接运行：** 已在标注的 LoopX 版本上核对命令表面；
- **基于官方 scaffold：** 示例只给出完成当前任务所需的领域改动、协议和验证，不依赖单独的
  配套练习仓库；
- **为解释而简化：** 用于说明状态关系，不应直接写入生产配置。

## 权威来源

本书拥有教学顺序和解释，不拥有 LoopX 的版本化行为：

| 内容 | 权威来源 |
| --- | --- |
| CLI 参数、协议和 runtime 行为 | LoopX 发布物、`--help` 与官方仓库 |
| 学习路径、scaffold 导读、概念解释与取舍建议 | 本书 |
| 你的项目事实 | Git、CI、外部服务和项目自己的事实源 |

当本书与当前发布版本冲突时，先以发布物为准，再提交文档修正。不要为了让教程“跑通”而绕过
新版本的权限或生命周期检查。

## 版本基线

当前内容以 LoopX GitHub release `v0.4.1` 为发布锚点；本地命令示例已在 `loopx 0.4.0` CLI
表面核对。发布标签、已安装 CLI 与源码 checkout 可能处于不同 revision，因此以下表面尤其需要
按实际环境复核：

- 安装与升级；
- Host 启动方式；
- `start-goal` guided packet；
- Codex App heartbeat 与 Codex CLI visible Goal；
- Extension manifest 与生命周期命令。

运行书中命令前先执行：

```bash
loopx --version
loopx doctor
```

如果版本不同，先查看当前命令帮助和官方 release notes，再判断差异是文档漂移、发布差异还是
产品行为变化。本书不猜测不同版本标识之间的发布含义。

## 本书的边界

开发者贡献部分覆盖外部贡献者需要的 placement、协议地图、规则修改、Capability/Provider、
Host/Runner、Projection/Docs/fixtures、Extension lifecycle、验证与 PR，不复制完整九讲核心
维护者课程，也不提供完整 CLI reference。生产级 effectful provider、企业内部案例和 benchmark
live operation 不进入当前主线。需要这些能力时，应回到官方源码、协议和具体项目的事实源。

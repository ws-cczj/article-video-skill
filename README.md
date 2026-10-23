# article-video-skill

将学术文献转为便于学习的视频总结，让研究问题、核心方法、关键结果与局限更容易理解和回顾。

本项目是面向 AI 编程助手的 **Skill**。它指导助手从文献出发，整理可追溯的知识要点，编写旁白与分镜，并在具备相应工具时生成视频。

> 当前阶段：基础架构。已提供工作流指令、证据记录模板和视频脚本模板；尚未集成 PDF 解析、语音合成或视频渲染程序。仅安装本 Skill 不会自动获得这些能力，也没有一键生成视频的命令。

## 工作流程

1. **读取文献**：接收 PDF、论文链接或正文，记录标题、作者、年份、来源与可访问范围。
2. **建立证据记录**：提炼研究问题、方法、主要结果和局限，为关键结论标注页码、章节或图表位置。
3. **设计视频**：根据受众、语言和时长组织故事线，解释必要的术语和公式。
4. **生成脚本**：产出旁白、字幕、分镜、画面说明与来源标注。
5. **制作与检查**：在实际具备 TTS、字幕和渲染工具时制作视频，核对内容、字幕同步和画面可读性。

默认使用中文讲解，保留论文英文标题、公式、变量和关键术语。视频帮助理解原文，不替代原文阅读。

## 安装与使用

以 Codex 为例，将仓库克隆到技能目录；若设置了 `CODEX_HOME`，请使用该目录下的 `skills`。

**PowerShell：**

```powershell
git clone https://github.com/ws-cczj/article-video-skill.git "$HOME/.codex/skills/article-video-skill"
```

**macOS / Linux：**

```bash
git clone https://github.com/ws-cczj/article-video-skill.git ~/.codex/skills/article-video-skill
```

重新打开支持技能发现的助手会话，然后提供文献并调用：

```text
请使用 $article-video-skill，将这篇论文整理为面向本科生的 5 分钟中文学习视频。
先给出带原文定位的要点、完整旁白和分镜；如果环境具备渲染工具，再生成视频。
```

也可以指定语言、受众、视频时长、横屏/竖屏及输出目录。只有摘要时，输出会明确限制在摘要范围。

## 目录结构

```text
article-video-skill/
├── SKILL.md                         # 技能入口与工作流
├── agents/openai.yaml               # 助手界面元数据
├── assets/
│   ├── evidence-template.md         # 原文证据与结论记录
│   └── storyboard-template.md       # 旁白、字幕和分镜模板
├── DEVELOPMENT.md                   # 现有协作者的同步与推送方法
└── LICENSE                          # GPL-2.0 完整许可证
```

## 输出约定

每次任务使用独立输出目录，通常包含：

- `evidence.md`：文献信息、证据定位、关键结果、局限与待核实项。
- `storyboard.md`：分镜、旁白、字幕文本、画面设计、时间轴和引用。
- `subtitles.srt`：语音时间轴确定后生成的字幕。
- `video.mp4`：仅在已完成渲染和检查时交付。

输入论文和生成的视频默认不提交到本仓库。不得编造实验数据、引用或原文结论；示意动画应注明“示意”。原论文、图表、音频和其他第三方素材仍受各自权利及许可约束。

## 开发方式

本项目目前由已授权的协作者直接开发和推送，不开放外部贡献入口。Issues、Discussions 和 Pull Requests 均已关闭。

协作者直接同步和推送 `main`，无需 PR 或审核；推送前合入远程最新提交，遇到冲突时先解决并验证再推送。操作步骤见 [开发说明](DEVELOPMENT.md)。禁止强制推送及删除 `main`，以保护双方已提交的工作。

## 许可证

本项目采用 **GNU General Public License v2.0 only**（`GPL-2.0-only`），完整条款见 [LICENSE](LICENSE)。第三方素材不因存放于项目中而自动改用本许可证。

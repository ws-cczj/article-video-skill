# article-video-skill

将学术文献转为便于学习的视频总结，让研究问题、核心方法、关键结果与局限更容易理解和回顾。

本项目是面向 AI 编程助手的 **Skill**。它指导助手先生成规范排版的中文文献总结，再编写旁白、按内容选择视觉方案和组织分镜，并在具备相应工具时生成、审查和微调视频。

> 当前阶段：可运行的制作原型。提供 PDF 提取、中文总结与 XeLaTeX 编译、可选神经配音、语音触发的连续对象动画和带字幕视频渲染。高质量路径支持原生4K抗锯齿矢量与120fps，默认按中文讲解补足句间停顿；镜头时长覆盖末尾动画。本地与在线配音接入同一渲染器，全部音频在编码前统一格式，整片PCM处理后最终一次编码。论文理解、证据核查与成片审查仍由助手完成。详见 [本地制作说明](references/local-production.md) 与 [讲解设计](references/explainer-style.md)。

## 工作流程

1. **读取文献**：接收 PDF、论文链接或正文，记录标题、作者、年份、来源与可访问范围。
2. **建立证据记录**：提炼研究问题、方法、主要结果和局限，为关键结论标注页码、章节或图表位置。
3. **中文论文式总结**：无论输入为中文或英文，先产出中文总结，按论文式结构组织内容，规范段落、标点、符号、单位、公式和引用；有可用编译器时同时生成并检查 PDF。
4. **讲解与视觉规划**：将总结改写为适合受众的旁白，统一整片审美，再按内容选择流程、对比、概念、数据或公式等镜头表达方式。
5. **生成脚本**：产出旁白、字幕、分镜、画面说明与来源标注。
6. **制作、审查与微调**：在实际具备 TTS、字幕和渲染工具时制作视频，审查内容、学习效果、视觉质量和同步情况，记录时间点与镜头并局部修正。

默认使用中文讲解，保留论文英文标题、公式、变量和关键术语。视频帮助理解原文，不替代原文阅读。

中文总结是独立于视频旁白的首要交付：默认包含摘要、关键词、引言、方法或理论框架、结果或论证、讨论与局限、结论和参考文献，并按论文类型调整。默认使用 A4、25 mm 页边距、正文小四号、1.5 倍行距和首行缩进两字；这是项目默认格式，用户提供的学校或期刊模板优先。详见 [中文总结与排版规范](references/chinese-summary-format.md)。

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
先生成带原文依据、规范排版的中文论文式总结，再编写旁白、选择视觉方案和组织分镜；工具可用时生成 PDF 和视频，并审查、微调实际视频。
```

也可以指定语言、受众、视频时长、横屏/竖屏及输出目录。只有摘要时，输出会明确限制在摘要范围。

## 目录结构

```text
article-video-skill/
├── SKILL.md                         # 技能入口与工作流
├── agents/openai.yaml               # 助手界面元数据
├── scripts/                         # PDF提取、总结、配音、FFmpeg下载、音频转换与渲染
├── requirements.txt                 # Python依赖；不包含外部程序
├── requirements-neural.txt          # 可选在线神经配音依赖
├── assets/
│   ├── evidence-template.md         # 原文证据与结论记录
│   ├── chinese-summary-template.tex # 中文论文式总结排版源稿
│   └── storyboard-template.md       # 旁白、字幕和分镜模板
├── references/
│   ├── chinese-summary-format.md    # 中文总结结构与排版规范
│   ├── local-production.md          # 本地命令、数据结构与验收边界
│   └── explainer-style.md           # 例子贯穿、连续动画与配音质量
├── DEVELOPMENT.md                   # 现有协作者的同步与推送方法
└── LICENSE                          # GPL-2.0 完整许可证
```

## 输出约定

每次任务使用独立输出目录，通常包含：

- `evidence.md`：文献信息、证据定位、关键结果、局限与待核实项。
- `summary.md`：独立的中文论文式总结，不以旁白或要点列表代替。
- `summary.tex`：与总结正文一致的可编辑排版源稿。
- `summary.json`：本地生成器使用的共同内容源，便于同步维护正文和排版稿。
- `summary.pdf`：仅在具备编译条件并完成页面检查后交付；无法编译时明确排版未验收。
- `storyboard.md`：分镜、旁白、字幕文本、画面设计、时间轴和引用。
- `storyboard.json`：渲染器使用的可执行分镜；`audio/`保存本地配音和逐句计时。
- `subtitles.srt`：语音时间轴确定后生成的字幕。
- `video.mp4`：仅在已完成渲染和检查时交付。
- `review.md`：实际视频审查的问题、时间点、镜头编号、修改建议及复查结果；未能完成的检查如实标明。

输入论文和生成的视频默认不提交到本仓库。不得编造实验数据、引用或原文结论；示意动画应注明“示意”。原论文、图表、音频和其他第三方素材仍受各自权利及许可约束。

## 开发方式

本项目目前由已授权的协作者直接开发和推送，不开放外部贡献入口。Issues、Discussions 和 Pull Requests 均已关闭。

协作者直接同步和推送 `main`，无需 PR 或审核；推送前合入远程最新提交，遇到冲突时先解决并验证再推送。操作步骤见 [开发说明](DEVELOPMENT.md)。禁止强制推送及删除 `main`，以保护双方已提交的工作。

## 许可证

本项目采用 **GNU General Public License v2.0 only**（`GPL-2.0-only`），完整条款见 [LICENSE](LICENSE)。第三方素材不因存放于项目中而自动改用本许可证。

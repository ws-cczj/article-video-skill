# 贡献指南

欢迎改进 article-video-skill。可以贡献文档、技能指令、模板、工具集成和使用反馈。请友善交流，围绕具体问题讨论，并尊重不同背景的贡献者。

## 提出问题与建议

- 使用 Issue 模板说明问题、复现步骤、预期行为与实际结果。
- 开放式想法和使用交流可放在 Discussions。
- 较大的工具集成建议先建 Issue，说明输入、输出、依赖、运行成本和验证方法。
- 不要在 Issue、PR 或示例中上传密钥、个人隐私、未公开论文或无权再分发的素材。

## 两人协作：克隆、开发与提交

拥有仓库 Write 权限的协作者可直接向本仓库的开发分支推送，无需 Fork。每个人使用自己的 GitHub 账号认证；提交者不能批准自己的 PR。

首次使用，先安装 Git，并配置自己的提交身份：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的 GitHub 邮箱或 GitHub 提供的 noreply 邮箱"
git clone https://github.com/ws-cczj/article-video-skill.git
cd article-video-skill
```

首次推送时按 Git 凭据管理器的提示登录自己的 GitHub 账号；GitHub CLI 用户也可使用 `gh auth login` 和 `gh auth setup-git`。Git 提交身份不会授予仓库权限。

每次开始一个新任务，先在工作区干净时同步 `main`，再创建自己的开发分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/pdf-parser
```

修改后检查、提交并推送该开发分支。以下以修改 `SKILL.md` 为例，按实际修改选择暂存文件：

```bash
git diff --check
git diff
git add SKILL.md
git commit -m "feat: improve paper extraction guidance"
git push -u origin feature/pdf-parser
```

在 GitHub 打开仓库，点击 **Compare & pull request**，选择 `base: main`、`compare: feature/pdf-parser`，填写变更和验证结果，并请求另一位成员审核。已安装 GitHub CLI 时，也可运行：

```bash
gh pr create --base main --head feature/pdf-parser --title "Improve paper extraction guidance" --body "说明变更内容、验证结果和关联 Issue"
```

同一个 PR 的后续修改继续提交到同一分支，再运行 `git push`，PR 会自动更新。每个独立任务使用新的分支名；不要直接向 `main` 推送。

## main 分支保护与审核

`main` 使用启用状态的 GitHub 规则集，要求：

- 所有修改通过 PR 合并，至少需要一位有资格的其他成员批准。
- 新的可审核提交使已有批准失效，需要重新审核。
- 所有代码审核讨论解决后才能合并。
- 禁止强制推送和删除 `main`。
- 不设绕过名单，管理员也需遵守。

规则对双方对称适用：协作者提交 PR，由维护者审核；维护者提交 PR，由协作者审核。目前未设置 CODEOWNERS 或强制 CI 检查；新增成员后，如需固定审核人，可重新设计审核规则。

审核者检查 **Files changed**、相关功能和验证结果，再通过 **Review changes** 选择 **Approve** 或 **Request changes**。AI 可以协助审查、测试和修复；GitHub 正式批准由有权限的账号提交，最终合并由维护者确认。

## 拉取已合并的修改

先提交或妥善保存当前工作，再切回 `main` 更新：

```bash
git switch main
git pull --ff-only origin main
```

`git fetch origin` 只更新远程分支信息，不修改当前工作文件。若要把 `main` 的更新带到尚未完成的开发分支，按下面的合并流程操作。

## 在开发分支解决冲突

先确保当前修改已提交，再将最新的 `main` 合入 PR 分支：

```bash
git fetch origin
git switch feature/pdf-parser
git merge origin/main
```

若有冲突，运行 `git status` 找到冲突文件，结合双方意图编辑内容，移除 `<<<<<<<`、`=======`、`>>>>>>>` 标记。不要整批选择一方内容来掩盖冲突。完成后暂存已解决的文件、验证并提交，例如：

```bash
git add SKILL.md
git diff --cached --check
git status
git commit -m "merge: resolve conflicts with main"
git push
```

按实际冲突文件调整 `git add`，并运行与变更相关的检查。需要放弃本次尚未完成的合并时可运行 `git merge --abort`。PR 更新后需重新审核最新内容；冲突解决不代表审核通过。

## 外部贡献者通过 Fork 提交 Pull Request

1. Fork 本仓库，克隆自己的 Fork。
2. 创建描述性的分支，例如 `git switch -c docs/improve-storyboard`。
3. 完成单一主题的修改，并更新受影响的文档。
4. 检查修改后提交，再推送到自己的 Fork：

   ```bash
   git diff --check
   git add <修改的文件>
   git commit -m "docs: improve storyboard guidance"
   git push -u origin docs/improve-storyboard
   ```

5. 向本仓库的 `main` 分支提交 PR，说明解决的问题、变更内容及验证结果。

公开仓库允许通过 Fork 和 PR 参与，无需直接写入权限。维护者审核后合并；请不要在 PR 中夹带生成视频、大型素材或与主题无关的修改。

## 验证要求

- 修改 `SKILL.md` 时，保留有效的 YAML frontmatter，确保 `name` 与技能目录名一致，模板链接可用。
- 文档或模板修改：检查示例、相对链接与字段，运行 `git diff --check`。
- 新增工具或脚本：说明版本与安装方式，提供可复现的运行命令；使用有权分享的最小样例验证输入、输出和失败行为。
- 涉及视频：检查事实依据、数值及单位、旁白与字幕同步、中文字体和画面可读性；说明未验证的部分。
- 不得将计划中的能力描述为已实现，也不要编造测试通过记录。

## 许可证

提交贡献表示你有权提供该内容，并同意将原创贡献按本项目的 GPL-2.0-only 许可证分发。第三方材料需记录来源、许可与署名要求；不要提交与本项目分发条件不兼容的材料。

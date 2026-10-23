# 协作者开发说明

仅已授权的成员可以向本仓库推送。现有成员直接使用 `main`，无需 PR 或审核。Issues、Discussions、Pull Requests 已关闭；仓库保持公开，GPL-2.0-only 许可证继续适用。

## 首次克隆

安装 Git，使用自己的 GitHub 账号认证，再执行：

```bash
git clone https://github.com/ws-cczj/article-video-skill.git
cd article-video-skill
git config user.name "自己的名字"
git config user.email "自己的 GitHub 邮箱或 noreply 邮箱"
```

首次推送时按 Git 凭据管理器提示登录。若使用 GitHub CLI，也可执行 `gh auth login` 和 `gh auth setup-git`。提交身份与仓库写入权限是不同的设置。

## 每次开始工作

先确保当前修改已提交或妥善保存，再切换并同步主分支：

```bash
git switch main
git pull --ff-only origin main
```

如果本地已有尚未推送的提交，导致 `--ff-only` 失败，使用下面的合并流程保留双方提交。

## 提交与推送

以下以修改 `SKILL.md` 为例，按实际修改选择暂存文件：

```bash
git diff --check
git diff
git add SKILL.md
git commit -m "feat: improve paper summary workflow"
git pull --no-rebase origin main
git push origin main
```

`git pull --no-rebase` 会获取并合入远程提交；兼容的修改通常可以自动合并，内容冲突则需先处理。只有拉取、合并和必要检查成功后才继续推送。

如果拉取后另一位成员又推送了新提交，本次推送可能再次被拒绝；重新执行拉取、处理冲突和推送即可。不要使用 `--force` 或 `--force-with-lease` 覆盖主分支。

## 解决冲突

出现冲突后执行 `git status`，逐个编辑标记为冲突的文件，结合双方修改保留正确内容，并移除 `<<<<<<<`、`=======`、`>>>>>>>` 标记。不要直接丢弃一方内容来消除冲突。

例如冲突发生在 `SKILL.md`，解决后执行：

```bash
git add SKILL.md
git diff --cached --check
git status
git commit -m "merge: resolve conflicts with main"
git push origin main
```

按实际文件调整 `git add`，确认所有冲突均已解决，并执行与变更相关的验证。若需要放弃尚未完成的合并，可执行 `git merge --abort`，之后检查工作区状态。

Git 能发现部分文本冲突，但不能发现所有逻辑冲突。即使自动合并成功，也应检查双方修改是否能一起正常工作。有疑难冲突时，可将工作交给助手处理；处理完成后再推送。

## 仅拉取已发布的更新

在干净的 `main` 工作区执行：

```bash
git pull --ff-only origin main
```

仓库只保留禁止强制推送和禁止删除 `main` 的保护规则，没有批准或 PR 要求。

# Git 迭代管理与回滚说明

本文档用于说明如何用 Git 管理当前前列腺术中超声可视化工具的代码迭代、版本隔离和回滚。

当前工作区里虽然存在 `.git` 目录，但缺少 `HEAD` 和 `config`，`git rev-parse --is-inside-work-tree` 会报错。因此它目前不能作为一个正常 Git 仓库使用。建议先按下面步骤重新初始化或修复。

## 1. 建议管理范围

建议 Git 只管理代码、配置模板、说明文档和少量测试 JSON。

建议纳入 Git：

```text
code/
spacing.yaml
spacing_new.yaml
data/jpg/S00002/cutting_plan_import_more_points_*.json
```

不建议纳入 Git：

```text
data/jpg/              # 大量图像数据
data/seg/              # .nii.gz 分割数据
dataset/               # 原始数据集
*.nii.gz
*.jpg
*.png
__pycache__/
*.pyc
```

原因是医学图像和分割文件通常很大，不适合直接放进 Git。后续如果确实要版本化大文件，建议使用 Git LFS。

## 2. 初始化仓库

如果当前 `.git` 是坏的空目录，可以先确认里面没有重要内容：

```powershell
Get-ChildItem -Force .git
```

如果确认为坏目录，可以删除后重新初始化：

```powershell
Remove-Item -Recurse -Force .git
git init
```

如果不想删除，也可以先重命名备份：

```powershell
Rename-Item .git .git_broken_backup
git init
```

设置用户信息：

```powershell
git config user.name "your-name"
git config user.email "your-email@example.com"
```

## 3. 添加 `.gitignore`

建议在项目根目录创建 `.gitignore`：

```gitignore
__pycache__/
*.pyc
*.pyo
*.pyd

.venv/
venv/
env/

*.nii.gz
*.jpg
*.jpeg
*.png
*.bmp

data/seg/
dataset/

~$*
*.tmp
*.log
```

如果希望保留少量测试 JSON，可以不要忽略整个 `data/`，而是只忽略大文件类型和大目录。

## 4. 第一次提交

先查看当前状态：

```powershell
git status
```

添加代码和文档：

```powershell
git add code spacing.yaml spacing_new.yaml
```

如果要把测试导入 JSON 也纳入版本：

```powershell
git add data/jpg/S00002/cutting_plan_import_more_points_1.json
git add data/jpg/S00002/cutting_plan_import_more_points_2.json
git add data/jpg/S00002/cutting_plan_import_more_points_mixed.json
```

提交：

```powershell
git commit -m "Initialize prostate ultrasound viewer"
```

## 5. 推荐分支策略

主分支保留稳定版本：

```powershell
git branch -M main
```

每次做一个新功能，从 `main` 新建功能分支：

```powershell
git switch -c feature/iter3-dynamic-json
```

功能完成并验证后，合并回 `main`：

```powershell
git switch main
git merge feature/iter3-dynamic-json
```

如果功能不满意，可以直接丢弃分支：

```powershell
git branch -D feature/iter3-dynamic-json
```

## 6. 当前项目的版本迭代建议

当前已有 v2 和 v3：

```text
code/prostate_us_viewer_iter2.py
code/us_viewer_iter2/

code/prostate_us_viewer_iter3.py
code/us_viewer_iter3/
```

建议每个大版本独立提交：

```powershell
git add code/prostate_us_viewer_iter2.py code/us_viewer_iter2
git commit -m "Add iter2 viewer with cutting plan support"

git add code/prostate_us_viewer_iter3.py code/us_viewer_iter3
git commit -m "Add iter3 viewer with dynamic JSON import"
```

给稳定版本打标签：

```powershell
git tag v2-stable
git tag v3-dynamic-json
```

查看标签：

```powershell
git tag
```

## 7. 每次修改前后的基本流程

修改前：

```powershell
git status
```

看当前有哪些未提交修改：

```powershell
git diff
```

修改后先编译验证：

```powershell
python -m py_compile .\code\prostate_us_viewer_iter3.py .\code\us_viewer_iter3\main_window.py
```

查看改动：

```powershell
git diff
```

分批提交：

```powershell
git add code/us_viewer_iter3/main_window.py
git commit -m "Support index-keyed cutting plan import"
```

## 8. 提交粒度建议

不要把很多无关改动塞进一个提交。建议按功能拆：

```text
1. Add iter3 package
2. Support transverse-only JSON import
3. Support index-keyed points with name field
4. Separate iter2 and iter3 state files
5. Add Git workflow documentation
```

这样回滚时可以只回滚某个功能，而不是整批撤销。

## 9. 查看历史

查看简洁历史：

```powershell
git log --oneline --graph --decorate --all
```

查看某个提交具体改了什么：

```powershell
git show <commit-id>
```

查看某个文件历史：

```powershell
git log --oneline -- code/us_viewer_iter3/main_window.py
```

查看某个文件在某次提交中的内容：

```powershell
git show <commit-id>:code/us_viewer_iter3/main_window.py
```

## 10. 回滚未提交修改

如果某个文件改坏了，还没有提交，可以恢复单个文件：

```powershell
git restore code/us_viewer_iter3/main_window.py
```

恢复整个工作区的未提交修改：

```powershell
git restore .
```

如果已经 `git add`，但还没提交，先取消暂存：

```powershell
git restore --staged code/us_viewer_iter3/main_window.py
```

然后再恢复文件：

```powershell
git restore code/us_viewer_iter3/main_window.py
```

## 11. 回滚到某个历史版本查看

临时切换到某个提交：

```powershell
git switch --detach <commit-id>
```

这适合临时查看旧版本。查看完回主分支：

```powershell
git switch main
```

切换到某个标签：

```powershell
git switch --detach v3-dynamic-json
```

## 12. 回滚某个提交

如果一个提交已经进入主分支，并且想保留历史，推荐用 `git revert`：

```powershell
git revert <commit-id>
```

它会生成一个新的提交，用来抵消旧提交的内容。这种方式适合已经共享给别人或已经推送到远端的分支。

## 13. 回退本地分支到旧提交

如果提交还没有推送，也没有别人依赖，可以使用 reset。

回退提交但保留文件改动：

```powershell
git reset --soft <commit-id>
```

回退提交并把改动放回工作区：

```powershell
git reset --mixed <commit-id>
```

彻底回退到某个提交，丢弃之后所有改动：

```powershell
git reset --hard <commit-id>
```

`git reset --hard` 会丢弃未保存修改，使用前必须确认 `git status`。

## 14. 只恢复某个文件到旧版本

例如只把 v3 主窗口恢复到某个历史版本：

```powershell
git restore --source <commit-id> -- code/us_viewer_iter3/main_window.py
```

然后提交这个恢复：

```powershell
git add code/us_viewer_iter3/main_window.py
git commit -m "Restore iter3 main window from previous version"
```

## 15. 使用 stash 临时保存修改

如果当前正在改代码，但临时要切换分支：

```powershell
git stash push -m "wip iter3 import logic"
```

查看 stash：

```powershell
git stash list
```

恢复最近一次 stash：

```powershell
git stash pop
```

只应用但不删除 stash：

```powershell
git stash apply
```

## 16. 远端仓库

如果使用 GitHub/GitLab，可以添加远端：

```powershell
git remote add origin <remote-url>
git push -u origin main
```

后续推送：

```powershell
git push
```

拉取远端更新：

```powershell
git pull
```

## 17. 推荐日常命令清单

查看状态：

```powershell
git status
```

查看改动：

```powershell
git diff
```

提交：

```powershell
git add <file>
git commit -m "message"
```

看历史：

```powershell
git log --oneline --graph --decorate --all
```

撤销未提交文件：

```powershell
git restore <file>
```

回滚已提交功能：

```powershell
git revert <commit-id>
```

临时保存：

```powershell
git stash push -m "message"
```

## 18. 针对本项目的建议习惯

1. 每次让 Codex 修改前，先提交当前稳定状态。
2. 每次完成一个明确功能后，立刻提交。
3. v2 和 v3 分开提交，不混在一个提交里。
4. 数据 JSON 和代码分开提交。
5. 大图像、大 mask 不进 Git。
6. 能用 `git revert` 就不要优先用 `git reset --hard`。
7. 每次运行前先用 `python -m py_compile` 做基础检查。

推荐一次修改的完整流程：

```powershell
git status
git switch -c feature/some-change

# 修改代码
python -m py_compile .\code\prostate_us_viewer_iter3.py .\code\us_viewer_iter3\main_window.py

git diff
git add code/us_viewer_iter3/main_window.py
git commit -m "Describe the change"

git switch main
git merge feature/some-change
git tag v3-some-change
```


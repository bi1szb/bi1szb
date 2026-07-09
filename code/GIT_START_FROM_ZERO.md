# 从零开始使用 Git 管理一个目录

本文档说明：如果换到另一个目录，如何从零开始用 Git 管理代码、提交版本，并推送到 GitHub。

## 1. 进入项目目录

先进入你想管理的项目根目录：

```powershell
cd D:\your_project
```

确认当前目录内容：

```powershell
Get-ChildItem
```

这个目录应该是项目根目录，例如里面有 `code/`、`README.md`、配置文件等。

## 2. 初始化 Git 仓库

```powershell
git init
```

设置用户名和邮箱：

```powershell
git config user.name "bi1szb"
git config user.email "bi1szb@163.com"
```

这两个配置会写到当前仓库里，用于记录提交作者。

## 3. 创建 `.gitignore`

`.gitignore` 用来告诉 Git 哪些文件不要提交。

Python 项目可以先用这个：

```gitignore
__pycache__/
*.pyc

.venv/
venv/

*.log
*.tmp

data/
dataset/
*.jpg
*.png
*.nii.gz
```

如果你的项目需要提交少量测试 JSON，不要直接忽略整个 `data/`，可以只忽略大文件类型：

```gitignore
*.jpg
*.png
*.nii.gz
data/seg/
dataset/
```

## 4. 查看当前状态

```powershell
git status
```

这个命令会显示哪些文件还没有被 Git 管理，哪些文件已经修改。

## 5. 添加文件

添加当前目录下所有未忽略文件：

```powershell
git add .
```

更推荐只添加你明确想管理的文件：

```powershell
git add code README.md .gitignore
```

如果只想添加某个文件：

```powershell
git add code/prostate_us_viewer_iter3.py
```

## 6. 第一次提交

```powershell
git commit -m "first commit"
```

提交后，这个版本就被 Git 记录下来了。以后可以回滚到这个版本。

## 7. 设置主分支名

```powershell
git branch -M main
```

现在 GitHub 默认主分支一般叫 `main`。

## 8. 连接 GitHub 仓库

先在 GitHub 上新建一个空仓库。

然后在本地执行：

```powershell
git remote add origin https://github.com/用户名/仓库名.git
```

例如：

```powershell
git remote add origin https://github.com/bi1szb/bi1szb.git
```

查看远端是否设置成功：

```powershell
git remote -v
```

## 9. 推送到 GitHub

```powershell
git push -u origin main
```

注意：GitHub 不支持用账号密码直接推送。

推荐使用以下方式之一：

- Git Credential Manager 浏览器登录
- Personal Access Token
- SSH key

不要把密码写进命令，也不要把密码发给别人。

## 10. 以后每次修改的流程

查看状态：

```powershell
git status
```

查看具体改了什么：

```powershell
git diff
```

添加修改：

```powershell
git add .
```

提交：

```powershell
git commit -m "说明这次改了什么"
```

推送：

```powershell
git push
```

## 11. 从零开始最小命令版

如果你已经知道要提交哪些文件，可以按下面这组命令快速开始：

```powershell
cd D:\your_project
git init
git config user.name "bi1szb"
git config user.email "bi1szb@163.com"
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/bi1szb/仓库名.git
git push -u origin main
```

## 12. 推荐习惯

1. 每次开始大改前，先提交当前稳定版本。
2. 每次完成一个明确功能后，马上提交。
3. 不要把数据集、大图像、模型文件直接提交到 Git。
4. 先用 `git status` 检查，再 `git add`。
5. 提交信息要写清楚这次改了什么。
6. 推送前确认没有把密码、token、隐私数据提交进去。


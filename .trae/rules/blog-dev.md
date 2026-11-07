# TDLAI 博客开发准则

本仓库是基于 Hugo + hugo-jijian 主题的个人博客（GitHub Pages 自动部署）。每次对话必须遵守以下规则。

## 1. 环境与目录

- 日常开发必须在本目录（`D:\workspace\03-blog`）下进行。
- 本地预览：`hugo server -D`，访问 http://localhost:1313/ 。
- Hugo 与 Go 安装在 `D:\workspace\huanjing`，主题模块通过 `HUGO_MODULE_PROXY=https://goproxy.cn` 拉取。

## 2. 新增文章规范

- 所有新文章必须存放在 `content/posts/` 下。
- 文件名格式：`YYYY-MM-DD-文章英文缩写.md`（例如 `2026-11-05-hugo-pages-fix.md`）。

## 3. Front Matter 规范

文章头部必须包含以下字段：

```yaml
---
title: "文章标题"
date: YYYY-MM-DD
categories: ["工具与攻略"]   # 只能是：工具与攻略 / AI+教育 / 前沿观察 之一
tags: ["标签1", "标签2"]
---
```

- `categories` 只能取 `工具与攻略`、`AI+教育`、`前沿观察` 之一。
- `tags` 自由填写，至少一个。

## 4. 图片资源

- 文章插图统一放在 `static/images/` 目录下。
- Markdown 中引用使用绝对路径：`/images/xxx.jpg`。

## 5. 提交规范

- 完成修改后，用**中文**写一句清晰的 commit message。
- 然后自动执行：`git add .` → `git commit` → `git push`（推送到 `main` 分支）。
- 推送后 GitHub Actions 会自动构建并部署到线上。

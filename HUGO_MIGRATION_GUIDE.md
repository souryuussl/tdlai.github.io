# TDLAI Hugo 迁移指南

## 迁移结果

本目录已经准备了 Hugo + 极简（hugo-jijian）主题项目配置、菜单分类、第一篇 Markdown 文章和 GitHub Actions 部署工作流。

- Hugo 配置：`hugo.yaml`
- 极简（hugo-jijian）：通过 Hugo Modules 引入，见 `hugo.yaml` 和 `go.mod`
- 文章：`content/posts/2026-11-04-first-post.md`
- 首页内容：`content/_index.md`
- 菜单分类页：`content/categories/{tools,education,frontier}/_index.md`
- 自定义样式：`assets/css/extended/custom.css`
- 图片素材：`static/images/`
- GitHub Actions：`.github/workflows/hugo.yaml`
- 原始 HTML：已归档至 `legacy/`（2026-11-07），不再参与构建；Hugo 发布以 `content/` 下的 Markdown 为准。

文章正文从 `first-post.html` 改写为 Markdown：保留标题、段落、引用、列表、公众号二维码和 Bilibili 链接；封面和二维码从旧页面抽取到 `static/images/`。首页通过极简主题的 `cardMode` 呈现吉祥物、简介、公众号和 Bilibili 入口。

## 极简主题与导航

极简（hugo-jijian）作为 Hugo Module 引入；扩展样式放入 `assets/css/extended/`，主题会将其中的 CSS 打包进资源。主题首页使用 `params.cardMode`，展示 TDLAI 吉祥物、简介、社交入口和板块按钮。项目配置中建立了三个分类菜单：

1. 工具与攻略 → `/categories/tools/`
2. AI+教育 → `/categories/education/`
3. 前沿观察 → `/categories/frontier/`

文章 front matter 中使用 `tools`、`education`、`frontier` 作为分类 slug；分类页 `_index.md` 显示中文名称与介绍。极简主题提供中文优化、文章元数据、暗黑模式、移动端导航和 Pagefind 搜索。

## 本机预览

> 更新（2026-11-07）：本机已安装 Hugo 0.166.0 extended 与 Go 1.27.0，位置见 `PROJECT_HANDOFF.md` 第 5 节；以下 macOS/Homebrew 步骤为历史记录。

管理员在 macOS 上安装 Homebrew 后，可执行：

```sh
brew install hugo go
```

进入站点目录后获取主题模块并启动预览：

```sh
hugo mod get
hugo server -D
```

Hugo 会显示本地预览地址，通常为 `http://localhost:1313/`。退出预览按 `Ctrl+C`。

## 推送到现有 GitHub 仓库

当前工作目录不是 Git 克隆。为保留远端仓库提交历史，请先克隆现有仓库，再把这份工作目录里的 Hugo 文件复制到克隆目录。不要覆盖克隆目录中的 `.git`：

```sh
git clone https://github.com/souryuussl/tdlai.github.io.git tdlai-hugo
```

将本目录中的 `hugo.yaml`、`go.mod`、`content/`、`static/`、`assets/`、`.github/workflows/hugo.yaml`、`.gitignore` 和本指南复制到 `tdlai-hugo/`。然后：

```sh
cd tdlai-hugo
hugo mod get
hugo server -D
git add hugo.yaml go.mod content static assets .github/workflows/hugo.yaml .gitignore HUGO_MIGRATION_GUIDE.md
git commit -m "Migrate TDLAI site to Hugo and Jijian theme"
git push origin main
```

建议先确认本机 Hugo 首页、分类和文章都正常，再推送。旧根目录 `index.html` 与 `first-post.html` 可以先保留作迁移对照；Hugo Actions 只会发布 `public/` 构建产物，旧文件不会覆盖 Hugo 页面。确认迁移完成后再清理旧文件。

## GitHub Pages 发布设置

首次部署前，在仓库 **Settings → Pages → Build and deployment → Source**，将来源从 **Deploy from a branch** 切换为 **GitHub Actions**。之后 push 到 `main` 会触发 `.github/workflows/hugo.yaml`。

工作流会安装 Go、Node.js 与 Hugo，构建静态站点和 Pagefind 搜索索引，再上传 `public/` artifact 并发布 Pages。工作流需要 `contents: read`、`pages: write` 和 `id-token: write` 权限。Hugo 官方指引同样要求将 Pages Source 改为 GitHub Actions，并在 workflow 中构建、上传、部署站点。

## 维护注意事项

- 新文章存放于 `content/posts/`，使用 Markdown front matter 设置标题、日期、分类、标签和封面。
- 图片放入 `static/images/`，文章中使用以 `/images/` 开头的路径。
- 分类 slug 使用 `tools`、`education`、`frontier`，确保文章进入对应分类页。
- 更新 Hugo Module 后一并提交 `go.mod` 和 `go.sum`。
- 不要把 Hugo 生成的 `public/` 提交到源码仓库；Actions 每次构建都会生成它。
- `baseURL` 必须保留项目路径：`https://souryuussl.github.io/tdlai.github.io/`。同时已开启 `relativeURLs`，以修复 GitHub Pages 项目站点中静态图片被错误解析到域名根目录的问题。
- 当前 `first-post.html` 的 HTML `<title>` 与 Markdown 标题会统一到 TDLAI 品牌名称。
- 每次涉及 Hugo 配置、主题或工作流的修改，建议本地 `hugo server -D` 预览，并查看 GitHub Actions 构建结果。

## 交接时优先核对

1. 用本机 Hugo 版本构建一次，修复配置或 front matter 错误。
2. 确认极简主题 module 下载成功，并提交 `go.sum`。
3. 在仓库 Pages 设置中切换为 GitHub Actions，再推送 Hugo 项目。
4. 检查首页、三类菜单、首篇文章、二维码、Bilibili 超链接及手机布局。
5. 后续接入飞书矩阵前，先确认希望展示的公开名称与链接。

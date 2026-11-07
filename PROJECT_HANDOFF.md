# TDLAI 项目交接报告

> 最后更新：2026-11-07（Asia/Shanghai）
> 当前版本已迁移至 **Hugo + hugo-jijian 主题**，由 GitHub Actions 自动构建发布。
> 历史纯 HTML 版本已归档至 `legacy/`，如需查阅请使用 `git log` 或备份分支 `backup/pre-hugo-cleanup`。

## 1. 项目概览

- **项目名称：** TDLAI
- **定位：** AI 工具学习、实测与使用攻略，并逐步探索 AI 与教育、课程培训的结合。
- **核心内容：** AI 工具上手、提示词与工作流、AI 教育实践、技术与产品更新。
- **品牌角色：** 桃大龙，作为 TDLAI 的视觉吉祥物和学习伙伴。
- **视觉方向：** 粉色为主，搭配淡蓝色；留白、柔和渐变和较大的阅读字号。
- **目标读者：** 对 AI 工具感兴趣的普通用户、教育工作者、学习者，以及关注 AI 教育应用的人群。

## 2. 仓库与发布

- **GitHub 仓库：** [souryuussl/tdlai.github.io](https://github.com/souryuussl/tdlai.github.io)
- **可见性：** Public
- **默认分支：** `main`
- **站点地址：** <https://souryuussl.github.io/tdlai.github.io/>
- **发布方式：** GitHub Actions（`.github/workflows/hugo.yaml`）构建 Hugo 站点并部署到 GitHub Pages
- **触发条件：** 推送到 `main` 分支，或在 Actions 页面手动触发
- **本地映射目录：** `D:\workspace\03-blog`（Git 克隆，远端 `origin` 使用 SSH）

> 仓库名与用户名不一致，因此这是**项目站点**，访问路径必须包含 `/tdlai.github.io/`。`hugo.yaml` 中的 `baseURL` 已按此配置。

## 3. 技术栈

| 层 | 技术 |
|---|---|
| 静态站点生成 | Hugo 0.166.0（extended） |
| 主题 | `github.com/hcllmsx/hugo-jijian`（Hugo Modules） |
| 搜索 | Pagefind（构建时生成索引） |
| 部署 | GitHub Actions + GitHub Pages |
| 自动草稿 | `scripts/fetch_ai_news.py` + `fetch-ai-news.yml`（每两天一次） |

## 4. 当前目录结构

```text
/
├── .github/workflows/
│   ├── hugo.yaml              # 构建并部署到 Pages
│   └── fetch-ai-news.yml      # 定时抓取 AI 新闻草稿
├── .trae/rules/blog-dev.md    # 开发准则（Windows 路径已更新）
├── archetypes/posts.md        # 新文章模板
├── content/
│   ├── posts/                 # 正式文章
│   ├── drafts/                # 自动生成的草稿
│   ├── education/             # AI+教育栏目
│   ├── tools/                 # 工具与攻略栏目
│   └── categories/            # 分类索引
├── layouts/                   # 自定义布局与 shortcode
├── assets/css/extended/custom.css
├── static/images/             # 文章图片
├── scripts/fetch_ai_news.py
├── legacy/                    # 旧版纯 HTML 页面（不再参与构建）
├── hugo.yaml
├── go.mod / go.sum
├── PROJECT_GUIDE.md           # 内容规范
└── HUGO_MIGRATION_GUIDE.md    # 迁移历史
```

## 5. 本地开发环境

| 工具 | 位置 |
|---|---|
| Hugo 0.166.0 extended | `D:\workspace\huanjing\hugo` |
| Go 1.27.0 | `D:\workspace\huanjing\go` |
| gh CLI 2.103.3 | `D:\workspace\huanjing\gh` |
| 建设预览工作区 | `D:\workspace\04-blogjianshe`（先预览，确认后再落到本目录） |

本地预览（PowerShell）：

```powershell
$env:Path = "D:\workspace\huanjing\hugo;D:\workspace\huanjing\go\bin;" + $env:Path
$env:HUGO_MODULE_PROXY = "https://goproxy.cn"
cd D:\workspace\03-blog
hugo server -D --baseURL http://127.0.0.1:1313/
```

浏览器访问 <http://localhost:1313/>。

> 生产环境的 `baseURL` 包含 `/tdlai.github.io/` 子路径。本地预览必须用 `--baseURL` 覆盖为根路径，否则 CSS 会指向 `/tdlai.github.io/assets/...` 而 404。

## 6. 内容规范

- 文章目录：`content/posts/`，文件名 `YYYY-MM-DD-英文缩写.md`。
- Front Matter 必填：`title`、`date`、`categories`、`tags`。
- `categories` 只能是：`工具与攻略`、`AI+教育`、`前沿观察`。
- 图片放在 `static/images/`，Markdown 中使用 `/images/xxx.jpg`。
- 详细写作结构见 [PROJECT_GUIDE.md](PROJECT_GUIDE.md)。

## 7. 发布流程

```powershell
cd D:\workspace\03-blog
git pull --rebase
# 编辑文章 / 图片
hugo server -D          # 本地预览（可选）
git add .
git commit -m "新增文章：标题"
git push origin main
```

推送后约 1–3 分钟，Actions 完成构建并发布。可在仓库 Actions 页面查看进度。

## 8. 媒体矩阵

| 渠道 | 展示名称 | 当前链接/入口 |
|---|---|---|
| 微信公众号 | 桃大龙的生活实验室 | `static/images/wechat-qr.jpg`（主题社交图标） |
| Bilibili | 桃大龙的生活实验室 | <https://space.bilibili.com/66382812> |
| 视频号 | TDLAI | 暂仅展示名称 |
| 小红书 | 桃大龙的生活实验室 | 暂仅展示名称 |

## 9. 已知限制与待办

1. 旧版 HTML 已归档到 `legacy/`，其中的内嵌 Base64 图片不再维护；如需旧内容，请迁移为 Markdown。
2. 订阅表单未接入后端服务，目前只是界面展示。
3. 视频号、小红书尚无直达链接。
4. `fetch-ai-news.yml` 依赖仓库 Secret `LLM_API_KEY`，若未配置则定时任务会失败。
5. 评论、自定义域名尚未启用。

## 10. 最近变更记录

- 2026-11-07：建立本地 Git 映射 `D:\workspace\03-blog`；配置 SSH 部署密钥；修复 `baseURL` 为项目站点路径；归档旧版 HTML；清理 `.DS_Store`；新增文章模板；更新开发准则与交接文档。

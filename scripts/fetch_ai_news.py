#!/usr/bin/env python3
"""抓取 AI 官方博客 RSS，调用 LLM 生成中文「前沿观察」草稿。

用法：
    python scripts/fetch_ai_news.py            # 正常生成草稿
    python scripts/fetch_ai_news.py --dry-run  # 跳过 LLM 调用，仅验证抓取与文件写入

环境变量：
    LLM_API_KEY   LLM 的 API Key（必填，dry-run 除外）
    LLM_PROVIDER  deepseek（默认）或 gemini
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

# ---- 配置 ----
FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    # Anthropic 无公开 RSS，用 BAIR（伯克利 AI 研究院）替代
    ("BAIR", "https://bair.berkeley.edu/blog/feed.xml"),
    ("MIT Tech Review AI",
     "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
]

DAYS_BACK = 3        # 只取最近 3 天的条目
MAX_PER_FEED = 5     # 每个源最多取 5 条
MAX_TOTAL = 12       # 送入 LLM 的条目总数上限（控制 token）

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = REPO_ROOT / "content" / "drafts"

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()

CST = timezone(timedelta(hours=8))  # 北京时间

PROMPT_TEMPLATE = """你是一名中文科技博客编辑。以下是最近几天来自多个 AI 官方渠道的新闻条目（JSON 数组）。

请用中文写一篇 600-900 字的「前沿观察」速览草稿，要求：
1. 按主题归纳，用 ## 二级标题分节，不要逐条罗列。
2. 每条重要信息后注明来源，格式为 Markdown 链接（如 [OpenAI](https://...)）。
3. 语气客观克制，不做夸大预测。
4. 结尾另起一段写：> 编辑注：本文由自动化工作流生成，发布前需人工核对事实与表述。
5. 只输出正文 Markdown，不要输出 YAML front matter，不要任何额外解释。

新闻条目：
"""


def fetch_entries():
    """抓取各 RSS 源，返回按时间倒序的条目列表。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    items = []
    for name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                print(f"[warn] {name}: 解析失败 ({feed.bozo_exception})")
                continue
        except Exception as e:
            print(f"[warn] {name}: 抓取异常 ({e})")
            continue
        count = 0
        for entry in feed.entries:
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                parsed = getattr(entry, attr, None)
                if parsed:
                    published = datetime(*parsed[:6], tzinfo=timezone.utc)
                    break
            if published and published < cutoff:
                continue
            summary = getattr(entry, "summary", "") or ""
            summary = re.sub(r"<[^>]+>", "", summary)  # 去 HTML 标签
            summary = re.sub(r"\s+", " ", summary).strip()
            items.append({
                "source": name,
                "title": (getattr(entry, "title", "无标题") or "").strip(),
                "link": (getattr(entry, "link", "") or "").strip(),
                "published": published.isoformat() if published else "",
                "summary": summary[:600],
            })
            count += 1
            if count >= MAX_PER_FEED:
                break
        print(f"[info] {name}: 取到 {count} 条")
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:MAX_TOTAL]


def call_llm(prompt):
    """调用 LLM API，返回生成的文本。支持 deepseek / gemini。"""
    if not LLM_API_KEY:
        sys.exit("[error] 缺少环境变量 LLM_API_KEY")

    if LLM_PROVIDER == "gemini":
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.0-flash:generateContent?key={LLM_API_KEY}")
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
    else:  # deepseek（OpenAI 兼容格式）
        url = "https://api.deepseek.com/chat/completions"
        body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        }

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[error] LLM API 返回 {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}")

    if LLM_PROVIDER == "gemini":
        return data["candidates"][0]["content"]["parts"][0]["text"]
    return data["choices"][0]["message"]["content"]


def build_markdown(today, items, article):
    """拼装带 front matter 的完整 Markdown。"""
    lines = [
        "---",
        f'title: "AI 前沿速览（{today}）"',
        f"date: {today}",
        "draft: true",
        'categories: ["前沿观察"]',
        'tags: ["AI 新闻", "自动摘要", "LLM"]',
        "# 本期抓取来源",
        "sources:",
    ]
    seen = set()
    for it in items:
        if it["link"] and it["link"] not in seen:
            seen.add(it["link"])
            lines.append(f'  - "{it["link"]}"')
    lines += ["---", "", article.strip(), ""]
    return "\n".join(lines)


def ensure_index():
    """确保 content/drafts/_index.md 存在且为 draft，防止 section 页被发布。"""
    idx = DRAFTS_DIR / "_index.md"
    if not idx.exists():
        idx.write_text('---\ntitle: "草稿箱"\ndraft: true\n---\n', encoding="utf-8")


def main():
    dry_run = "--dry-run" in sys.argv

    items = fetch_entries()
    if not items:
        print("[info] 没有抓到符合条件的条目，本次不生成草稿")
        return

    if dry_run:
        article = "（dry-run 模式：此处为 LLM 生成内容的占位文本）\n"
        print("[info] dry-run 模式，跳过 LLM 调用")
    else:
        prompt = PROMPT_TEMPLATE + json.dumps(items, ensure_ascii=False, indent=2)
        print(f"[info] 调用 LLM（provider={LLM_PROVIDER}）生成摘要……")
        article = call_llm(prompt)

    today = datetime.now(CST).strftime("%Y-%m-%d")
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_index()
    out = DRAFTS_DIR / f"{today}-ai-news-roundup.md"
    out.write_text(build_markdown(today, items, article), encoding="utf-8")
    print(f"[done] 草稿已生成: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

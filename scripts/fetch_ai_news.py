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
# (源名称, RSS 地址, 是否启用教育关键词过滤)
# 泛技术源（如 OpenAI）只保留教育相关条目；教育专门源全量保留
FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml", True),
    ("EdSurge", "https://www.edsurge.com/feed", False),
    ("EdTech Higher Ed", "http://feeds.feedburner.com/EdTechHiEd", False),
    ("EdTech K-12", "http://feeds.feedburner.com/EdTechK12", False),
]

# 教育关键词：命中标题或摘要即视为教育相关（注意避免 "learning" 这类
# 会误中 machine learning 的宽泛词）
EDU_KEYWORDS = [
    "education", "school", "teacher", "student", "classroom", "university",
    "college", "campus", "tutor", "pedagogy", "curriculum", "k-12",
    "higher ed", "academic", "study mode",
]

DAYS_BACK = 3        # 只取最近 3 天的条目
MAX_PER_FEED = 5     # 每个源最多取 5 条
MAX_TOTAL = 12       # 送入 LLM 的条目总数上限（控制 token）

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = REPO_ROOT / "content" / "drafts"

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()

CST = timezone(timedelta(hours=8))  # 北京时间

PROMPT_TEMPLATE = """你是一位资深教育科技编辑，长期为教育从业者（一线教师、教研员、学校管理者）撰写「前沿观察」专栏。下面是最近几天从多个海外教育科技渠道抓取的新闻素材（JSON 数组，含 source / title / link / summary 字段）。

写作要求：
0. 【结构】正文最开头写 2-3 句导语（不加小标题），概括本期最值得教育从业者关注的动向；导语结束后另起一行写 <!--more-->（ Hugo 摘要截断标签），然后再进入第一个 ## 小标题。
1. 【严格筛选】只采用与课堂教学、学生学习、教师工作、教育政策相关的内容。纯技术发布（新模型、新工具、纯研究）和融资、商业新闻一律忽略，即使它们出现在素材里；某条新闻与教育的关联如果需要拐弯抹角才能建立，就放弃它。若素材整体偏少，宁可写短也不要凑数。
2. 把筛选后的素材视为一个整体，提炼 2-4 个核心主题（例如：AI 进课堂、教师工作与减负、学习方式变化、教育政策与治理等），围绕主题进行综合报道，严禁逐条罗列或翻译。
3. 每个主题拟一个有吸引力的中文小标题（## 二级标题），标题要点明对教育工作者的实际意义，不要平铺直叙。
4. 语言专业但不晦涩：面向一线教育从业者，不可避免的技术术语首次出现时用一句话解释清楚。严禁出现「据悉」「该文章指出」「据报道」「值得注意的是」这类生硬翻译腔词汇。
5. 同一主题下不同来源的新闻要合并叙述，点出事件之间的关联与趋势，而不是罗列清单。
6. 全文 600-900 字，段落与列表混排，详略得当。
7. 文末设「参考来源」一节，用 Markdown 列表统一附上引用过的原新闻链接，格式：- [来源名：文章标题](链接)。
8. 最后另起一段写：> 编辑注：本文由自动化工作流生成，发布前需人工核对事实与表述。
9. 只输出正文 Markdown，不要输出 YAML front matter，不要任何额外解释或寒暄。

新闻素材：
"""


def is_edu_related(title, summary):
    """判断条目是否与教育相关（命中任一教育关键词）。"""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in EDU_KEYWORDS)


def fetch_entries():
    """抓取各 RSS 源，返回按时间倒序的条目列表。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    items = []
    for name, url, edu_only in FEEDS:
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
            title = (getattr(entry, "title", "无标题") or "").strip()
            summary = getattr(entry, "summary", "") or ""
            summary = re.sub(r"<[^>]+>", "", summary)  # 去 HTML 标签
            summary = re.sub(r"\s+", " ", summary).strip()
            if edu_only and not is_edu_related(title, summary):
                continue
            items.append({
                "source": name,
                "title": title,
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
        f'title: "AI+教育前沿速览（{today}）"',
        f"date: {today}",
        "draft: true",
        'categories: ["前沿观察"]',
        'tags: ["AI+教育", "教育科技", "自动摘要"]',
        "# 本期抓取来源",
        "sources:",
    ]
    seen_links = []
    for it in items:
        if it["link"] and it["link"] not in seen_links:
            seen_links.append(it["link"])
    for link in seen_links:
        lines.append(f'  - "{link}"')
    lines += [
        "# 封面图",
        "cover:",
        '  image: "/images/ai-edu-cover.jpg"',
        '  alt: "AI+教育"',
        "---",
        "",
        article.strip(),
        "",
    ]
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

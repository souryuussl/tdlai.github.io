#!/usr/bin/env python3
"""按星期抓取国内/海外 AI+教育新闻，调用 LLM 生成中文「前沿观察」草稿。

规则：周一抓国内源，周四抓海外源（其他日期默认国内，可用 --region 覆盖）。

用法：
    python scripts/fetch_ai_news.py                  # 按星期自动选择区域
    python scripts/fetch_ai_news.py --dry-run        # 跳过 LLM 调用，仅验证抓取与文件写入
    python scripts/fetch_ai_news.py --region global  # 手动指定区域（cn / global）

环境变量：
    LLM_API_KEY   LLM 的 API Key（必填，dry-run 除外）
    LLM_PROVIDER  deepseek（默认）或 gemini
    FETCH_REGION  auto（默认）/ cn / global
"""

import html as html_lib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

# ---- 配置 ----
# kind:   rss = 标准 RSS/Atom；html = 新闻列表页（按链接中的 tYYYYMMDD 识别文章）
# filter: 抓取时初筛规则
#         edu_en = 只保留命中英文教育关键词的条目（泛技术源用）
#         edu_zh = 只保留命中中文教育关键词的条目（国内 AI/科技源用）
#         ai_zh  = 只保留命中中文 AI/数字化关键词的条目（国内教育媒体/政策源用）
#         none   = 全量保留，交给 LLM 筛选
# region: global / cn，分别控制送入 LLM 的条数，保证国内内容占比
FEEDS = [
    # ---- 国外源 ----
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml", "kind": "rss", "filter": "edu_en", "region": "global"},
    {"name": "EdSurge", "url": "https://www.edsurge.com/feed", "kind": "rss", "filter": "none", "region": "global"},
    {"name": "EdTech Higher Ed", "url": "http://feeds.feedburner.com/EdTechHiEd", "kind": "rss", "filter": "none", "region": "global"},
    {"name": "EdTech K-12", "url": "http://feeds.feedburner.com/EdTechK12", "kind": "rss", "filter": "none", "region": "global"},
    # ---- 国内源 ----
    {"name": "芥末堆", "url": "https://www.jiemodui.com/feed", "kind": "rss", "filter": "ai_zh", "region": "cn"},
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "kind": "rss", "filter": "edu_zh", "region": "cn"},
    {"name": "教育部", "url": "http://www.moe.gov.cn/jyb_xwfb/s5147/", "kind": "html", "filter": "ai_zh", "region": "cn"},
    {"name": "中国教育在线", "url": "https://news.eol.cn/", "kind": "html", "filter": "ai_zh", "region": "cn"},
    {"name": "中国教育报", "url": "http://www.jyb.cn/", "kind": "html", "filter": "ai_zh", "region": "cn"},
]

# 英文教育关键词：泛技术源（如 OpenAI）只保留教育相关条目
EDU_KEYWORDS_EN = [
    "education", "school", "teacher", "student", "classroom", "university",
    "college", "campus", "tutor", "pedagogy", "curriculum", "k-12",
    "higher ed", "academic", "study mode",
]

# 中文教育关键词：国内 AI/科技源只保留教育相关条目
# 注意避免「学习」这类会误中「机器学习」的宽泛词
EDU_KEYWORDS_ZH = [
    "教育", "学校", "教师", "老师", "学生", "课堂", "教学", "课程",
    "高校", "中小学", "大学", "校园", "作业", "考试", "培训", "教研",
    "备课", "家长", "幼儿园", "职业院校", "职教", "教材",
]

# 中文 AI/数字化关键词：国内教育媒体与政策源只保留 AI 赋能教育相关条目
AI_KEYWORDS_ZH = [
    "人工智能", "生成式", "大模型", "大语言模型", "智能体", "智慧教育",
    "教育信息化", "数字化教育", "智能教育", "机器学习", "深度学习",
    "deepseek", "chatgpt", "豆包", "文心一言", "通义", "讯飞星火",
    "kimi", "智谱", "ai赋能", "ai+教育", "workbuddy",
    # 泛教育科技源（芥末堆）里用于识别数字化/智能化选题
    "智能", "科技", "数字化", "信息化",
]

# 匹配独立的 "AI"（避免误中 said、email 等英文单词里的 ai）
AI_RE = re.compile(r"(?<![a-z])ai(?![a-z])")

DAYS_BACK = 5        # 只取最近 5 天的条目（覆盖每周两次抓取之间的间隔）
MAX_PER_FEED = 5     # 每个源最多取 5 条
MAX_GLOBAL = 8       # 送入 LLM 的海外条目上限
MAX_CN = 8           # 送入 LLM 的国内条目上限
MAX_PER_SOURCE_RESULT = 3  # 最终结果中单个源最多保留的条数，避免单源占满名额

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HTTP_TIMEOUT = 30

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = REPO_ROOT / "content" / "drafts"

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
FETCH_REGION = os.environ.get("FETCH_REGION", "auto").strip().lower()

CST = timezone(timedelta(hours=8))  # 北京时间
REGION_LABELS = {"cn": "国内", "global": "海外"}

PROMPT_TEMPLATE = """你是一位资深教育科技编辑，长期为教育从业者（一线教师、教研员、学校管理者）撰写「前沿观察」专栏。本期抓取范围：{region_desc}。下面是最近几天抓取的新闻素材（JSON 数组，含 source / region / title / link / summary 字段）。

写作要求：
0. 【结构】正文最开头写 2-3 句导语（不加小标题），概括本期最值得教育从业者关注的动向；导语结束后另起一行写 <!--more-->（Hugo 摘要截断标签），然后再进入第一个 ## 小标题。
1. 【严格筛选】优先保留与课堂教学、学生学习、教师备课/批改、教育政策边界、学校落地实践相关的内容。纯技术发布（新模型、新工具、纯研究）和融资、商业新闻一律忽略，即使它们出现在素材里；某条新闻与教育的关联如果需要拐弯抹角才能建立，就放弃它。若素材整体偏少，宁可写短也不要凑数。
2. 【主题】{topic_rule}
3. 每个主题拟一个有吸引力的中文小标题（## 二级标题），标题要点明对教育工作者的实际意义，不要平铺直叙。
4. 语言专业但不晦涩：面向一线教育从业者，不可避免的技术术语首次出现时用一句话解释清楚。严禁出现「据悉」「该文章指出」「据报道」「值得注意的是」这类生硬翻译腔词汇。
5. {detail_rule}
6. 全文 800-1200 字，段落与列表混排，详略得当。
7. 【本土化延伸】主体报道之后，用「## 这对国内教师意味着什么」开一个小节，用 2-4 句话点评上述趋势对国内教师的实际影响，要具体、不说空话。
8. 【落地建议】再加一个「## 一线教师可以怎么做」小节，给出 2-3 条具体可操作的建议，优先推荐国内可直接使用的工具（如豆包、DeepSeek、希沃、WorkBuddy 等）；若素材没有直接对应的做法，可基于报道趋势合理推演，但必须注明这是编辑建议而非新闻事实。
9. 文末设「参考来源」一节，用 Markdown 列表统一附上引用过的原新闻链接，格式：- [来源名：文章标题](链接)。
10. 最后另起一段写：> 编辑注：本文由自动化工作流生成，发布前需人工核对事实与表述。
11. 只输出正文 Markdown，不要输出 YAML front matter，不要任何额外解释或寒暄。

新闻素材：
"""

PROMPT_REGION_CONFIG = {
    "cn": {
        "region_desc": "国内教育媒体与主管部门（教育部、中国教育报、中国教育在线、芥末堆、量子位）",
        "topic_rule": "把筛选后的素材视为一个整体，提炼 2-4 个国内 AI 教育主题（例如：政策与治理、区域/学校落地实践、教师培训与减负、企业产品进校园、学生使用与评价）。围绕主题综合报道，同一主题下不同来源的新闻要合并叙述、点出关联，严禁逐条罗列或翻译。",
        "detail_rule": "国内动态要具体到政策名称、地区、学校或产品（素材里有的信息必须保留），让国内教师能对上自己的工作场景；素材没有的细节不要编造。",
    },
    "global": {
        "region_desc": "海外教育科技媒体（EdSurge、EdTech Magazine、OpenAI 等）",
        "topic_rule": "把筛选后的素材视为一个整体，提炼 2-4 个海外 AI 教育趋势主题（例如：AI 进课堂、教师工作与评价、学习方式变化、教育治理与政策）。围绕主题综合报道，同一主题下不同来源的新闻要合并叙述、点出关联，严禁逐条罗列或翻译。",
        "detail_rule": "写清趋势背后的机制、政策背景和对学校/教师的具体影响，不要只停留在现象描述；素材没有的细节不要编造。",
    },
}


def matches_filter(text, mode):
    """按源配置的初筛规则判断条目是否保留。"""
    if mode == "none":
        return True
    low = text.lower()
    if mode == "edu_en":
        return any(kw in low for kw in EDU_KEYWORDS_EN)
    if mode == "edu_zh":
        return any(kw in text for kw in EDU_KEYWORDS_ZH)
    if mode == "ai_zh":
        return any(kw in low for kw in AI_KEYWORDS_ZH) or bool(AI_RE.search(low))
    return True


def http_get(url):
    """带 UA 和超时地获取页面，按响应头/常见编码解码。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset()
    for enc in (charset, "utf-8", "gbk"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "ignore")


def parse_entry_time(entry):
    """从 feedparser 条目解析发布时间（UTC）。"""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def make_item(feed, title, link, summary, published):
    return {
        "source": feed["name"],
        "region": "国内" if feed["region"] == "cn" else "海外",
        "title": title,
        "link": link,
        "published": published.isoformat() if published else "",
        "summary": summary[:600],
        "_sort": published.timestamp() if published else 0,
    }


def fetch_rss(feed, cutoff):
    """抓取 RSS/Atom 源并按初筛规则过滤。"""
    content = http_get(feed["url"])
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"解析失败 ({parsed.bozo_exception})")

    items = []
    for entry in parsed.entries:
        published = parse_entry_time(entry)
        if published and published < cutoff:
            continue
        title = (getattr(entry, "title", "") or "").strip() or "无标题"
        summary = getattr(entry, "summary", "") or ""
        summary = re.sub(r"<[^>]+>", "", summary)  # 去 HTML 标签
        summary = re.sub(r"\s+", " ", summary).strip()
        if not matches_filter(title + " " + summary, feed["filter"]):
            continue
        items.append(make_item(
            feed, title, (getattr(entry, "link", "") or "").strip(),
            summary, published,
        ))
        if len(items) >= MAX_PER_FEED:
            break
    return items


# HTML 列表页中的文章链接：href 里带 t20261116_1458379.html / t20261116_2795114.shtml
HTML_ITEM_RE = re.compile(
    r'<a\b([^>]*?\bhref="([^"]*?t(\d{8})_\d+\.s?html)"[^>]*)>(.*?)</a>',
    re.I | re.S,
)


def clean_text(text):
    """去掉标签、HTML 实体与多余空白。"""
    text = re.sub(r"<[^>]+>", "", text)
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def fetch_html(feed, cutoff):
    """抓取新闻列表页，按链接日期与关键词过滤。"""
    content = http_get(feed["url"])
    items = []
    seen = set()
    for attrs, href, date_str, inner in HTML_ITEM_RE.findall(content):
        try:
            published = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=CST)
        except ValueError:
            continue
        if published < cutoff:
            continue
        title_attr = re.search(r'\btitle="([^"]*)"', attrs, re.I)
        title = clean_text(title_attr.group(1) if title_attr else inner)
        if not title or title in {"[详情]", "详情"}:
            continue
        link = urllib.parse.urljoin(feed["url"], html_lib.unescape(href))
        if link in seen:
            continue
        seen.add(link)
        if not matches_filter(title, feed["filter"]):
            continue
        items.append(make_item(feed, title, link, "", published))
        if len(items) >= MAX_PER_FEED:
            break
    return items


def resolve_region():
    """周一抓国内、周四抓海外；其他日期默认国内。可用 --region / FETCH_REGION 覆盖。"""
    for i, arg in enumerate(sys.argv):
        if arg == "--region" and i + 1 < len(sys.argv):
            value = sys.argv[i + 1].strip().lower()
            if value in REGION_LABELS:
                return value
    if FETCH_REGION in REGION_LABELS:
        return FETCH_REGION
    weekday = datetime.now(CST).weekday()  # 0=周一，3=周四
    return "global" if weekday == 3 else "cn"


def fetch_entries(region):
    """抓取指定区域的源，按时间倒序截断，返回条目列表。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    pool = []

    for feed in FEEDS:
        if feed["region"] != region:
            continue
        fetcher = fetch_html if feed["kind"] == "html" else fetch_rss
        try:
            items = fetcher(feed, cutoff)
        except Exception as e:
            print(f"[warn] {feed['name']}: 抓取异常 ({e})")
            continue
        print(f"[info] {feed['name']}: 取到 {len(items)} 条")
        pool.extend(items)

    def pick(candidates, limit):
        """按时间倒序选取，同时限制单源条数，避免一个源占满名额。"""
        per_source = {}
        chosen = []
        for it in sorted(candidates, key=lambda x: x["_sort"], reverse=True):
            count = per_source.get(it["source"], 0)
            if count >= MAX_PER_SOURCE_RESULT:
                continue
            per_source[it["source"]] = count + 1
            chosen.append(it)
            if len(chosen) >= limit:
                break
        return chosen

    limit = MAX_CN if region == "cn" else MAX_GLOBAL
    picked = pick(pool, limit)
    picked.sort(key=lambda x: x["_sort"], reverse=True)
    for it in picked:
        it.pop("_sort", None)
    return picked


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


def build_markdown(today, items, article, region):
    """拼装带 front matter 的完整 Markdown。"""
    region_tag = "国内动态" if region == "cn" else "海外观察"
    lines = [
        "---",
        f'title: "AI+教育前沿速览（{today}）"',
        f"date: {today}",
        "draft: true",
        'categories: ["前沿观察"]',
        f'tags: ["AI+教育", "教育科技", "{region_tag}", "自动摘要"]',
        f"# 本期范围：{REGION_LABELS[region]}",
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
    region = resolve_region()
    print(f"[info] 本期抓取区域：{REGION_LABELS[region]}（{region}）")

    items = fetch_entries(region)
    if not items:
        print("[info] 没有抓到符合条件的条目，本次不生成草稿")
        return

    if dry_run:
        article = "（dry-run 模式：此处为 LLM 生成内容的占位文本）\n"
        print("[info] dry-run 模式，跳过 LLM 调用")
    else:
        prompt = PROMPT_TEMPLATE.format(**PROMPT_REGION_CONFIG[region])
        prompt += json.dumps(items, ensure_ascii=False, indent=2)
        print(f"[info] 调用 LLM（provider={LLM_PROVIDER}）生成摘要……")
        article = call_llm(prompt)

    today = datetime.now(CST).strftime("%Y-%m-%d")
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_index()
    out = DRAFTS_DIR / f"{today}-ai-news-roundup.md"
    out.write_text(build_markdown(today, items, article, region), encoding="utf-8")
    print(f"[done] 草稿已生成: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

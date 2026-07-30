"""解析 aihot.virxact.com 的日报 / 周报 / 月报 / 详情页。

目标站为 Next.js SSR，正文 HTML 带语义化 class，直接解析即可。
注意桌面版与移动版内容会重复渲染，日报正文只取 id="sec-N" 的分节
（移动版为 id="m-sec-N"），周报/月报为 id="period-sec-N"。
"""

import re

from bs4 import BeautifulSoup

BASE_URL = "https://aihot.virxact.com"


def _text(node):
    return node.get_text(strip=True) if node else ""


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _item_id(href):
    m = re.search(r"/items/([A-Za-z0-9]+)", href or "")
    return m.group(1) if m else None


def parse_daily(html):
    """解析日报页，返回结构化 dict。"""
    soup = BeautifulSoup(html, "lxml")

    masthead = soup.select_one(".daily-masthead-eyebrow")
    eyebrow = _clean(_text(masthead))  # 例如 "VOL.2026.07.30 · 21 STORIES · AI HOT DAILY"
    vol = ""
    m = re.search(r"VOL\.\s*([\d.\-Ww]+)", eyebrow)
    if m:
        vol = m.group(1)

    metrics = [
        {"value": _text(li.select_one(".daily-metric-value")),
         "label": _text(li.select_one(".daily-metric-label"))}
        for li in soup.select(".daily-metric")
    ]

    sections = []
    for sec in soup.select('section.daily-section[id^="sec-"]'):
        articles = []
        for art in sec.select("article.daily-article"):
            a = art.select_one(".daily-article-title a[href]")
            if not a:
                continue
            source_box = art.select_one(".daily-article-source")
            role = source_box.select_one(".role-tag") if source_box else None
            source_spans = [
                _text(sp) for sp in (source_box.find_all("span") if source_box else [])
                if "role-tag" not in (sp.get("class") or [])
            ]
            articles.append({
                "id": _item_id(a.get("href")),
                "title": _clean(_text(a)),
                "url": BASE_URL + a["href"] if a["href"].startswith("/") else a["href"],
                "role_tag": _text(role),
                "source": _clean(" ".join(source_spans)),
                "summary": _clean(_text(art.select_one(".daily-article-summary"))),
                "is_lead": "daily-article--lead" in (art.get("class") or []),
            })
        sections.append({
            "no": _text(sec.select_one(".daily-section-no")),
            "title": _text(sec.select_one(".daily-section-title")),
            "subtitle": _text(sec.select_one(".daily-section-subtitle")),
            "count": _text(sec.select_one(".daily-section-count strong")),
            "articles": articles,
        })

    return {
        "type": "daily",
        "vol": vol,
        "eyebrow": eyebrow,
        "metrics": metrics,
        "sections": sections,
        "story_count": sum(len(s["articles"]) for s in sections),
    }


def parse_period(html, kind):
    """解析周报/月报页，kind 为 'weekly' 或 'monthly'。"""
    soup = BeautifulSoup(html, "lxml")

    eyebrow = _clean(_text(soup.select_one(".daily-masthead-eyebrow")))
    vol = ""
    m = re.search(r"VOL\.\s*([\d.\-Ww]+)", eyebrow)
    if m:
        vol = m.group(1)

    date_range = _clean(_text(soup.select_one(".daily-masthead-date")))

    lead = {
        "kicker": _text(soup.select_one(".period-lead-kicker")),
        "headline": _text(soup.select_one(".period-lead-headline")),
        "overview": _clean(_text(soup.select_one(".period-lead-overview"))),
    }

    stats = [
        {"value": _text(li.select_one(".period-stat-value")),
         "label": _text(li.select_one(".period-stat-label"))}
        for li in soup.select(".period-stat")
    ]

    themes = []
    for sec in soup.select('section.daily-section[id^="period-sec-"]'):
        stories = []
        for art in sec.select("article.period-story"):
            a = art.select_one(".period-story-title a[href]")
            if not a:
                continue
            stories.append({
                "id": _item_id(a.get("href")),
                "title": _clean(_text(a)),
                "url": BASE_URL + a["href"] if a["href"].startswith("/") else a["href"],
                "source": _clean(_text(art.select_one(".period-story-source"))),
            })
        themes.append({
            "no": _text(sec.select_one(".daily-section-no")),
            "title": _text(sec.select_one(".daily-section-title")),
            "count": _text(sec.select_one(".daily-section-count strong")),
            "intro": _clean(_text(sec.select_one(".period-theme-intro"))),
            "stories": stories,
        })

    return {
        "type": kind,
        "vol": vol,
        "eyebrow": eyebrow,
        "date_range": date_range,
        "lead": lead,
        "stats": stats,
        "themes": themes,
        "story_count": sum(len(t["stories"]) for t in themes),
    }


def parse_item_markdown(md_text):
    """解析详情页的 Markdown 导出（/items/<id>/markdown）。

    格式：
        # 标题
        - 来源：...
        - 发布时间：2026-07-29 08:00
        - AIHOT 分数：77
        - AIHOT 标记：精选
        - AIHOT 链接：...
        - 原文链接：...
        ## 精选理由 / ## AI 摘要 / ## 正文
    """
    out = {
        "title": "", "source": "", "published_at": "", "score": "",
        "flags": "", "original_url": "", "aihot_url": "",
        "curation_reason": "", "ai_summary": "", "content_markdown": "",
    }
    lines = md_text.splitlines()

    body_start = len(lines)
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("# ") and not out["title"]:
            out["title"] = s[2:].strip()
            continue
        m = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", s)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "来源":
                out["source"] = val
            elif key == "发布时间":
                out["published_at"] = val
            elif key == "AIHOT 分数":
                out["score"] = val
            elif key == "AIHOT 标记":
                out["flags"] = val
            elif key == "原文链接":
                out["original_url"] = val
            elif key == "AIHOT 链接":
                out["aihot_url"] = val
            continue
        if s.startswith("## "):
            body_start = i
            break

    # 按 ## 小节切分
    section_re = re.compile(r"^##\s+(.+?)\s*$", re.M)
    body = "\n".join(lines[body_start:])
    parts = section_re.split(body)
    # parts: ['', '精选理由', '...', 'AI 摘要', '...', '正文', '...']
    sections = {}
    for j in range(1, len(parts) - 1, 2):
        sections[parts[j].strip()] = parts[j + 1].strip()
    out["curation_reason"] = sections.get("精选理由", "")
    out["ai_summary"] = sections.get("AI 摘要", "")
    out["content_markdown"] = sections.get("正文", "")
    if not out["content_markdown"] and body.strip():
        # 没有「正文」小节时，把剩余内容都当作正文
        out["content_markdown"] = body.strip()
    return out


def parse_report_links(html, kind):
    """从 /weekly 或 /monthly 索引页提取所有期号链接，返回去重有序列表。"""
    pat = r'href="/%s/([\d]{4}-(?:W\d{2}|\d{2}))"' % kind
    seen, out = set(), []
    for m in re.finditer(pat, html):
        pid = m.group(1)
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out

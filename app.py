"""
PT 文章發想站 Phase 1
資料來源：PubMed（美國國家醫學圖書館）
完全免費，不需要 API Key

【快取設計】
- 每個主題有一份「原始快取」，key = pubmed_raw_{topic}
- 原始快取存的是「不限年份、最多 200 筆」的完整資料
- 顯示時再從原始快取動態過濾年份 + 取前 N 筆
- 總覽與單一主題共用同一份原始快取，不重複打 API
- 改年份滑桿不觸發任何 API，純 Python 過濾

【已修正的問題】
1. 總覽抓完後切換個別主題需重抓 → 共用原始快取解決
2. 年份放寬反而文獻變少 → API 端不限年份，Python 端過濾
3. 搜尋詞加了 AND physical therapy 導致結果太少 → 移除
4. 頁面 rerun 自動觸發 API → 無快取時改為手動按鈕觸發
"""

import streamlit as st
import requests
import pandas as pd
import time
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ─────────────────────────────────────────
# 頁面設定
# ─────────────────────────────────────────
st.set_page_config(page_title="PT 文章發想站", page_icon="📚", layout="wide")

# ─────────────────────────────────────────
# 快取（7 天有效）
# ─────────────────────────────────────────
CACHE_DIR  = "cache"
CACHE_DAYS = 7
os.makedirs(CACHE_DIR, exist_ok=True)

def _safe_key(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)

def _raw_cache_key(topic: str) -> str:
    """原始快取 key，不含年份/筆數，供所有模式共用"""
    return f"pubmed_raw_{_safe_key(topic)}"

def load_cache(key: str):
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            c = json.load(f)
        if datetime.now() - datetime.fromisoformat(c["ts"]) < timedelta(days=CACHE_DAYS):
            return c["data"]
    except Exception:
        pass
    return None

def save_cache(key: str, data):
    path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.now().isoformat(), "data": data}, f, ensure_ascii=False)
    except Exception as e:
        st.warning(f"快取儲存失敗：{e}")

def cache_age_str(key: str) -> str:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            c = json.load(f)
        diff = datetime.now() - datetime.fromisoformat(c["ts"])
        h = int(diff.total_seconds() / 3600)
        return f"（{h} 小時前更新）" if h < 24 else f"（{diff.days} 天前更新）"
    except Exception:
        return ""

# ─────────────────────────────────────────
# 主題清單
# ─────────────────────────────────────────
DEFAULT_TOPICS = [
    ("adhesive capsulitis",              "五十肩（沾黏性肩關節囊炎）"),
    ("disc herniation",                  "椎間盤突出"),
    ("lateral epicondylitis",            "網球肘（外側上髁炎）"),
    ("medial epicondylitis",             "高爾夫球肘（內側上髁炎）"),
    ("carpal tunnel syndrome",           "腕隧道症候群"),
    ("osteoarthritis",                   "退化性關節炎（骨關節炎）"),
    ("meniscus injury",                  "膝蓋半月板損傷"),
    ("plantar fasciitis",                "足底筋膜炎"),
    ("sciatica",                         "坐骨神經痛"),
    ("cervical spondylosis",             "頸椎病"),
    ("low back pain",                    "腰痛"),
    ("subacromial impingement syndrome", "肩峰下夾擠症候群"),
    ("patellofemoral pain syndrome",     "髕骨股骨疼痛症候群"),
    ("joint replacement rehabilitation", "關節置換術後復健"),
    ("knee pain",                        "膝關節疼痛"),
    ("scoliosis",                        "脊椎側彎"),
    ("myofascial pain syndrome",         "肌筋膜疼痛症候群"),
    ("rotator cuff",                     "旋轉肌袖損傷"),
    ("ankle sprain",                     "踝關節扭傷"),
    ("piriformis syndrome",              "梨狀肌症候群"),
]

# ─────────────────────────────────────────
# PubMed API（完全免費，不需要 Key）
# ─────────────────────────────────────────
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def _search_ids(topic: str) -> list:
    """只用主題詞搜尋，不限年份，不加額外限制詞"""
    params = {
        "db":      "pubmed",
        "term":    f"{topic}[Title/Abstract]",
        "retmax":  200,
        "sort":    "relevance",
        "retmode": "json",
    }
    time.sleep(0.4)
    r = requests.get(ESEARCH, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])

def _fetch_details(pmids: list) -> list:
    """批量抓取詳細資料，只打一次 API"""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract"}
    time.sleep(0.4)
    r = requests.get(EFETCH, params=params, timeout=20)
    r.raise_for_status()

    papers = []
    for art in ET.fromstring(r.content).findall(".//PubmedArticle"):
        try:
            title_el = art.find(".//ArticleTitle")
            title    = "".join(title_el.itertext()) if title_el is not None else ""

            auths = art.findall(".//Author")
            names = []
            for a in auths[:3]:
                last  = a.findtext("LastName", "")
                first = a.findtext("ForeName", "")
                if last:
                    names.append(f"{last} {first}".strip())
            author_str = ", ".join(names) + (" et al." if len(auths) > 3 else "")

            journal = (art.findtext(".//Journal/Title") or
                       art.findtext(".//ISOAbbreviation") or "")

            year_raw = (art.findtext(".//PubDate/Year") or
                        art.findtext(".//PubDate/MedlineDate") or "")
            year = year_raw[:4] if year_raw else ""

            pmid_el = art.find(".//PMID")
            pmid    = pmid_el.text if pmid_el is not None else ""

            abs_parts = art.findall(".//AbstractText")
            abstract  = " ".join("".join(p.itertext()) for p in abs_parts)

            doi = ""
            for el in art.findall(".//ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = el.text or ""
                    break
            link = (f"https://doi.org/{doi}" if doi
                    else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}" if pmid else ""))

            papers.append({
                "title":    title,
                "authors":  author_str,
                "journal":  journal,
                "year":     year,
                "abstract": abstract,
                "link":     link,
            })
        except Exception:
            continue
    return papers

def fetch_raw(topic: str) -> list | None:
    """
    抓取並快取原始資料（不限年份的完整 200 筆）。
    有快取直接回傳，無快取回傳 None（讓 UI 顯示按鈕）。
    """
    key    = _raw_cache_key(topic)
    cached = load_cache(key)
    if cached is not None:
        return cached

    # 需要打 API
    max_retries = 3
    for attempt in range(max_retries):
        try:
            pmids   = _search_ids(topic)
            papers  = _fetch_details(pmids)
            save_cache(key, papers)
            return papers
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            wait = 30 * (attempt + 1)
            if code == 429:
                st.warning(f"⚠️ PubMed 限流（第 {attempt+1} 次），等待 {wait} 秒後重試...")
            else:
                st.warning(f"⚠️ API 錯誤 {code}，等待 {wait} 秒後重試...")
            time.sleep(wait)
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"查詢失敗：{e}")
            time.sleep(5)
    return None

def filter_papers(raw: list, year_start: int, year_end: int, limit: int,
                  exclude_kws: list) -> tuple[pd.DataFrame, bool]:
    """
    從原始資料（Python 端）過濾年份 + 排除關鍵字 + 取前 limit 筆。
    回傳 (DataFrame, year_relaxed)
    不打任何 API，改年份滑桿完全即時。
    """
    # 1. 依年份篩選
    in_range = [
        p for p in raw
        if p.get("year", "").isdigit() and year_start <= int(p["year"]) <= year_end
    ]

    # 2. 若不足 10 筆，自動放寬：使用全部原始資料
    year_relaxed = False
    if len(in_range) < 10:
        in_range     = raw
        year_relaxed = True

    # 3. 年份新到舊排序
    in_range = sorted(
        in_range,
        key=lambda x: int(x["year"]) if x.get("year", "").isdigit() else 0,
        reverse=True
    )

    # 4. 排除關鍵字（標題 + 摘要）
    rows = []
    for p in in_range:
        title    = p.get("title", "") or ""
        abstract = p.get("abstract", "") or ""
        if any(kw.lower() in title.lower() or kw.lower() in abstract.lower()
               for kw in exclude_kws if kw.strip()):
            continue
        rows.append({
            "標題":   title,
            "作者":   p.get("authors", ""),
            "期刊":   p.get("journal", ""),
            "年份":   p.get("year", ""),
            "摘要":   (abstract[:300] + "…") if len(abstract) > 300 else abstract,
            "連結":   p.get("link", ""),
        })
        if len(rows) >= limit:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df.index = range(1, len(df) + 1)
    return df, year_relaxed

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 查詢設定")

    current_year = datetime.now().year
    y1, y2 = st.slider(
        "文獻年份範圍",
        min_value=2000, max_value=current_year,
        value=(current_year - 7, current_year), step=1
    )

    top_n = st.selectbox("每個主題顯示幾篇", [10, 20, 30], index=1)

    st.divider()
    st.subheader("🚫 排除關鍵字")
    st.caption("含有這些詞的論文會被過濾（逗號分隔）")
    exclude_raw = st.text_area(
        "排除詞", value="animal, rat, mice, cadaver, pediatric",
        height=90, label_visibility="collapsed"
    )
    exclude_kws = [k.strip() for k in exclude_raw.split(",") if k.strip()]

    st.divider()
    st.subheader("📋 主題管理")

    if "topics" not in st.session_state:
        st.session_state.topics = DEFAULT_TOPICS.copy()

    new_en = st.text_input("英文搜尋詞", placeholder="e.g. shoulder impingement")
    new_zh = st.text_input("中文標籤",   placeholder="e.g. 肩夾擠症候群")
    if st.button("➕ 新增主題"):
        existing = [t[0] for t in st.session_state.topics]
        if new_en and new_en not in existing:
            st.session_state.topics.append((new_en, new_zh or new_en))
            st.success(f"已新增：{new_zh or new_en}")
        elif new_en in existing:
            st.warning("此主題已存在")

    labels = ["（不刪除）"] + [f"{zh}（{en}）" for en, zh in st.session_state.topics]
    del_choice = st.selectbox("刪除主題", labels)
    if st.button("🗑️ 刪除") and del_choice != "（不刪除）":
        idx = labels.index(del_choice) - 1
        removed = st.session_state.topics.pop(idx)
        st.success(f"已刪除：{removed[1]}")

    st.divider()
    if st.button("🔄 清除快取（重新抓取）"):
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except Exception:
                pass
        st.success("✅ 快取已清除，請逐一點擊各主題的「抓取」按鈕。")

    st.info(
        f"📦 快取有效期：{CACHE_DAYS} 天\n\n"
        "• 總覽與個別主題**共用同一份快取**\n"
        "• 調整年份滑桿**不需重新抓取**\n"
        "• 有快取時完全不打 API"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站｜文獻情報")
st.caption("透過 PubMed 資料庫抓取物理治療相關主題文獻，快速找到衛教文章的科學依據")

topics = st.session_state.topics

selected = st.selectbox(
    "選擇查詢主題",
    options=topics,
    format_func=lambda t: f"{t[1]}　({t[0]})"
)
show_all = st.toggle("顯示所有主題總覽", value=False)
st.divider()

# ─────────────────────────────────────────
# 共用：顯示單一主題結果
# ─────────────────────────────────────────
def render_papers(en: str, zh: str, raw: list):
    """把原始資料過濾後顯示，不打 API"""
    df, year_relaxed = filter_papers(raw, y1, y2, top_n, exclude_kws)

    age      = cache_age_str(_raw_cache_key(en))
    st.caption(f"`{en}`　｜　{y1}–{y2}　｜　前 {top_n} 篇　｜　📦 快取 {age}")

    if year_relaxed:
        st.info(
            f"ℹ️ 「{zh}」在 {y1}–{y2} 年間文獻不足 10 篇，"
            "已自動顯示全部年份的結果。可嘗試調整左側年份滑桿。"
        )

    if df.empty:
        st.warning("所有結果都被排除關鍵字篩掉了，請調整排除詞設定。")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("找到文獻", f"{len(df)} 篇")
    years = pd.to_numeric(df["年份"], errors="coerce").dropna()
    c2.metric("最新年份", f"{int(years.max())} 年" if not years.empty else "—")
    c3.metric("平均年份", f"{int(years.mean())} 年" if not years.empty else "—")

    for idx, row in df.iterrows():
        j_tag = f"｜{row['期刊']}" if row["期刊"] else ""
        y_tag = row["年份"] or "年份不明"
        with st.expander(f"#{idx}　{row['標題']}　（{y_tag}{j_tag}）"):
            st.markdown(f"**作者：** {row['作者']}")
            st.markdown(f"**期刊：** {row['期刊'] or '（未知）'}")
            st.markdown(f"**摘要：** {row['摘要'] or '（無摘要）'}")
            if row["連結"]:
                st.markdown(f"[🔗 查看原文 / PubMed]({row['連結']})")

    csv = df.to_csv(index=True, encoding="utf-8-sig")
    st.download_button(
        f"⬇️ 下載「{zh}」文獻清單 (CSV)", csv,
        file_name=f"pubmed_{_safe_key(en)}_{y1}_{y2}.csv",
        mime="text/csv"
    )

# ─────────────────────────────────────────
# 單一主題模式
# ─────────────────────────────────────────
def display_topic(en: str, zh: str):
    st.markdown(f"### {zh}")
    raw = load_cache(_raw_cache_key(en))  # 先看有無快取

    if raw is None:
        # 無快取：顯示按鈕，不自動觸發 API
        st.info("📭 此主題尚無快取。點擊下方按鈕開始抓取（約 5~15 秒）。")
        if not st.button(f"🔍 抓取「{zh}」的文獻", key=f"fetch_{en}"):
            return
        with st.spinner(f"正在從 PubMed 抓取「{zh}」..."):
            raw = fetch_raw(en)
        if raw is None:
            st.error("抓取失敗，請稍後再試。")
            return

    render_papers(en, zh, raw)

# ─────────────────────────────────────────
# 全部總覽模式
# ─────────────────────────────────────────
def display_all():
    st.subheader("🗂️ 所有主題總覽（各顯示前 5 篇）")
    st.caption("總覽與個別主題共用快取，總覽抓完後切換個別主題不需重抓。")

    # 計算哪些主題還沒有快取
    missing = [(en, zh) for en, zh in topics if load_cache(_raw_cache_key(en)) is None]
    cached  = [(en, zh) for en, zh in topics if load_cache(_raw_cache_key(en)) is not None]

    if missing:
        st.warning(
            f"共 {len(missing)} 個主題尚無快取：\n"
            + "、".join(zh for _, zh in missing)
        )
        if not st.button(f"📥 開始抓取 {len(missing)} 個未快取主題", key="load_all"):
            st.info("點擊上方按鈕開始抓取。有快取的 "
                    f"{len(cached)} 個主題會直接顯示，不重複打 API。")
            # 先顯示已有快取的主題
            _render_overview(cached, fetch_missing=False)
            return
        _render_overview(topics, fetch_missing=True)
    else:
        # 全部有快取，直接顯示
        _render_overview(topics, fetch_missing=False)

def _render_overview(topic_list: list, fetch_missing: bool):
    overview_rows = []
    progress = st.progress(0)

    for i, (en, zh) in enumerate(topic_list):
        progress.progress((i + 1) / len(topic_list), text=f"載入「{zh}」（{i+1}/{len(topic_list)}）")

        raw = load_cache(_raw_cache_key(en))

        if raw is None:
            if fetch_missing:
                with st.spinner(f"抓取「{zh}」中..."):
                    raw = fetch_raw(en)
            if raw is None:
                st.warning(f"「{zh}」抓取失敗，跳過。")
                continue

        df, _ = filter_papers(raw, y1, y2, 5, exclude_kws)  # 總覽每個主題顯示 5 篇
        if df.empty:
            continue

        st.markdown(f"#### {zh}　`{en}`")
        st.dataframe(df[["標題", "期刊", "年份", "作者"]], use_container_width=True)

        for _, row in df.iterrows():
            overview_rows.append({"主題（中文）": zh, "主題（英文）": en, **row.to_dict()})

    progress.empty()

    if overview_rows:
        st.divider()
        st.download_button(
            "⬇️ 下載所有主題總覽 (CSV)",
            pd.DataFrame(overview_rows).to_csv(index=False, encoding="utf-8-sig"),
            file_name=f"PT_overview_{y1}_{y2}.csv",
            mime="text/csv"
        )

# ─────────────────────────────────────────
# 顯示入口
# ─────────────────────────────────────────
if show_all:
    display_all()
else:
    en, zh = selected
    display_topic(en, zh)

st.divider()
st.caption(
    "📚 PT 文章發想站 Phase 1　｜　"
    "資料來源：[PubMed / NCBI](https://pubmed.ncbi.nlm.nih.gov/)　｜　"
    f"完全免費，不需要 API Key　｜　快取有效期：{CACHE_DAYS} 天"
)

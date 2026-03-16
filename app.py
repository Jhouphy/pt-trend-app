import streamlit as st
import requests
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta

# ─────────────────────────────────────────
# 頁面設定
# ─────────────────────────────────────────
st.set_page_config(
    page_title="PT 文章發想站",
    page_icon="📚",
    layout="wide"
)

# ─────────────────────────────────────────
# 快取設定（7 天）
# ─────────────────────────────────────────
CACHE_DIR = "cache"
CACHE_DAYS = 7
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return os.path.join(CACHE_DIR, f"{safe}.json")

def load_cache(key: str):
    path = get_cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        saved_at = datetime.fromisoformat(cached["timestamp"])
        if datetime.now() - saved_at < timedelta(days=CACHE_DAYS):
            return cached["data"]
    except Exception:
        pass
    return None

def save_cache(key: str, data):
    path = get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "data": data}, f, ensure_ascii=False)
    except Exception as e:
        st.warning(f"快取儲存失敗：{e}")

def cache_age_str(key: str) -> str:
    path = get_cache_path(key)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        saved_at = datetime.fromisoformat(cached["timestamp"])
        diff = datetime.now() - saved_at
        hours = int(diff.total_seconds() / 3600)
        if hours < 24:
            return f"（{hours} 小時前更新）"
        else:
            return f"（{diff.days} 天前更新）"
    except Exception:
        return ""

# ─────────────────────────────────────────
# 主題清單（20 個 PT 核心主題）
# ─────────────────────────────────────────
DEFAULT_TOPICS = [
    ("adhesive capsulitis",          "五十肩（沾黏性肩關節囊炎）"),
    ("disc herniation",              "椎間盤突出"),
    ("lateral epicondylitis",        "網球肘（外側上髁炎）"),
    ("medial epicondylitis",         "高爾夫球肘（內側上髁炎）"),
    ("carpal tunnel syndrome",       "腕隧道症候群"),
    ("osteoarthritis",               "退化性關節炎（骨關節炎）"),
    ("meniscus injury",              "膝蓋半月板損傷"),
    ("plantar fasciitis",            "足底筋膜炎"),
    ("sciatica",                     "坐骨神經痛"),
    ("cervical spondylosis",         "頸椎病"),
    ("low back pain",                "腰痛"),
    ("subacromial impingement syndrome", "肩峰下夾擠症候群"),
    ("patellofemoral pain syndrome", "髕骨股骨疼痛症候群"),
    ("joint replacement rehabilitation", "關節置換術後復健"),
    ("knee pain",                    "膝關節疼痛"),
    ("scoliosis",                    "脊椎側彎"),
    ("myofascial pain syndrome",     "肌筋膜疼痛症候群"),
    ("rotator cuff injury",          "旋轉肌袖損傷"),
    ("ankle sprain",                 "踝關節扭傷"),
    ("piriformis syndrome",          "梨狀肌症候群"),
]

# ─────────────────────────────────────────
# Semantic Scholar API
# ─────────────────────────────────────────
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

def fetch_papers(topic: str, year_start: int, year_end: int, limit: int = 30) -> list:
    cache_key = f"papers_{topic}_{year_start}_{year_end}_{limit}"
    cached = load_cache(cache_key)
    if cached:
        return cached

    # year + sort=citationCount 同時使用會讓結果大幅減少
    # 改為先抓 100 筆，再在 Python 端過濾年份
    params = {
        "query": topic,
        "fields": "title,authors,year,citationCount,abstract,externalIds,openAccessPdf,publicationVenue",
        "sort": "citationCount:desc",
        "limit": 100,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(3 + attempt * 2)  # 3 → 5 → 7 秒
            resp = requests.get(SEMANTIC_SCHOLAR_URL, params=params, timeout=20)

            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                st.warning(f"⚠️ Semantic Scholar 限流（第 {attempt+1} 次），等待 {wait} 秒後重試...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            all_papers = data.get("data", [])

            # Python 端過濾年份
            filtered = [
                p for p in all_papers
                if p.get("year") and year_start <= int(p["year"]) <= year_end
            ]
            filtered = sorted(filtered, key=lambda x: x.get("citationCount", 0), reverse=True)[:limit]

            save_cache(cache_key, filtered)
            return filtered

        except requests.exceptions.HTTPError as e:
            if attempt == max_retries - 1:
                st.error(f"API 錯誤（已重試 {max_retries} 次）：{e}")
            continue
        except Exception as e:
            st.error(f"查詢失敗：{e}")
            return []

    return []

def papers_to_df(papers: list, exclude_keywords: list) -> pd.DataFrame:
    rows = []
    for p in papers:
        title    = p.get("title", "") or ""
        abstract = p.get("abstract", "") or ""

        # 排除關鍵字篩選
        excluded = any(
            kw.strip().lower() in title.lower() or kw.strip().lower() in abstract.lower()
            for kw in exclude_keywords if kw.strip()
        )
        if excluded:
            continue

        # 作者
        authors    = p.get("authors", []) or []
        author_str = ", ".join(a.get("name", "") for a in authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        # 期刊名稱
        venue      = p.get("publicationVenue") or {}
        journal    = venue.get("name", "") or ""

        # 連結（優先 DOI）
        ext_ids = p.get("externalIds") or {}
        doi     = ext_ids.get("DOI", "")
        link    = f"https://doi.org/{doi}" if doi else ""
        if not link:
            pdf_info = p.get("openAccessPdf") or {}
            link = pdf_info.get("url", "")

        rows.append({
            "標題":   title,
            "作者":   author_str,
            "期刊":   journal,
            "年份":   p.get("year", ""),
            "引用數": p.get("citationCount", 0),
            "摘要":   abstract[:300] + "…" if len(abstract) > 300 else abstract,
            "連結":   link,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("引用數", ascending=False).reset_index(drop=True)
        df.index += 1
    return df

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站｜文獻情報")
st.caption("透過 Semantic Scholar 抓取物理治療相關主題近年最高引用文獻，快速找到衛教文章的科學依據")

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 查詢設定")

    current_year = datetime.now().year
    year_range = st.slider(
        "文獻年份範圍",
        min_value=2010,
        max_value=current_year,
        value=(current_year - 7, current_year),
        step=1
    )
    year_start, year_end = year_range

    top_n = st.selectbox("每個主題顯示前幾名", options=[10, 20, 30], index=1)

    st.divider()

    # 排除關鍵字
    st.subheader("🚫 排除關鍵字")
    st.caption("含有這些詞的論文會被過濾（逗號分隔）")
    exclude_input = st.text_area(
        label="排除詞",
        value="animal, rat, mice, cadaver, pediatric",
        height=100,
        label_visibility="collapsed"
    )
    exclude_keywords = [k.strip() for k in exclude_input.split(",") if k.strip()]

    st.divider()

    # 主題管理
    st.subheader("📋 主題管理")

    if "topics" not in st.session_state:
        st.session_state.topics = DEFAULT_TOPICS.copy()

    # 新增主題
    new_en = st.text_input("英文搜尋詞", placeholder="e.g. shoulder impingement")
    new_zh = st.text_input("中文標籤",   placeholder="e.g. 肩夾擠症候群")
    if st.button("➕ 新增主題"):
        existing_en = [t[0] for t in st.session_state.topics]
        if new_en and new_en not in existing_en:
            st.session_state.topics.append((new_en, new_zh or new_en))
            st.success(f"已新增：{new_zh or new_en}")
        elif new_en in existing_en:
            st.warning("此主題已存在")

    # 刪除主題
    topic_labels = ["（不刪除）"] + [f"{zh}（{en}）" for en, zh in st.session_state.topics]
    del_choice = st.selectbox("刪除主題", options=topic_labels)
    if st.button("🗑️ 刪除") and del_choice != "（不刪除）":
        idx = topic_labels.index(del_choice) - 1
        removed = st.session_state.topics.pop(idx)
        st.success(f"已刪除：{removed[1]}")

    st.divider()

    if st.button("🔄 清除快取（重新抓取）"):
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except Exception:
                pass
        st.success("快取已清除。")

    st.info(f"📦 快取有效期：{CACHE_DAYS} 天\n\n文獻資料每週自動更新。")

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
topics = st.session_state.topics

def topic_label(t):
    en, zh = t
    return f"{zh}　({en})"

selected = st.selectbox(
    "選擇查詢主題",
    options=topics,
    format_func=topic_label
)

show_all = st.toggle("顯示所有主題總覽", value=False)
st.divider()

# ─────────────────────────────────────────
# 單一主題顯示
# ─────────────────────────────────────────
def display_topic(topic_tuple):
    en, zh = topic_tuple
    cache_key = f"papers_{en}_{year_start}_{year_end}_{top_n}"

    with st.spinner(f"載入「{zh}」的文獻資料..."):
        papers = fetch_papers(en, year_start, year_end, limit=top_n)

    from_cache = load_cache(cache_key) is not None
    age = cache_age_str(cache_key)

    st.markdown(f"### {zh}")
    st.caption(f"`{en}`　｜　{year_start}–{year_end}　｜　引用數前 {top_n} 名　｜　{'📦 快取' if from_cache else '🔴 即時'} {age}")

    if not papers:
        st.warning("查無文獻，請確認主題名稱或調整年份範圍。")
        return

    df = papers_to_df(papers, exclude_keywords)

    if df.empty:
        st.warning("所有結果都被排除關鍵字篩掉了，請調整排除詞設定。")
        return

    # 統計指標
    c1, c2, c3 = st.columns(3)
    c1.metric("文獻數", f"{len(df)} 篇")
    c2.metric("最高引用", f"{df['引用數'].max():,} 次")
    c3.metric("平均引用", f"{int(df['引用數'].mean()):,} 次")

    # 論文清單
    for idx, row in df.iterrows():
        journal_tag = f"｜{row['期刊']}" if row["期刊"] else ""
        with st.expander(
            f"#{idx}　{row['標題']}　（{row['年份']}{journal_tag}｜引用 {row['引用數']:,} 次）"
        ):
            st.markdown(f"**作者：** {row['作者']}")
            st.markdown(f"**期刊：** {row['期刊'] if row['期刊'] else '（未知）'}")
            st.markdown(f"**摘要：** {row['摘要'] if row['摘要'] else '（無摘要）'}")
            if row["連結"]:
                st.markdown(f"[🔗 查看原文]({row['連結']})")
            else:
                st.caption("（無公開連結）")

    # CSV 下載
    csv = df.to_csv(index=True, encoding="utf-8-sig")
    st.download_button(
        label=f"⬇️ 下載「{zh}」文獻清單 (CSV)",
        data=csv,
        file_name=f"papers_{en.replace(' ', '_')}_{year_start}_{year_end}.csv",
        mime="text/csv"
    )

# ─────────────────────────────────────────
# 全部主題總覽
# ─────────────────────────────────────────
def display_all():
    st.subheader("🗂️ 所有主題總覽（各顯示前 5 名）")
    st.caption("切換到單一主題模式可查看完整清單與摘要")

    overview_rows = []

    for en, zh in topics:
        with st.spinner(f"載入「{zh}」..."):
            papers = fetch_papers(en, year_start, year_end, limit=30)
        df = papers_to_df(papers, exclude_keywords)
        if df.empty:
            continue

        st.markdown(f"#### {zh}　`{en}`")
        display_df = df[["標題", "期刊", "年份", "引用數", "作者"]].head(5)
        st.dataframe(display_df, use_container_width=True)

        for _, row in df.head(5).iterrows():
            overview_rows.append({
                "主題（中文）": zh,
                "主題（英文）": en,
                **row.to_dict()
            })

        time.sleep(0.5)

    if overview_rows:
        st.divider()
        overview_df = pd.DataFrame(overview_rows)
        st.download_button(
            label="⬇️ 下載所有主題總覽 (CSV)",
            data=overview_df.to_csv(index=False, encoding="utf-8-sig"),
            file_name=f"PT_literature_overview_{year_start}_{year_end}.csv",
            mime="text/csv"
        )

# ─────────────────────────────────────────
# 顯示
# ─────────────────────────────────────────
if show_all:
    display_all()
else:
    display_topic(selected)

# 頁尾
st.divider()
st.caption(
    "📚 PT 文章發想站 Phase 1　｜　"
    "資料來源：[Semantic Scholar](https://www.semanticscholar.org/)　｜　"
    "免費學術 API，不需要 API Key　｜　"
    f"快取有效期：{CACHE_DAYS} 天"
)

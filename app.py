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
# 主題清單
# ─────────────────────────────────────────
DEFAULT_TOPICS = [
    ("adhesive capsulitis",              "五十肩（沾黏性肩關節囊炎）"),
    ("disc herniation",                  "椎間盤突出"),
    ("lateral epicondylitis",            "網球肘（外側上髁炎）"),
    ("medial epicondylitis",             "高爾夫球肘（內側上髁炎）"),
    ("carpal tunnel syndrome",           "腕隧道症候群"),
    ("osteoarthritis rehabilitation",    "退化性關節炎（骨關節炎）"),
    ("meniscus injury rehabilitation",   "膝蓋半月板損傷"),
    ("plantar fasciitis",                "足底筋膜炎"),
    ("sciatica",                         "坐骨神經痛"),
    ("cervical spondylosis",             "頸椎病"),
    ("low back pain physical therapy",   "腰痛"),
    ("subacromial impingement syndrome", "肩峰下夾擠症候群"),
    ("patellofemoral pain syndrome",     "髕骨股骨疼痛症候群"),
    ("joint replacement rehabilitation", "關節置換術後復健"),
    ("knee pain physical therapy",       "膝關節疼痛"),
    ("scoliosis",                        "脊椎側彎"),
    ("myofascial pain syndrome",         "肌筋膜疼痛症候群"),
    ("rotator cuff injury rehabilitation","旋轉肌袖損傷"),
    ("ankle sprain rehabilitation",      "踝關節扭傷"),
    ("piriformis syndrome",              "梨狀肌症候群"),
]

# ─────────────────────────────────────────
# PubMed API
# 完全免費，不需要 API Key
# 官方建議速率：每秒最多 3 次請求
# ─────────────────────────────────────────
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_BASE    = "https://pubmed.ncbi.nlm.nih.gov"

def search_pubmed_ids(topic: str, limit: int) -> list:
    """Step 1：用關鍵字搜尋，取得論文 ID 清單（不在 API 端限制年份）
    
    ⚠️ 不在 API 端篩選年份的原因：
    PubMed 的 relevance 排序受日期範圍影響，
    範圍越大反而會讓舊論文擠進來、近年文獻掉出去。
    改為一次抓足夠多的 ID，再於 Python 端過濾年份，確保結果一致。
    """
    params = {
        "db": "pubmed",
        "term": f"{topic}[Title/Abstract] AND physical therapy[Title/Abstract]",
        "retmax": 200,  # 多抓一些，讓 Python 端過濾後仍有足夠數量
        "sort": "relevance",
        "retmode": "json",
    }
    time.sleep(0.4)
    resp = requests.get(PUBMED_ESEARCH, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("esearchresult", {}).get("idlist", [])

def fetch_pubmed_details(pmids: list) -> list:
    """Step 2：用 ID 清單批量抓取論文詳細資料（一次打 API，節省請求次數）"""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    time.sleep(0.4)
    resp = requests.get(PUBMED_EFETCH, params=params, timeout=20)
    resp.raise_for_status()

    papers = []
    root = ET.fromstring(resp.content)

    for article in root.findall(".//PubmedArticle"):
        try:
            # 標題
            title_el = article.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            # 作者
            authors = []
            for author in article.findall(".//Author")[:3]:
                last  = author.findtext("LastName", "")
                first = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())
            author_count = len(article.findall(".//Author"))
            author_str = ", ".join(authors)
            if author_count > 3:
                author_str += " et al."

            # 期刊
            journal = article.findtext(".//Journal/Title", "") or \
                      article.findtext(".//ISOAbbreviation", "")

            # 年份
            year = article.findtext(".//PubDate/Year", "") or \
                   article.findtext(".//PubDate/MedlineDate", "")[:4]

            # PMID
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            # 摘要
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join("".join(p.itertext()) for p in abstract_parts)

            # DOI
            doi = ""
            for eloc in article.findall(".//ELocationID"):
                if eloc.get("EIdType") == "doi":
                    doi = eloc.text or ""
                    break

            link = f"https://doi.org/{doi}" if doi else (f"{PUBMED_BASE}/{pmid}" if pmid else "")

            papers.append({
                "title":    title,
                "authors":  author_str,
                "journal":  journal,
                "year":     year,
                "pmid":     pmid,
                "abstract": abstract,
                "link":     link,
            })
        except Exception:
            continue

    return papers

# 固定的 base cache key（不含 year_start/year_end/limit，讓總覽和單一主題共用）
def _base_cache_key(topic: str) -> str:
    return f"pubmed_base_{topic}"

def fetch_papers(topic: str, year_start: int, year_end: int, limit: int = 30) -> list:
    """統一入口：搜尋 + 抓取詳細資料，含快取與重試
    
    快取策略：用 base key 儲存完整原始資料（不含年份/筆數篩選），
    顯示時再動態過濾年份、取前 limit 筆。
    這樣總覽模式和單一主題模式可以共用同一份快取，不會重複打 API。
    """
    base_key = _base_cache_key(topic)
    cached_raw = load_cache(base_key)

    if cached_raw is None:
        # 沒有快取，需要打 API
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Step 1：搜尋 ID（不限年份，多抓 200 筆）
                pmids = search_pubmed_ids(topic, limit=200)
                if not pmids:
                    return []

                # Step 2：批量抓取詳細資料（只打一次 API）
                papers = fetch_pubmed_details(pmids)
                save_cache(base_key, papers)
                cached_raw = papers
                break

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    wait = 30 * (attempt + 1)
                    st.warning(f"⚠️ PubMed 限流（第 {attempt+1} 次），等待 {wait} 秒後重試...")
                    time.sleep(wait)
                else:
                    if attempt == max_retries - 1:
                        st.error(f"API 錯誤：{e}")
                    time.sleep(5)
            except Exception as e:
                if attempt == max_retries - 1:
                    st.error(f"查詢失敗：{e}")
                time.sleep(5)

        if cached_raw is None:
            return []

    # Python 端過濾年份（這樣改年份不需要重新打 API）
    filtered = []
    year_relaxed = False
    for p in cached_raw:
        try:
            y = int(str(p.get("year", "0"))[:4])
            if year_start <= y <= year_end:
                filtered.append(p)
        except Exception:
            continue

    # 若篩選後不足 10 筆，自動放寬年份顯示所有資料
    if len(filtered) < 10:
        filtered = cached_raw
        year_relaxed = True

    # 依年份新到舊排序，取前 limit 筆
    filtered = sorted(filtered, key=lambda x: int(str(x.get("year", "0"))[:4]), reverse=True)[:limit]

    # 標記年份是否放寬
    for p in filtered:
        p["_year_relaxed"] = year_relaxed

    return filtered

def papers_to_df(papers: list, exclude_keywords: list) -> pd.DataFrame:
    rows = []
    for p in papers:
        title    = p.get("title", "") or ""
        abstract = p.get("abstract", "") or ""

        # 排除關鍵字
        excluded = any(
            kw.lower() in title.lower() or kw.lower() in abstract.lower()
            for kw in exclude_keywords if kw.strip()
        )
        if excluded:
            continue

        rows.append({
            "標題":   title,
            "作者":   p.get("authors", ""),
            "期刊":   p.get("journal", ""),
            "年份":   p.get("year", ""),
            "摘要":   abstract[:300] + "…" if len(abstract) > 300 else abstract,
            "連結":   p.get("link", ""),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        # PubMed 沒有引用數，改依年份新到舊排序
        df["年份"] = pd.to_numeric(df["年份"], errors="coerce")
        df = df.sort_values("年份", ascending=False).reset_index(drop=True)
        df.index += 1
    return df

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站｜文獻情報")
st.caption("透過 PubMed 資料庫抓取物理治療相關主題文獻，快速找到衛教文章的科學依據")
st.success("✅ 資料來源：PubMed（美國國家醫學圖書館）｜免費、穩定、不需要 API Key")

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

    top_n = st.selectbox("每個主題顯示幾篇", options=[10, 20, 30], index=1)

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

    new_en = st.text_input("英文搜尋詞", placeholder="e.g. shoulder impingement")
    new_zh = st.text_input("中文標籤",   placeholder="e.g. 肩夾擠症候群")
    if st.button("➕ 新增主題"):
        existing_en = [t[0] for t in st.session_state.topics]
        if new_en and new_en not in existing_en:
            st.session_state.topics.append((new_en, new_zh or new_en))
            st.success(f"已新增：{new_zh or new_en}")
        elif new_en in existing_en:
            st.warning("此主題已存在")

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
        st.success("✅ 快取已清除。請逐一點擊各主題的抓取按鈕。")

    st.info(
        f"📦 快取有效期：{CACHE_DAYS} 天\n\n"
        "有快取時開 App 不打 API，\n完全不會被限流。"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
topics = st.session_state.topics

selected = st.selectbox(
    "選擇查詢主題",
    options=topics,
    format_func=lambda t: f"{t[1]}　({t[0]})"
)

show_all = st.toggle("顯示所有主題總覽", value=False)
st.divider()

# ─────────────────────────────────────────
# 單一主題顯示
# ─────────────────────────────────────────
def display_topic(topic_tuple):
    en, zh = topic_tuple
    base_key = _base_cache_key(en)  # 共用 base key，與總覽模式一致
    has_cache = load_cache(base_key) is not None

    if not has_cache:
        st.markdown(f"### {zh}")
        st.caption(f"`{en}`　｜　{year_start}–{year_end}　｜　前 {top_n} 篇")
        st.info("📭 此主題尚無快取。點擊下方按鈕開始抓取（約 5~15 秒）。")
        if not st.button(f"🔍 抓取「{zh}」的文獻", key=f"fetch_{en}"):
            return
        with st.spinner(f"正在從 PubMed 抓取「{zh}」的文獻..."):
            papers = fetch_papers(en, year_start, year_end, limit=top_n)
    else:
        papers = fetch_papers(en, year_start, year_end, limit=top_n)

    age = cache_age_str(base_key)
    from_cache = load_cache(base_key) is not None

    st.markdown(f"### {zh}")
    st.caption(
        f"`{en}`　｜　{year_start}–{year_end}　｜　前 {top_n} 篇　｜　"
        f"{'📦 快取' if from_cache else '🔴 即時'} {age}"
    )

    if not papers:
        st.warning("查無文獻，請確認主題名稱或調整年份範圍。")
        return

    # 放寬年份提示
    if any(p.get("_year_relaxed") for p in papers):
        st.info(
            f"ℹ️ 「{zh}」在 {year_start}–{year_end} 年間文獻不足 10 篇，"
            "已自動擴大至 2000 年至今以確保結果數量。"
        )

    df = papers_to_df(papers, exclude_keywords)

    if df.empty:
        st.warning("所有結果都被排除關鍵字篩掉了，請調整排除詞設定。")
        return

    # 統計
    c1, c2, c3 = st.columns(3)
    c1.metric("找到文獻", f"{len(df)} 篇")
    valid_years = df["年份"].dropna()
    c2.metric("最新年份", f"{int(valid_years.max())} 年" if not valid_years.empty else "—")
    c3.metric("平均年份", f"{int(valid_years.mean())} 年" if not valid_years.empty else "—")

    # 論文清單
    for idx, row in df.iterrows():
        journal_tag = f"｜{row['期刊']}" if row["期刊"] else ""
        year_tag = f"{int(row['年份'])}" if pd.notna(row["年份"]) else "年份不明"
        with st.expander(f"#{idx}　{row['標題']}　（{year_tag}{journal_tag}）"):
            st.markdown(f"**作者：** {row['作者']}")
            st.markdown(f"**期刊：** {row['期刊'] if row['期刊'] else '（未知）'}")
            st.markdown(f"**摘要：** {row['摘要'] if row['摘要'] else '（無摘要）'}")
            if row["連結"]:
                st.markdown(f"[🔗 查看原文 / PubMed]({row['連結']})")
            else:
                st.caption("（無公開連結）")

    # CSV 下載
    csv = df.to_csv(index=True, encoding="utf-8-sig")
    st.download_button(
        label=f"⬇️ 下載「{zh}」文獻清單 (CSV)",
        data=csv,
        file_name=f"pubmed_{en.replace(' ', '_')}_{year_start}_{year_end}.csv",
        mime="text/csv"
    )

# ─────────────────────────────────────────
# 全部主題總覽
# ─────────────────────────────────────────
def display_all():
    st.subheader("🗂️ 所有主題總覽（各顯示前 5 篇）")
    st.caption("切換到單一主題模式可查看完整清單與摘要")

    # 總覽模式也用按鈕觸發，避免自動打 API
    if not st.button("📥 載入所有主題（需要一段時間）", key="load_all"):
        st.info("點擊上方按鈕開始載入所有主題的文獻（每個主題間隔 2 秒，避免限流）。")
        return

    overview_rows = []
    progress = st.progress(0, text="開始載入...")

    for i, (en, zh) in enumerate(topics):
        progress.progress((i + 1) / len(topics), text=f"載入「{zh}」中...（{i+1}/{len(topics)}）")

        has_cache = load_cache(_base_cache_key(en)) is not None

        with st.spinner(f"載入「{zh}」..."):
            papers = fetch_papers(en, year_start, year_end, limit=30)

        df = papers_to_df(papers, exclude_keywords)
        if df.empty:
            continue

        st.markdown(f"#### {zh}　`{en}`")
        st.dataframe(
            df[["標題", "期刊", "年份", "作者"]].head(5),
            use_container_width=True
        )

        for _, row in df.head(5).iterrows():
            overview_rows.append({
                "主題（中文）": zh,
                "主題（英文）": en,
                **row.to_dict()
            })

        if not has_cache:
            time.sleep(2)  # 只有在沒有快取（需要打 API）時才等待

    progress.empty()

    if overview_rows:
        st.divider()
        overview_df = pd.DataFrame(overview_rows)
        st.download_button(
            label="⬇️ 下載所有主題總覽 (CSV)",
            data=overview_df.to_csv(index=False, encoding="utf-8-sig"),
            file_name=f"PT_pubmed_overview_{year_start}_{year_end}.csv",
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
    "資料來源：[PubMed / NCBI](https://pubmed.ncbi.nlm.nih.gov/)　｜　"
    "完全免費，不需要 API Key　｜　"
    f"快取有效期：{CACHE_DAYS} 天"
)

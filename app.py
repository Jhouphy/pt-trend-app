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
# 主題清單預設值
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
    ("subacromial impingement",          "肩峰下夾擠症候群"),
    ("patellofemoral pain syndrome",     "髕骨股骨疼痛症候群"),
    ("joint replacement",                "關節置換術後復健"),
    ("knee pain",                        "膝關節疼痛"),
    ("scoliosis",                        "脊椎側彎"),
    ("myofascial pain syndrome",         "肌筋膜疼痛症候群"),
    ("rotator cuff",                     "旋轉肌袖損傷"),
    ("ankle sprain",                     "踝關節扭傷"),
    ("piriformis syndrome",              "梨狀肌症候群"),
]

# ─────────────────────────────────────────
# 主題清單永久儲存
# 存成 custom_topics.json，重啟不會遺失
# ─────────────────────────────────────────
TOPICS_FILE = "custom_topics.json"

def load_topics() -> list:
    """優先從 JSON 檔讀取，失敗才用預設清單"""
    if os.path.exists(TOPICS_FILE):
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # json 存的是 list of list，轉回 list of tuple
            result = [tuple(item) for item in data if len(item) == 2]
            if result:
                return result
        except Exception as e:
            st.sidebar.warning(f"⚠️ 讀取自定義清單失敗（{e}），使用預設清單。")
    return DEFAULT_TOPICS.copy()

def save_topics(topics_list: list):
    """永久儲存主題清單到 JSON 檔"""
    try:
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            # 存成 list of list（JSON 不支援 tuple）
            json.dump([list(t) for t in topics_list], f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"❌ 清單儲存失敗：{e}")
        return False

# ─────────────────────────────────────────
# PubMed API
# ─────────────────────────────────────────
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def _search_ids(topic: str) -> list:
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
                "title": title, "authors": author_str, "journal": journal,
                "year": year, "abstract": abstract, "link": link,
            })
        except Exception:
            continue
    return papers

def fetch_raw(topic: str) -> list | None:
    key    = _raw_cache_key(topic)
    cached = load_cache(key)
    if cached is not None:
        return cached

    max_retries = 3
    for attempt in range(max_retries):
        try:
            pmids  = _search_ids(topic)
            papers = _fetch_details(pmids)
            save_cache(key, papers)
            return papers
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            wait = 30 * (attempt + 1)
            st.warning(f"⚠️ PubMed 限流（第 {attempt+1} 次），等待 {wait} 秒...")
            time.sleep(wait)
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"查詢失敗：{e}")
            time.sleep(5)
    return None

def filter_papers(raw: list, year_start: int, year_end: int,
                  limit: int, exclude_kws: list) -> tuple:
    in_range = [
        p for p in raw
        if p.get("year", "").isdigit() and year_start <= int(p["year"]) <= year_end
    ]
    year_relaxed = False
    if len(in_range) < 10:
        in_range     = raw
        year_relaxed = True

    in_range = sorted(
        in_range,
        key=lambda x: int(x["year"]) if x.get("year", "").isdigit() else 0,
        reverse=True
    )

    rows = []
    for p in in_range:
        title    = p.get("title", "") or ""
        abstract = p.get("abstract", "") or ""
        if any(kw.lower() in title.lower() or kw.lower() in abstract.lower()
               for kw in exclude_kws if kw.strip()):
            continue
        rows.append({
            "標題": title,
            "作者": p.get("authors", ""),
            "期刊": p.get("journal", ""),
            "年份": p.get("year", ""),
            "摘要": (abstract[:300] + "…") if len(abstract) > 300 else abstract,
            "連結": p.get("link", ""),
        })
        if len(rows) >= limit:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df.index = range(1, len(df) + 1)
    return df, year_relaxed

# ─────────────────────────────────────────
# Session state 初始化（只在第一次執行時設定）
# ─────────────────────────────────────────
if "topics" not in st.session_state:
    st.session_state.topics = load_topics()

if "show_editor" not in st.session_state:
    st.session_state.show_editor = False

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

    # ── 主題管理標題 + ✏️ 按鈕 ──
    col_title, col_btn = st.columns([3, 1])
    col_title.subheader("📋 主題管理")
    if col_btn.button("✏️", help="編輯主題清單", use_container_width=True):
        st.session_state.show_editor = not st.session_state.show_editor

    # ── 編輯區塊（toggle 開關控制顯示）──
    if st.session_state.show_editor:
        st.caption("每行一個主題，格式：`英文搜尋詞 | 中文標籤`")

        # 把目前清單轉成文字
        current_text = "\n".join(
            f"{en} | {zh}" for en, zh in st.session_state.topics
        )
        edited_text = st.text_area(
            "主題清單編輯框",
            value=current_text,
            height=360,
            label_visibility="collapsed",
            key="editor_textarea"
        )

        btn_col1, btn_col2 = st.columns(2)

        # ── 套用按鈕 ──
        if btn_col1.button("✅ 套用", use_container_width=True, key="apply_btn"):
            new_topics = []
            errors     = []
            for i, line in enumerate(edited_text.strip().splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                if "|" not in line:
                    errors.append(f"第 {i} 行格式錯誤（缺少 |）：{line}")
                    continue
                parts  = line.split("|", 1)
                en_new = parts[0].strip()
                zh_new = parts[1].strip() if len(parts) > 1 else ""
                if en_new:
                    new_topics.append((en_new, zh_new or en_new))

            if errors:
                for err in errors:
                    st.error(err)
            elif not new_topics:
                st.error("清單不能是空的！")
            else:
                # 1. 寫入 JSON 檔案（永久儲存）
                ok = save_topics(new_topics)
                # 2. 更新 session_state
                st.session_state.topics = new_topics
                # 3. 清除 selectbox 的快取索引，避免舊索引衝突
                for k in list(st.session_state.keys()):
                    if k.startswith("selectbox") or k == "topic_select":
                        del st.session_state[k]
                # 4. 關閉編輯器
                st.session_state.show_editor = False
                if ok:
                    st.success(f"✅ 已儲存 {len(new_topics)} 個主題！")
                st.rerun()

        # ── 取消按鈕 ──
        if btn_col2.button("✖️ 取消", use_container_width=True, key="cancel_btn"):
            st.session_state.show_editor = False
            st.rerun()

    else:
        # 編輯器收合時，顯示目前主題清單預覽
        for en, zh in st.session_state.topics:
            st.caption(f"• {zh}　`{en}`")

    st.divider()

    if st.button("🔄 清除快取（重新抓取）"):
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except Exception:
                pass
        st.success("✅ 快取已清除。")

    st.info(
        f"📦 快取有效期：{CACHE_DAYS} 天\n\n"
        "• 總覽與個別主題共用同一份快取\n"
        "• 調整年份滑桿不需重新抓取\n"
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
    format_func=lambda t: f"{t[1]}　({t[0]})",
    key="topic_select"
)
show_all = st.toggle("顯示所有主題總覽", value=False)
st.divider()

# ─────────────────────────────────────────
# 顯示單一主題
# ─────────────────────────────────────────
def render_papers(en: str, zh: str, raw: list):
    df, year_relaxed = filter_papers(raw, y1, y2, top_n, exclude_kws)
    age = cache_age_str(_raw_cache_key(en))
    st.caption(f"`{en}`　｜　{y1}–{y2}　｜　前 {top_n} 篇　｜　📦 快取 {age}")

    if year_relaxed:
        st.info(f"ℹ️ 「{zh}」在 {y1}–{y2} 年間文獻不足 10 篇，已自動顯示全部年份。")

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

    st.download_button(
        f"⬇️ 下載「{zh}」文獻清單 (CSV)",
        df.to_csv(index=True, encoding="utf-8-sig"),
        file_name=f"pubmed_{_safe_key(en)}_{y1}_{y2}.csv",
        mime="text/csv"
    )

def display_topic(en: str, zh: str):
    st.markdown(f"### {zh}")
    raw = load_cache(_raw_cache_key(en))

    if raw is None:
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
# 全部主題總覽
# ─────────────────────────────────────────
def display_all():
    st.subheader("🗂️ 所有主題總覽（各顯示前 5 篇）")
    missing = [(en, zh) for en, zh in topics if load_cache(_raw_cache_key(en)) is None]
    cached  = [(en, zh) for en, zh in topics if load_cache(_raw_cache_key(en)) is not None]

    if missing:
        st.warning(f"共 {len(missing)} 個主題尚無快取：" + "、".join(zh for _, zh in missing))
        if not st.button(f"📥 抓取 {len(missing)} 個未快取主題", key="load_all"):
            st.info(f"點擊上方按鈕開始抓取。已有快取的 {len(cached)} 個主題會直接顯示。")
            _render_overview(cached, fetch_missing=False)
            return
        _render_overview(topics, fetch_missing=True)
    else:
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

        df, _ = filter_papers(raw, y1, y2, 5, exclude_kws)
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

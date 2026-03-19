import streamlit as st
from urllib.parse import urlencode
import datetime
import requests
import xml.etree.ElementTree as ET
import time

st.set_page_config(page_title="PT 文章發想站", page_icon="📚", layout="wide")

# ─────────────────────────────────────────
# 預設值
# ─────────────────────────────────────────
DEFAULT_BASE = "physical therapy"
DEFAULT_EXCL = "animal, rat, mice, cadaver, pediatric"
CURRENT_YEAR = datetime.datetime.now().year

GROUP_A = [
    "neck pain", "shoulder pain", "low back pain", "knee pain",
    "plantar fasciitis", "adhesive capsulitis", "shoulder impingement",
    "myofascial pain syndrome", "ankle sprain", "osteoarthritis",
]

GROUP_B = [
    "therapy exercises", "manual therapy",
    "guidelines", "systematic reviews", "mechanism",
]

# ─────────────────────────────────────────
# Session state
# ─────────────────────────────────────────
for key, default in [("sel_a", set()), ("sel_b", set()),
                     ("results", None), ("last_query", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────
# 搜尋詞組合
# ─────────────────────────────────────────
def build_query(custom: str, sel_a: list, sel_b: list) -> str:
    parts = []
    if custom.strip():
        parts.append(f'"{custom.strip()}"')
    if sel_a:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_a) + ")")
    if sel_b:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_b) + ")")
    return " ".join(parts)

def scholar_url(query: str, base: str, excl: list, y1: int, y2: int) -> str:
    full = query
    if base.strip():
        full += f" {base.strip()}"
    for ex in excl:
        if ex.strip():
            full += f" -{ex.strip()}"
    return "https://scholar.google.com/scholar?" + urlencode({"q": full, "as_ylo": y1, "as_yhi": y2})

# ─────────────────────────────────────────
# PubMed API
# ─────────────────────────────────────────
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def pubmed_search(query: str, base: str, excl: list,
                  y1: int, y2: int, limit: int = 20) -> list:
    # 組合 PubMed 搜尋詞（用 NOT 排除）
    full = query
    if base.strip():
        full += f" {base.strip()}"
    excl_str = " NOT ".join(ex.strip() for ex in excl if ex.strip())
    if excl_str:
        full += f" NOT ({excl_str})"

    # Step 1: 取得 PMID 清單
    try:
        time.sleep(0.3)
        r = requests.get(ESEARCH, params={
            "db": "pubmed", "term": full,
            "datetype": "pdat", "mindate": str(y1), "maxdate": str(y2),
            "retmax": limit, "sort": "relevance", "retmode": "json"
        }, timeout=15)
        r.raise_for_status()
        pmids = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        st.error(f"PubMed 搜尋失敗：{e}")
        return []

    if not pmids:
        return []

    # Step 2: 批量抓詳細資料
    try:
        time.sleep(0.3)
        r2 = requests.get(EFETCH, params={
            "db": "pubmed", "id": ",".join(pmids),
            "retmode": "xml", "rettype": "abstract"
        }, timeout=20)
        r2.raise_for_status()
    except Exception as e:
        st.error(f"PubMed 抓取詳細資料失敗：{e}")
        return []

    papers = []
    for art in ET.fromstring(r2.content).findall(".//PubmedArticle"):
        try:
            title_el = art.find(".//ArticleTitle")
            title    = "".join(title_el.itertext()) if title_el is not None else ""

            auths  = art.findall(".//Author")
            names  = []
            for a in auths[:3]:
                last  = a.findtext("LastName", "")
                first = a.findtext("ForeName", "")
                if last:
                    names.append(f"{last} {first}".strip())
            authors = ", ".join(names) + (" et al." if len(auths) > 3 else "")

            journal  = art.findtext(".//Journal/Title", "") or art.findtext(".//ISOAbbreviation", "") or ""
            year_raw = art.findtext(".//PubDate/Year", "") or art.findtext(".//PubDate/MedlineDate", "") or ""
            year     = year_raw[:4]

            pmid_el = art.find(".//PMID")
            pmid    = pmid_el.text if pmid_el is not None else ""

            abs_parts = art.findall(".//AbstractText")
            abstract  = " ".join("".join(p.itertext()) for p in abs_parts)

            doi = ""
            for el in art.findall(".//ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = el.text or ""
                    break
            link = f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}" if pmid else "")

            papers.append({
                "title": title, "authors": authors, "journal": journal,
                "year": year, "abstract": abstract, "link": link, "pmid": pmid
            })
        except Exception:
            continue
    return papers

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 全域設定")
    base = st.text_input("📌 固定包含詞", value=DEFAULT_BASE)
    excl_raw = st.text_area("🚫 排除關鍵字（逗號分隔）", value=DEFAULT_EXCL, height=80)
    excl = [k.strip() for k in excl_raw.split(",") if k.strip()]
    col1, col2 = st.columns(2)
    y1 = col1.number_input("起始年份", min_value=2000, max_value=CURRENT_YEAR, value=2015)
    y2 = col2.number_input("結束年份", min_value=2000, max_value=CURRENT_YEAR, value=CURRENT_YEAR)
    result_limit = st.selectbox("顯示筆數", [10, 20, 30], index=1)

    st.divider()
    if st.button("🗑️ 清除所有選取", use_container_width=True):
        st.session_state.sel_a = set()
        st.session_state.sel_b = set()
        st.session_state.results = None
        st.rerun()

    st.divider()
    st.info(
        "**使用方式**\n\n"
        "① 輸入自訂關鍵字（選填）\n"
        "② 點選 A 組主題（選填）\n"
        "③ 點選 B 組文獻類型（選填）\n"
        "④ 按「搜尋」，結果直接顯示在頁面內\n"
        "⑤ 或點「Google Scholar」開新分頁"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站")

# ── 自訂搜尋框 ──
custom = st.text_input(
    "🔍 自訂關鍵字（選填，可搭配下方 A/B 組）",
    placeholder="e.g. rotator cuff, disc herniation, dry needling..."
)

st.divider()

# ── A 組 Tag 按鈕（每行 5 個） ──
st.markdown("**A 組：主題**　`點擊選取 / 再點取消`")
cols_a = st.columns(5)
for i, topic in enumerate(GROUP_A):
    is_sel = topic in st.session_state.sel_a
    label  = f"✅ {topic}" if is_sel else topic
    if cols_a[i % 5].button(label, key=f"a_{topic}", use_container_width=True):
        if topic in st.session_state.sel_a:
            st.session_state.sel_a.discard(topic)
        else:
            st.session_state.sel_a.add(topic)
        st.rerun()

st.divider()

# ── B 組 Tag 按鈕（一行 5 個） ──
st.markdown("**B 組：文獻類型**　`點擊選取 / 再點取消`")
cols_b = st.columns(5)
for i, btype in enumerate(GROUP_B):
    is_sel = btype in st.session_state.sel_b
    label  = f"✅ {btype}" if is_sel else btype
    if cols_b[i].button(label, key=f"b_{btype}", use_container_width=True):
        if btype in st.session_state.sel_b:
            st.session_state.sel_b.discard(btype)
        else:
            st.session_state.sel_b.add(btype)
        st.rerun()

st.divider()

# ── 搜尋區 ──
sel_a_list = sorted(st.session_state.sel_a)
sel_b_list = sorted(st.session_state.sel_b)
has_input  = custom.strip() or sel_a_list or sel_b_list

if has_input:
    query = build_query(custom.strip(), sel_a_list, sel_b_list)

    # 搜尋詞預覽
    preview = query
    if base.strip():
        preview += f" {base.strip()}"
    st.markdown("**搜尋詞：**")
    st.code(preview)

    # 按鈕列
    col_search, col_scholar = st.columns(2)

    do_search = col_search.button(
        "🔬 PubMed 搜尋（結果顯示在下方）",
        use_container_width=True, type="primary"
    )
    col_scholar.link_button(
        "🔗 Google Scholar（開新分頁）",
        url=scholar_url(query, base, excl, y1, y2),
        use_container_width=True
    )

    # ── PubMed 搜尋執行 ──
    if do_search:
        with st.spinner("正在從 PubMed 抓取文獻..."):
            st.session_state.results = pubmed_search(
                query, base, excl, y1, y2, limit=result_limit
            )
            st.session_state.last_query = preview

    # ── 顯示結果 ──
    if st.session_state.results is not None:
        papers = st.session_state.results
        st.divider()

        if not papers:
            st.warning("查無文獻，請嘗試調整關鍵字或放寬年份範圍。")
        else:
            st.subheader(f"📋 搜尋結果（共 {len(papers)} 篇）")
            st.caption(f"搜尋詞：`{st.session_state.last_query}`")

            for i, p in enumerate(papers, 1):
                j_tag = f"｜{p['journal']}" if p["journal"] else ""
                y_tag = p["year"] or "年份不明"
                with st.expander(f"#{i}　{p['title']}　（{y_tag}{j_tag}）"):
                    st.markdown(f"**作者：** {p['authors'] or '（未知）'}")
                    st.markdown(f"**期刊：** {p['journal'] or '（未知）'}")
                    st.markdown(f"**摘要：** {p['abstract'][:400] + '…' if len(p['abstract']) > 400 else p['abstract'] or '（無摘要）'}")
                    if p["link"]:
                        st.markdown(f"[🔗 查看原文 / PubMed]({p['link']})")

else:
    st.info("☝️ 輸入自訂關鍵字，或點選上方 A/B 組的標籤，搜尋按鈕會出現在這裡。")

st.divider()
st.caption("📚 PT 文章發想站　｜　文獻來源：PubMed & Google Scholar　｜　完全免費，不需要 API Key")

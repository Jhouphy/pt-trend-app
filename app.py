import streamlit as st
from urllib.parse import urlencode, quote
import datetime

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
if "sel_a" not in st.session_state:
    st.session_state.sel_a = set()
if "sel_b" not in st.session_state:
    st.session_state.sel_b = set()

# ─────────────────────────────────────────
# URL 組合
# ─────────────────────────────────────────
def build_query(custom: str, sel_a: list, sel_b: list,
                base: str, excl: list) -> str:
    parts = []
    if custom.strip():
        parts.append(f'"{custom.strip()}"')
    if sel_a:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_a) + ")")
    if sel_b:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_b) + ")")
    if base.strip():
        parts.append(base.strip())
    for ex in excl:
        if ex.strip():
            parts.append(f"-{ex.strip()}")
    return " ".join(parts)

def scholar_url(query: str, y1: int, y2: int) -> str:
    return "https://scholar.google.com/scholar?" + urlencode({
        "q": query, "as_ylo": y1, "as_yhi": y2
    })

def pubmed_url(query: str, y1: int, y2: int) -> str:
    # PubMed 不支援 -exclude 語法，改用 NOT
    pubmed_q = query
    for ex in excl_global:
        pubmed_q = pubmed_q.replace(f"-{ex}", f"NOT {ex}")
    date_filter = f"{y1}:{y2}[pdat]"
    return "https://pubmed.ncbi.nlm.nih.gov/?" + urlencode({
        "term": f"({pubmed_q}) AND {date_filter}"
    })

def pubmed_embed_url(query: str, y1: int, y2: int) -> str:
    """PubMed 嵌入式搜尋（iframe 用）"""
    date_filter = f"{y1}:{y2}[pdat]"
    full_q = f"({query}) AND {date_filter}"
    return "https://pubmed.ncbi.nlm.nih.gov/?" + urlencode({"term": full_q})

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 全域設定")
    base = st.text_input("📌 固定包含詞", value=DEFAULT_BASE)
    excl_raw = st.text_area("🚫 排除關鍵字（逗號分隔）", value=DEFAULT_EXCL, height=80)
    excl_global = [k.strip() for k in excl_raw.split(",") if k.strip()]
    c1, c2 = st.columns(2)
    y1 = c1.number_input("起始年份", min_value=2000, max_value=CURRENT_YEAR, value=2015)
    y2 = c2.number_input("結束年份", min_value=2000, max_value=CURRENT_YEAR, value=CURRENT_YEAR)

    st.divider()

    # 清除選取
    if st.button("🗑️ 清除所有選取", use_container_width=True):
        st.session_state.sel_a = set()
        st.session_state.sel_b = set()
        st.rerun()

    st.divider()
    st.info(
        "**使用方式**\n\n"
        "① 輸入自訂關鍵字（選填）\n"
        "② 點選 A 組主題（選填）\n"
        "③ 點選 B 組文獻類型（選填）\n"
        "④ 選擇 Google Scholar 或 PubMed"
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

# ── A 組：Tag 按鈕 ──
st.markdown("**A 組：主題**　`點擊選取／再點取消`")

# 用 CSS 讓按鈕看起來像 tag
st.markdown("""
<style>
div[data-testid="column"] > div > div > div > button {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    min-height: 0px;
    height: auto;
}
</style>
""", unsafe_allow_html=True)

# 每行 5 個
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

# ── B 組：Tag 按鈕 ──
st.markdown("**B 組：文獻類型**　`點擊選取／再點取消`")

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
    query = build_query(custom.strip(), sel_a_list, sel_b_list,
                        base, excl_global)

    # 搜尋詞預覽
    st.markdown("**搜尋詞預覽：**")
    st.code(query)

    # 按鈕列
    btn1, btn2 = st.columns(2)
    btn1.link_button(
        "🔗 Google Scholar（開新分頁）",
        url=scholar_url(query, y1, y2),
        use_container_width=True
    )
    btn2.link_button(
        "🔗 PubMed（開新分頁）",
        url=pubmed_url(query, y1, y2),
        use_container_width=True
    )

    st.divider()

    # ── PubMed 嵌入式結果 ──
    st.markdown("**📋 PubMed 嵌入結果（在頁面內直接瀏覽）**")
    st.caption("⚠️ Google Scholar 不允許嵌入，僅 PubMed 支援頁面內顯示")

    embed_url = pubmed_embed_url(query, y1, y2)
    st.components.v1.iframe(embed_url, height=600, scrolling=True)

else:
    st.info("☝️ 輸入自訂關鍵字，或點選上方 A/B 組的標籤，搜尋按鈕與結果會出現在這裡。")

st.divider()
st.caption("📚 PT 文章發想站　｜　Google Scholar & PubMed　｜　完全免費，不需要 API")

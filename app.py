import streamlit as st
from urllib.parse import urlencode
import datetime

st.set_page_config(page_title="PT 文章發想站", page_icon="📚", layout="wide")

# ─────────────────────────────────────────
# 預設值
# ─────────────────────────────────────────
DEFAULT_BASE  = "physical therapy"
DEFAULT_EXCL  = "animal, rat, mice, cadaver, pediatric"
CURRENT_YEAR  = datetime.datetime.now().year

GROUP_A = [
    "neck pain",
    "shoulder pain",
    "low back pain",
    "knee pain",
    "plantar fasciitis",
    "adhesive capsulitis",
    "shoulder impingement",
    "myofascial pain syndrome",
    "ankle sprain",
    "osteoarthritis",
]

GROUP_B = [
    "therapy exercises",
    "manual therapy",
    "guidelines",
    "systematic reviews",
    "mechanism",
]

# ─────────────────────────────────────────
# Session state 初始化
# ─────────────────────────────────────────
if "sel_a" not in st.session_state:
    st.session_state.sel_a = set()
if "sel_b" not in st.session_state:
    st.session_state.sel_b = set()

# ─────────────────────────────────────────
# URL 組合函式
# ─────────────────────────────────────────
def build_url(topic: str, base: str, excl: list, y1: int, y2: int) -> str:
    parts = [f'"{topic}"']
    if base.strip():
        parts.append(base.strip())
    for ex in excl:
        if ex.strip():
            parts.append(f"-{ex.strip()}")
    params = {"q": " ".join(parts), "as_ylo": y1, "as_yhi": y2}
    return "https://scholar.google.com/scholar?" + urlencode(params)

def build_combined_url(topics_a: list, topics_b: list, base: str,
                       excl: list, y1: int, y2: int) -> str:
    parts = []
    if topics_a:
        a_str = " OR ".join(f'"{t}"' for t in topics_a)
        parts.append(f"({a_str})")
    if topics_b:
        b_str = " OR ".join(f'"{t}"' for t in topics_b)
        parts.append(f"({b_str})")
    if base.strip():
        parts.append(base.strip())
    for ex in excl:
        if ex.strip():
            parts.append(f"-{ex.strip()}")
    params = {"q": " ".join(parts), "as_ylo": y1, "as_yhi": y2}
    return "https://scholar.google.com/scholar?" + urlencode(params)

# ─────────────────────────────────────────
# 側邊欄：全域設定
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 全域設定")
    base = st.text_input("📌 固定包含詞", value=DEFAULT_BASE)
    excl_raw = st.text_area("🚫 排除關鍵字（逗號分隔）", value=DEFAULT_EXCL, height=80)
    excl = [k.strip() for k in excl_raw.split(",") if k.strip()]
    c1, c2 = st.columns(2)
    y1 = c1.number_input("起始年份", min_value=2000, max_value=CURRENT_YEAR, value=2015)
    y2 = c2.number_input("結束年份", min_value=2000, max_value=CURRENT_YEAR, value=CURRENT_YEAR)

    st.divider()
    st.info(
        "**使用方式**\n\n"
        "1. 在搜尋框輸入主題，或\n"
        "2. 點 A 組選主題、B 組選文獻類型\n"
        "3. 按「Google Scholar」開新分頁"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站")

# ── 自訂搜尋框 ──
st.subheader("🔍 自訂搜尋")
custom = st.text_input(
    "輸入主題關鍵字",
    placeholder="e.g. rotator cuff, disc herniation...",
    label_visibility="collapsed"
)

if custom.strip():
    url_custom = build_url(custom.strip(), base, excl, y1, y2)
    preview = f'"{custom.strip()}" {base} ' + " ".join(f"-{ex}" for ex in excl)
    st.caption(f"搜尋詞：`{preview}`")
    st.link_button("🔗 在 Google Scholar 開啟", url=url_custom, use_container_width=True)

st.divider()

# ── A 組：主題按鈕 ──
st.subheader("A 組：選擇主題")
st.caption("點擊選取（可多選），或直接點右側「單獨搜尋」")

for topic in GROUP_A:
    col_check, col_label, col_btn = st.columns([0.08, 0.72, 0.20])

    # 選取 checkbox
    checked = col_check.checkbox(
        "　", value=(topic in st.session_state.sel_a),
        key=f"a_{topic}", label_visibility="collapsed"
    )
    if checked:
        st.session_state.sel_a.add(topic)
    else:
        st.session_state.sel_a.discard(topic)

    col_label.markdown(f"**{topic}**")

    # 單獨搜尋按鈕
    url_single = build_url(topic, base, excl, y1, y2)
    col_btn.link_button("單獨搜尋", url=url_single, use_container_width=True)

st.divider()

# ── B 組：文獻類型按鈕 ──
st.subheader("B 組：文獻類型")
st.caption("點擊選取（可多選）")

b_cols = st.columns(len(GROUP_B))
for i, btype in enumerate(GROUP_B):
    checked_b = b_cols[i].checkbox(
        btype,
        value=(btype in st.session_state.sel_b),
        key=f"b_{btype}"
    )
    if checked_b:
        st.session_state.sel_b.add(btype)
    else:
        st.session_state.sel_b.discard(btype)

st.divider()

# ── 組合搜尋 ──
sel_a_list = sorted(st.session_state.sel_a)
sel_b_list = sorted(st.session_state.sel_b)

if sel_a_list or sel_b_list:
    st.subheader("🔀 組合搜尋")

    # 顯示已選項目
    if sel_a_list:
        st.markdown("**A 組：** " + " ｜ ".join(f"`{t}`" for t in sel_a_list))
    if sel_b_list:
        st.markdown("**B 組：** " + " ｜ ".join(f"`{t}`" for t in sel_b_list))

    url_combined = build_combined_url(sel_a_list, sel_b_list, base, excl, y1, y2)

    # 搜尋詞預覽
    preview_parts = []
    if sel_a_list:
        preview_parts.append("(" + " OR ".join(f'"{t}"' for t in sel_a_list) + ")")
    if sel_b_list:
        preview_parts.append("(" + " OR ".join(f'"{t}"' for t in sel_b_list) + ")")
    if base:
        preview_parts.append(base)
    st.caption("搜尋詞預覽：`" + " ".join(preview_parts) + "`")

    col_open, col_clear = st.columns([3, 1])
    col_open.link_button(
        f"🔗 Google Scholar 組合搜尋（A:{len(sel_a_list)} B:{len(sel_b_list)}）",
        url=url_combined, use_container_width=True
    )
    if col_clear.button("🗑️ 清除選取", use_container_width=True):
        st.session_state.sel_a = set()
        st.session_state.sel_b = set()
        st.rerun()
else:
    st.caption("☝️ 勾選 A 組或 B 組的項目後，這裡會出現組合搜尋按鈕")

st.divider()
st.caption("📚 PT 文章發想站　｜　搜尋結果來自 Google Scholar　｜　完全免費，不需要 API")

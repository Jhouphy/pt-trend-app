import streamlit as st
from urllib.parse import urlencode

st.set_page_config(page_title="PT 社群雷達", page_icon="💬", layout="wide")

# ─────────────────────────────────────────
# 預設設定
# ─────────────────────────────────────────
DEFAULT_SUBREDDITS = [
    "physicaltherapy", "backpain", "fitness", "AskDocs"
]

GROUP_A = [
    "neck pain", "shoulder pain", "low back pain", "knee pain",
    "plantar fasciitis", "adhesive capsulitis", "shoulder impingement",
    "myofascial pain syndrome", "ankle sprain", "osteoarthritis",
]

GROUP_B = [
    "exercise", "treatment", "diagnosis", "recovery", "stretching",
]

# ─────────────────────────────────────────
# Session State
# ─────────────────────────────────────────
if "sel_a" not in st.session_state:
    st.session_state.sel_a = set()
if "sel_b" not in st.session_state:
    st.session_state.sel_b = set()

# ─────────────────────────────────────────
# URL 組合函式
# ─────────────────────────────────────────
def reddit_search_url(query: str, subreddits: list, sort: str = "relevance") -> str:
    """組合 Reddit 搜尋網址，限定在指定 subreddit"""
    sr = "+".join(subreddits)
    return f"https://www.reddit.com/r/{sr}/search/?" + urlencode({
        "q":           query,
        "sort":        sort,
        "restrict_sr": 1,
        "t":           "year",
    })

def reddit_hot_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/hot/"

def reddit_new_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/new/"

def build_query(custom: str, sel_a: list, sel_b: list) -> str:
    parts = []
    if custom.strip():
        parts.append(custom.strip())
    if sel_a:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_a) + ")")
    if sel_b:
        parts.append("(" + " OR ".join(f'"{t}"' for t in sel_b) + ")")
    return " ".join(parts)

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

    selected_subs = st.multiselect(
        "監測社群",
        options=DEFAULT_SUBREDDITS,
        default=DEFAULT_SUBREDDITS,
        format_func=lambda x: f"r/{x}"
    )

    new_sub = st.text_input("➕ 新增社群", placeholder="e.g. running")
    if st.button("新增", use_container_width=True) and new_sub.strip():
        sub = new_sub.strip().lstrip("r/")
        if sub not in DEFAULT_SUBREDDITS:
            DEFAULT_SUBREDDITS.append(sub)
            st.rerun()

    st.divider()

    sort_mode = st.selectbox(
        "搜尋排序",
        options=["relevance", "top", "new", "hot"],
        format_func=lambda x: {
            "relevance": "🎯 相關度",
            "top":       "⬆️ 高分",
            "new":       "🆕 最新",
            "hot":       "🔥 熱門",
        }[x]
    )

    st.divider()

    if st.button("🗑️ 清除所有選取", use_container_width=True):
        st.session_state.sel_a = set()
        st.session_state.sel_b = set()
        st.rerun()

    st.divider()
    st.info(
        "**使用方式**\n\n"
        "① 選取 A/B 組標籤或輸入自訂詞\n"
        "② 點搜尋按鈕，Reddit 在新分頁開啟\n\n"
        "搜尋結果直接在 Reddit 網站呈現，\n"
        "完全不會被封鎖。"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
st.title("💬 PT 社群雷達")
st.caption("快速產生 Reddit 搜尋連結，瀏覽民眾討論的身體健康問題")

# ── 各社群快速入口 ──
st.subheader("📌 社群快速入口")
st.caption("直接瀏覽各社群的熱門或最新討論")

cols = st.columns(len(selected_subs))
for i, sub in enumerate(selected_subs):
    with cols[i]:
        st.markdown(f"**r/{sub}**")
        st.link_button("🔥 熱門", url=reddit_hot_url(sub), use_container_width=True)
        st.link_button("🆕 最新", url=reddit_new_url(sub), use_container_width=True)

st.divider()

# ── 自訂搜尋框 ──
st.subheader("🔍 關鍵字搜尋")
custom = st.text_input(
    "自訂關鍵字（選填，可搭配下方 A/B 組）",
    placeholder="e.g. herniated disc, dry needling..."
)

st.divider()

# ── A 組標籤 ──
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

# ── B 組標籤 ──
st.markdown("**B 組：討論類型**　`點擊選取 / 再點取消`")
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
    st.markdown("**搜尋詞：**")
    st.code(query)

    # 各社群分別搜尋 + 全部合併搜尋
    st.markdown("**分別搜尋各社群：**")
    sub_cols = st.columns(len(selected_subs))
    for i, sub in enumerate(selected_subs):
        url = reddit_search_url(query, [sub], sort_mode)
        sub_cols[i].link_button(
            f"r/{sub}",
            url=url,
            use_container_width=True
        )

    st.markdown("**或全部社群合併搜尋：**")
    st.link_button(
        f"🔍 Reddit 合併搜尋（{', '.join(f'r/{s}' for s in selected_subs)}）",
        url=reddit_search_url(query, selected_subs, sort_mode),
        use_container_width=True
    )
else:
    st.info("☝️ 輸入自訂關鍵字，或點選上方 A/B 組的標籤，搜尋按鈕會出現在這裡。")

st.divider()
st.caption(
    "💬 PT 社群雷達　｜　"
    "搜尋結果來自 Reddit　｜　"
    "完全免費，不需要 API Key"
)

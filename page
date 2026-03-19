import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timezone

st.set_page_config(page_title="PT 社群雷達", page_icon="💬", layout="wide")

# ─────────────────────────────────────────
# 預設設定
# ─────────────────────────────────────────
DEFAULT_SUBREDDITS = ["physicaltherapy", "backpain", "fitness", "AskDocs"]

DEFAULT_KEYWORDS = [
    "neck pain", "shoulder pain", "low back pain", "knee pain",
    "plantar fasciitis", "adhesive capsulitis", "shoulder impingement",
    "myofascial pain syndrome", "ankle sprain", "osteoarthritis",
    "physical therapy", "physiotherapy", "rehabilitation",
]

# Reddit 公開 JSON 不需要 API Key
# User-Agent 是必要的，否則會被擋
HEADERS = {"User-Agent": "Mozilla/5.0 PT_Research_App/1.0"}

# ─────────────────────────────────────────
# Session State
# ─────────────────────────────────────────
if "hot_df"   not in st.session_state:
    st.session_state.hot_df = None
if "sel_kw"   not in st.session_state:
    st.session_state.sel_kw = set()

# ─────────────────────────────────────────
# Reddit 公開 JSON 查詢函式
# ─────────────────────────────────────────
def fetch_subreddit(subreddit: str, sort: str = "hot", limit: int = 25) -> list:
    """
    使用 Reddit 公開 JSON 端點抓取文章，完全不需要 API Key。
    網址格式：https://www.reddit.com/r/{subreddit}/{sort}.json
    """
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    try:
        time.sleep(1)  # 禮貌性延遲，避免被限流
        r = requests.get(url, headers=HEADERS,
                         params={"limit": limit}, timeout=15)
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        return [p["data"] for p in posts]
    except Exception as e:
        st.warning(f"r/{subreddit} 載入失敗：{e}")
        return []

def search_subreddit(subreddit: str, query: str,
                     sort: str = "relevance", limit: int = 25) -> list:
    """
    使用 Reddit 公開搜尋 JSON 端點。
    網址格式：https://www.reddit.com/r/{subreddit}/search.json
    """
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    try:
        time.sleep(1)
        r = requests.get(url, headers=HEADERS, params={
            "q":           query,
            "sort":        sort,
            "limit":       limit,
            "restrict_sr": True,  # 只搜此 subreddit
            "t":           "year",
        }, timeout=15)
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        return [p["data"] for p in posts]
    except Exception as e:
        st.warning(f"r/{subreddit} 搜尋失敗：{e}")
        return []

def posts_to_df(posts: list) -> pd.DataFrame:
    rows = []
    for p in posts:
        created_utc = p.get("created_utc", 0)
        created_dt  = datetime.fromtimestamp(created_utc, tz=timezone.utc)
        time_str    = created_dt.strftime("%Y-%m-%d %H:%M")
        rows.append({
            "標題":     p.get("title", ""),
            "社群":     f"r/{p.get('subreddit', '')}",
            "熱度":     p.get("score", 0),
            "留言數":   p.get("num_comments", 0),
            "發文時間": time_str,
            "連結":     f"https://reddit.com{p.get('permalink', '')}",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("熱度", ascending=False).reset_index(drop=True)
        df.index += 1
    return df

# ─────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")
    st.success("✅ 不需要 API Key！\n使用 Reddit 公開資料")

    st.divider()

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
        "排序方式",
        options=["hot", "top", "new"],
        format_func=lambda x: {
            "hot": "🔥 熱門", "top": "⬆️ 高分", "new": "🆕 最新"
        }[x]
    )
    limit = st.selectbox("每個社群顯示幾筆", [10, 25, 50], index=1)

    st.divider()
    st.info(
        "📌 **資料來源**\n\n"
        "Reddit 公開 JSON 端點，\n"
        "完全免費，不需要帳號或 API Key。\n\n"
        "每次請求間隔 1 秒，\n避免被 Reddit 限流。"
    )

# ─────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────
st.title("💬 PT 社群雷達")
st.caption("監測 Reddit 上民眾討論的身體健康問題，找到衛教文章的靈感方向")

tab1, tab2 = st.tabs(["🔥 熱門瀏覽", "🔍 關鍵字搜尋"])

# ── Tab 1：熱門瀏覽 ──
with tab1:
    st.subheader("各社群近期熱門討論")
    st.caption(
        f"社群：{', '.join(f'r/{s}' for s in selected_subs)}"
        f"　｜　排序：{sort_mode}　｜　每社群 {limit} 筆"
    )

    if st.button("📥 載入熱門文章", type="primary",
                 use_container_width=True, key="load_hot"):
        all_posts = []
        progress  = st.progress(0)
        for i, sub in enumerate(selected_subs):
            progress.progress(
                (i + 1) / len(selected_subs),
                text=f"載入 r/{sub}...（{i+1}/{len(selected_subs)}）"
            )
            posts = fetch_subreddit(sub, sort_mode, limit)
            all_posts.extend(posts)
        progress.empty()

        st.session_state.hot_df = posts_to_df(all_posts)

    if st.session_state.hot_df is not None:
        df = st.session_state.hot_df
        st.success(f"共載入 {len(df)} 篇文章")

        # 社群篩選
        filter_sub = st.multiselect(
            "篩選社群",
            options=df["社群"].unique().tolist(),
            default=df["社群"].unique().tolist(),
            key="filter_hot"
        )
        df_show = df[df["社群"].isin(filter_sub)]

        # 顯示結果
        for idx, row in df_show.iterrows():
            with st.expander(
                f"#{idx}　{row['標題']}"
                f"　｜ {row['社群']} ｜ ⬆️{row['熱度']} 💬{row['留言數']}"
            ):
                st.markdown(f"**社群：** {row['社群']}")
                st.markdown(
                    f"**熱度：** ⬆️ {row['熱度']}"
                    f"　｜　**留言：** 💬 {row['留言數']}"
                )
                st.markdown(f"**發文時間：** {row['發文時間']}")
                st.markdown(f"[🔗 前往 Reddit 原文]({row['連結']})")

        st.download_button(
            "⬇️ 下載熱門文章清單 (CSV)",
            df_show.to_csv(index=True, encoding="utf-8-sig"),
            file_name=f"reddit_hot_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ── Tab 2：關鍵字搜尋 ──
with tab2:
    st.subheader("搜尋特定關鍵字的討論")

    # 快速關鍵字標籤
    st.markdown("**快速選取關鍵字：**")
    kw_cols = st.columns(5)
    for i, kw in enumerate(DEFAULT_KEYWORDS):
        is_sel = kw in st.session_state.sel_kw
        label  = f"✅ {kw}" if is_sel else kw
        if kw_cols[i % 5].button(label, key=f"kw_{kw}", use_container_width=True):
            if kw in st.session_state.sel_kw:
                st.session_state.sel_kw.discard(kw)
            else:
                st.session_state.sel_kw.add(kw)
            st.rerun()

    st.divider()

    custom_kw = st.text_input(
        "或輸入自訂關鍵字",
        placeholder="e.g. herniated disc, sciatica..."
    )

    sel_kw_list = sorted(st.session_state.sel_kw)
    if custom_kw.strip() and sel_kw_list:
        final_query = custom_kw.strip() + " " + " OR ".join(f'"{k}"' for k in sel_kw_list)
    elif custom_kw.strip():
        final_query = custom_kw.strip()
    elif sel_kw_list:
        final_query = " OR ".join(f'"{k}"' for k in sel_kw_list)
    else:
        final_query = ""

    if final_query:
        st.info(f"**搜尋詞：** `{final_query}`")

        sort_search = st.selectbox(
            "搜尋排序",
            options=["relevance", "top", "new"],
            format_func=lambda x: {
                "relevance": "🎯 相關度", "top": "⬆️ 高分", "new": "🆕 最新"
            }[x],
            key="sort_search"
        )

        if st.button("🔍 搜尋", type="primary",
                     use_container_width=True, key="do_search"):
            all_search = []
            progress   = st.progress(0)
            for i, sub in enumerate(selected_subs):
                progress.progress(
                    (i + 1) / len(selected_subs),
                    text=f"搜尋 r/{sub}...（{i+1}/{len(selected_subs)}）"
                )
                posts = search_subreddit(sub, final_query, sort_search, limit)
                all_search.extend(posts)
            progress.empty()

            df_search = posts_to_df(all_search)

            if df_search.empty:
                st.warning("查無結果，請嘗試調整關鍵字。")
            else:
                st.success(f"找到 {len(df_search)} 篇討論")

                for idx, row in df_search.iterrows():
                    with st.expander(
                        f"#{idx}　{row['標題']}"
                        f"　｜ {row['社群']} ｜ ⬆️{row['熱度']} 💬{row['留言數']}"
                    ):
                        st.markdown(f"**社群：** {row['社群']}")
                        st.markdown(
                            f"**熱度：** ⬆️ {row['熱度']}"
                            f"　｜　**留言：** 💬 {row['留言數']}"
                        )
                        st.markdown(f"**發文時間：** {row['發文時間']}")
                        st.markdown(f"[🔗 前往 Reddit 原文]({row['連結']})")

                st.download_button(
                    "⬇️ 下載搜尋結果 (CSV)",
                    df_search.to_csv(index=True, encoding="utf-8-sig"),
                    file_name=f"reddit_search_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
    else:
        st.info("☝️ 點選上方關鍵字標籤，或輸入自訂關鍵字開始搜尋。")

st.divider()
st.caption(
    "💬 PT 社群雷達　｜　"
    "資料來源：Reddit 公開 JSON　｜　"
    "完全免費，不需要 API Key"
)

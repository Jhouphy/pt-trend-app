import streamlit as st
from pytrends.request import TrendReq
import pandas as pd
import plotly.express as px
import time
import os
import json
from datetime import datetime, timedelta

# ─────────────────────────────────────────
# 頁面設定
# ─────────────────────────────────────────
st.set_page_config(
    page_title="PT 衛教情報站",
    page_icon="🩺",
    layout="wide"
)

# ─────────────────────────────────────────
# 快取設定（6小時有效）
# ─────────────────────────────────────────
CACHE_DIR = "cache"
CACHE_HOURS = 6

os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(key: str) -> str:
    safe_key = key.replace(" ", "_").replace(",", "-").replace("/", "-")
    return os.path.join(CACHE_DIR, f"{safe_key}.json")

def load_cache(key: str):
    path = get_cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        saved_at = datetime.fromisoformat(cached["timestamp"])
        if datetime.now() - saved_at < timedelta(hours=CACHE_HOURS):
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
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"（{minutes} 分鐘前更新）"
        else:
            return f"（{minutes // 60} 小時前更新）"
    except Exception:
        return ""

# ─────────────────────────────────────────
# pytrends 初始化（模擬真實瀏覽器降低被封機率）
# ─────────────────────────────────────────
@st.cache_resource
def init_pytrends():
    return TrendReq(
        hl='zh-TW',
        tz=-480,
        timeout=(10, 25),
        retries=2,
        backoff_factor=0.5,
        requests_args={
            'headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            }
        }
    )

pytrends = init_pytrends()

# ─────────────────────────────────────────
# 重試包裝器（指數退避，最多重試 3 次）
# ─────────────────────────────────────────
def with_retry(fn, max_retries=3, base_wait=10):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            is_429 = "429" in err_str or "Too Many Requests" in err_str
            is_last = attempt == max_retries - 1

            if is_last:
                raise e

            wait = base_wait * (2 ** attempt)  # 10 → 20 → 40 秒
            if is_429:
                st.warning(
                    f"⚠️ Google 暫時限流（第 {attempt+1} 次），"
                    f"等待 {wait} 秒後自動重試..."
                )
            else:
                st.warning(f"⚠️ 連線問題，等待 {wait} 秒後重試...")
            time.sleep(wait)
    return None

# ─────────────────────────────────────────
# 查詢函式
# ─────────────────────────────────────────
def fetch_trends(kw_list, timeframe, geo):
    cache_key = f"trends_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        return pd.DataFrame(cached), True

    def _fetch():
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(5)
        return pytrends.interest_over_time()

    try:
        df = with_retry(_fetch)
        if df is not None and not df.empty:
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            save_cache(cache_key, df.reset_index().to_dict(orient="list"))
            return df, False
        return pd.DataFrame(), False
    except Exception as e:
        st.error(f"❌ 查詢失敗（已重試 3 次）：{e}\n\n請等待 5~10 分鐘後再試。")
        return pd.DataFrame(), False

def fetch_related(kw_list, timeframe, geo):
    cache_key = f"related_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        return cached, True

    def _fetch():
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(5)
        return pytrends.related_queries()

    try:
        related = with_retry(_fetch)
        if not related:
            return {}, False
        serializable = {}
        for kw in kw_list:
            serializable[kw] = {}
            for kind in ["rising", "top"]:
                df = related.get(kw, {}).get(kind)
                if df is not None and not df.empty:
                    serializable[kw][kind] = df.to_dict(orient="list")
                else:
                    serializable[kw][kind] = None
        save_cache(cache_key, serializable)
        return serializable, False
    except Exception as e:
        st.error(f"❌ 查詢相關詞失敗：{e}")
        return {}, False

def fetch_regional(kw_list, timeframe, geo):
    cache_key = f"region_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        df = pd.DataFrame(cached)
        if "geoName" in df.columns:
            df = df.set_index("geoName")
        return df, True

    def _fetch():
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(5)
        return pytrends.interest_by_region(resolution='CITY', inc_low_vol=True, inc_geo_code=False)

    try:
        df = with_retry(_fetch)
        if df is not None and not df.empty:
            save_cache(cache_key, df.reset_index().to_dict(orient="list"))
            return df, False
        return pd.DataFrame(), False
    except Exception as e:
        st.error(f"❌ 查詢地區數據失敗：{e}")
        return pd.DataFrame(), False

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.title("🩺 PT 衛教情報站")
st.caption("掌握近期台灣民眾最關心的身體問題，找到下一篇文章的靈感")

with st.sidebar:
    st.header("⚙️ 搜尋設定")

    keyword_input = st.text_area(
        "輸入關鍵字（逗號分隔，最多 5 個）",
        value="腰痛, 網球肘, 骨盆前傾",
        height=120
    )

    timeframe = st.selectbox(
        "時間範圍",
        options=["today 1-m", "today 3-m", "today 12-m"],
        format_func=lambda x: {
            "today 1-m": "近 1 個月",
            "today 3-m": "近 3 個月",
            "today 12-m": "近 12 個月"
        }[x]
    )

    geo = st.selectbox(
        "地區",
        options=["TW", "HK", "SG", ""],
        format_func=lambda x: {
            "TW": "🇹🇼 台灣",
            "HK": "🇭🇰 香港",
            "SG": "🇸🇬 新加坡",
            "": "🌏 全球"
        }[x]
    )

    st.divider()
    st.info(
        f"⏱️ 快取有效：{CACHE_HOURS} 小時\n\n"
        "快取期間不會重新打 API，\n完全不怕被限流。"
    )

    force_refresh = st.button("🔄 強制重新抓取（清除快取）")

    st.divider()
    st.markdown(
        "**💡 遇到 429 怎麼辦？**\n\n"
        "App 會自動等待後重試。\n"
        "若仍失敗，請等 **5~10 分鐘** 後再試。"
    )

# ── 解析關鍵字 ──
raw = keyword_input.replace("\n", ",")
kw_list = [x.strip() for x in raw.split(",") if x.strip()][:5]

if len(kw_list) == 0:
    st.warning("請輸入至少一個關鍵字")
    st.stop()

if force_refresh:
    for f in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, f))
        except Exception:
            pass
    st.success("✅ 快取已清除，將重新向 Google 抓取最新資料。")

st.markdown(f"**目前查詢：** {' ｜ '.join([f'`{k}`' for k in kw_list])}")
st.divider()

# ─────────────────────────────────────────
# 分頁
# ─────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📈 熱度走勢", "🚀 飆升關鍵字", "📍 地區分布"])

with tab1:
    with st.spinner("載入趨勢數據（新查詢可能需要 10~40 秒）..."):
        df_trends, from_cache = fetch_trends(kw_list, timeframe, geo)

    if not df_trends.empty:
        cache_key = f"trends_{'-'.join(kw_list)}_{timeframe}_{geo}"
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {cache_age_str(cache_key)}")

        fig = px.line(
            df_trends, y=kw_list,
            labels={"value": "搜尋熱度（0-100）", "date": "日期", "variable": "關鍵字"},
            title="關鍵字搜尋熱度走勢",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig.update_layout(hovermode="x unified", legend_title_text="關鍵字")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🏆 平均熱度排行")
        avg = df_trends[kw_list].mean().sort_values(ascending=False).reset_index()
        avg.columns = ["關鍵字", "平均熱度"]
        avg["平均熱度"] = avg["平均熱度"].round(1)

        fig2 = px.bar(
            avg, x="關鍵字", y="平均熱度",
            color="關鍵字", text="平均熱度",
            color_discrete_sequence=px.colors.qualitative.Set2,
            title="各關鍵字平均搜尋熱度（數字越高越值得優先寫）"
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

        top_kw = avg.iloc[0]["關鍵字"]
        st.success(f"💡 **寫作建議**：「{top_kw}」目前熱度最高，適合優先發文！")
    else:
        st.warning("⏳ 若剛遇到限流錯誤，請等 5~10 分鐘後重新整理頁面。")

with tab2:
    with st.spinner("載入相關關鍵字..."):
        related_data, from_cache = fetch_related(kw_list, timeframe, geo)

    if related_data:
        cache_key = f"related_{'-'.join(kw_list)}_{timeframe}_{geo}"
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {cache_age_str(cache_key)}")

        for kw in kw_list:
            st.subheader(f"🔍 「{kw}」的相關搜尋")
            col_rising, col_top = st.columns(2)

            with col_rising:
                st.markdown("**🚀 飆升詞（近期爆紅）**")
                rising = related_data.get(kw, {}).get("rising")
                if rising and rising.get("query"):
                    df_r = pd.DataFrame(rising)
                    df_r.columns = ["關鍵字", "成長幅度"]
                    st.dataframe(df_r, hide_index=True, use_container_width=True)
                else:
                    st.info("目前無飆升詞數據")

            with col_top:
                st.markdown("**📊 熱門詞（長期熱搜）**")
                top = related_data.get(kw, {}).get("top")
                if top and top.get("query"):
                    df_t = pd.DataFrame(top)
                    df_t.columns = ["關鍵字", "相對熱度"]
                    st.dataframe(df_t, hide_index=True, use_container_width=True)
                else:
                    st.info("目前無熱門詞數據")

            st.divider()

        st.info("💡 **使用技巧**：飆升詞適合作為文章**標題關鍵字**，熱門詞適合放在**文章內文**中自然帶入。")

with tab3:
    with st.spinner("載入地區數據..."):
        df_region, from_cache = fetch_regional(kw_list, timeframe, geo)

    if not df_region.empty:
        cache_key = f"region_{'-'.join(kw_list)}_{timeframe}_{geo}"
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {cache_age_str(cache_key)}")

        available_kw = [k for k in kw_list if k in df_region.columns]
        if available_kw:
            df_filtered = df_region[available_kw]
            df_filtered = df_filtered[df_filtered.sum(axis=1) > 0]

            if not df_filtered.empty:
                fig3 = px.bar(
                    df_filtered.reset_index(),
                    x="geoName", y=available_kw,
                    barmode="group",
                    title="各地區搜尋熱度分布",
                    labels={"geoName": "城市", "value": "熱度", "variable": "關鍵字"},
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig3.update_layout(xaxis_tickangle=-30)
                st.plotly_chart(fig3, use_container_width=True)
                st.info("💡 熱度集中的城市代表你的潛在核心讀者在那裡，可作為社群發文的地區鎖定參考。")
            else:
                st.warning("地區數據不足，可嘗試縮短時間範圍或更換關鍵字。")
    else:
        st.warning("⏳ 若剛遇到限流錯誤，請等 5~10 分鐘後重新整理頁面。")

st.divider()
st.caption("🩺 PT 衛教情報站 ｜ 數據來源：Google Trends ｜ 快取機制：每 6 小時更新一次")

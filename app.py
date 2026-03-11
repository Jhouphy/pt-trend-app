import streamlit as st
from pytrends.request import TrendReq
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
CACHE_HOURS = 6  # 快取有效時間（小時）

os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(key: str) -> str:
    safe_key = key.replace(" ", "_").replace(",", "-").replace("/", "-")
    return os.path.join(CACHE_DIR, f"{safe_key}.json")

def load_cache(key: str):
    """讀取快取，若過期或不存在則回傳 None"""
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
    """儲存快取"""
    path = get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "data": data}, f, ensure_ascii=False)
    except Exception as e:
        st.warning(f"快取儲存失敗：{e}")

def cache_age_str(key: str) -> str:
    """回傳快取的更新時間字串"""
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
# pytrends 初始化
# ─────────────────────────────────────────
@st.cache_resource
def init_pytrends():
    return TrendReq(hl='zh-TW', tz=-480)

pytrends = init_pytrends()

# ─────────────────────────────────────────
# Google Trends 查詢函式（含防封鎖保護）
# ─────────────────────────────────────────
def fetch_trends(kw_list, timeframe, geo):
    cache_key = f"trends_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        return pd.DataFrame(cached), True  # True = 來自快取

    try:
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(2)  # 防止 Google 限流
        df = pytrends.interest_over_time()
        if not df.empty and "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        save_cache(cache_key, df.reset_index().to_dict(orient="list"))
        return df, False
    except Exception as e:
        st.error(f"查詢趨勢時發生錯誤：{e}")
        return pd.DataFrame(), False

def fetch_related(kw_list, timeframe, geo):
    cache_key = f"related_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        return cached, True

    try:
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(2)
        related = pytrends.related_queries()
        # 轉成可序列化格式
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
        st.error(f"查詢相關詞時發生錯誤：{e}")
        return {}, False

def fetch_regional(kw_list, timeframe, geo):
    cache_key = f"region_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key)
    if cached:
        df = pd.DataFrame(cached)
        df.index = df.pop("geoName") if "geoName" in df.columns else df.index
        return df, True

    try:
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        time.sleep(2)
        df = pytrends.interest_by_region(resolution='CITY', inc_low_vol=True, inc_geo_code=False)
        to_save = df.reset_index().to_dict(orient="list")
        save_cache(cache_key, to_save)
        return df, False
    except Exception as e:
        st.error(f"查詢地區數據時發生錯誤：{e}")
        return pd.DataFrame(), False

# ─────────────────────────────────────────
# UI 主體
# ─────────────────────────────────────────
st.title("🩺 PT 衛教情報站")
st.caption("掌握近期台灣民眾最關心的身體問題，找到下一篇文章的靈感")

# ── 側邊欄設定 ──
with st.sidebar:
    st.header("⚙️ 搜尋設定")

    keyword_input = st.text_area(
        "輸入關鍵字（每行或逗號分隔，最多 5 個）",
        value="腰痛, 網球肘, 骨盆前傾",
        height=120
    )

    timeframe = st.selectbox(
        "時間範圍",
        options=["today 1-m", "today 3-m", "today 12-m"],
        format_func=lambda x: {"today 1-m": "近 1 個月", "today 3-m": "近 3 個月", "today 12-m": "近 12 個月"}[x]
    )

    geo = st.selectbox(
        "地區",
        options=["TW", "HK", "SG", ""],
        format_func=lambda x: {"TW": "🇹🇼 台灣", "HK": "🇭🇰 香港", "SG": "🇸🇬 新加坡", "": "🌏 全球"}[x]
    )

    st.divider()
    st.info(f"⏱️ 快取有效時間：{CACHE_HOURS} 小時\n\n資料會在快取到期後自動重新抓取，不需要手動更新。")

    force_refresh = st.button("🔄 強制重新抓取（清除快取）")

# ── 解析關鍵字 ──
raw = keyword_input.replace("\n", ",")
kw_list = [x.strip() for x in raw.split(",") if x.strip()][:5]

if len(kw_list) == 0:
    st.warning("請輸入至少一個關鍵字")
    st.stop()

# 強制清除快取
if force_refresh:
    for f in os.listdir(CACHE_DIR):
        os.remove(os.path.join(CACHE_DIR, f))
    st.success("快取已清除，下次查詢將重新抓取最新資料。")

st.markdown(f"**目前查詢關鍵字：** {' ｜ '.join([f'`{k}`' for k in kw_list])}")
st.divider()

# ─────────────────────────────────────────
# 分頁
# ─────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📈 熱度走勢", "🚀 飆升關鍵字", "📍 地區分布"])

# ── Tab 1：熱度走勢 ──
with tab1:
    with st.spinner("載入趨勢數據..."):
        df_trends, from_cache = fetch_trends(kw_list, timeframe, geo)

    if not df_trends.empty:
        age_str = cache_age_str(f"trends_{'-'.join(kw_list)}_{timeframe}_{geo}")
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {age_str}")

        # 折線圖
        fig = px.line(
            df_trends,
            y=kw_list,
            labels={"value": "搜尋熱度（0-100）", "date": "日期", "variable": "關鍵字"},
            title="關鍵字搜尋熱度走勢",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig.update_layout(hovermode="x unified", legend_title_text="關鍵字")
        st.plotly_chart(fig, use_container_width=True)

        # 平均熱度排行
        st.subheader("🏆 平均熱度排行")
        avg = df_trends[kw_list].mean().sort_values(ascending=False).reset_index()
        avg.columns = ["關鍵字", "平均熱度"]
        avg["平均熱度"] = avg["平均熱度"].round(1)

        fig2 = px.bar(
            avg,
            x="關鍵字",
            y="平均熱度",
            color="關鍵字",
            text="平均熱度",
            color_discrete_sequence=px.colors.qualitative.Set2,
            title="各關鍵字平均搜尋熱度（數字越高越值得優先寫）"
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

        # 建議
        top_kw = avg.iloc[0]["關鍵字"]
        st.success(f"💡 **寫作建議**：「{top_kw}」目前熱度最高，適合優先發文！")
    else:
        st.error("查無趨勢數據，請嘗試更換關鍵字或時間範圍。")

# ── Tab 2：飆升關鍵字 ──
with tab2:
    with st.spinner("載入相關關鍵字..."):
        related_data, from_cache = fetch_related(kw_list, timeframe, geo)

    if related_data:
        age_str = cache_age_str(f"related_{'-'.join(kw_list)}_{timeframe}_{geo}")
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {age_str}")

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
    else:
        st.error("查無相關詞數據。")

# ── Tab 3：地區分布 ──
with tab3:
    with st.spinner("載入地區數據..."):
        df_region, from_cache = fetch_regional(kw_list, timeframe, geo)

    if not df_region.empty:
        age_str = cache_age_str(f"region_{'-'.join(kw_list)}_{timeframe}_{geo}")
        st.caption(f"{'📦 快取資料' if from_cache else '🔴 即時資料'} {age_str}")

        available_kw = [k for k in kw_list if k in df_region.columns]
        if available_kw:
            # 篩掉全 0 的城市
            df_filtered = df_region[available_kw]
            df_filtered = df_filtered[df_filtered.sum(axis=1) > 0]

            if not df_filtered.empty:
                fig3 = px.bar(
                    df_filtered.reset_index(),
                    x="geoName",
                    y=available_kw,
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
        st.warning("查無地區數據，可能是查詢地區範圍太廣或數據不足。")

# ─────────────────────────────────────────
# 頁尾
# ─────────────────────────────────────────
st.divider()
st.caption("🩺 PT 衛教情報站 ｜ 數據來源：Google Trends ｜ 快取機制：每 6 小時更新一次")

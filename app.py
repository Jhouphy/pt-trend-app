import streamlit as st
from pytrends.request import TrendReq
import pandas as pd
import plotly.express as px
import time
import random
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
# 快取設定
# 趨勢/飆升詞：24 小時（衛教話題一天內不會大變）
# 地區分布：72 小時（更穩定的數據，減少 API 呼叫）
# ─────────────────────────────────────────
CACHE_DIR = "cache"
CACHE_HOURS_TRENDS  = 24
CACHE_HOURS_RELATED = 24
CACHE_HOURS_REGION  = 72

os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(key: str) -> str:
    safe = key.replace(" ", "_").replace(",", "-").replace("/", "-")
    return os.path.join(CACHE_DIR, f"{safe}.json")

def load_cache(key: str, max_hours: int):
    path = get_cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        saved_at = datetime.fromisoformat(cached["timestamp"])
        if datetime.now() - saved_at < timedelta(hours=max_hours):
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
# 資料來源選擇（pytrends 或 SerpApi）
# ─────────────────────────────────────────
# 📌 切換方式：在 Streamlit Cloud 的 Secrets 加入以下設定
#    [serpapi]
#    key = "你的 SerpApi Key"
# 若沒有設定，自動使用 pytrends（免費但可能被擋）

def get_serpapi_key():
    try:
        return st.secrets["serpapi"]["key"]
    except Exception:
        return None

SERPAPI_KEY = get_serpapi_key()
USE_SERPAPI = SERPAPI_KEY is not None

# ─────────────────────────────────────────
# pytrends 初始化
# ─────────────────────────────────────────
@st.cache_resource
def init_pytrends():
    # 注意：移除 retries / backoff_factor 參數，
    # 避免新版 urllib3 的 method_whitelist 命名衝突。
    # 重試邏輯改由 with_retry() 自行處理。
    return TrendReq(
        hl='zh-TW',
        tz=-480,
        timeout=(10, 25),
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

# ─────────────────────────────────────────
# 隨機延遲（模擬人類行為）
# ─────────────────────────────────────────
def human_sleep(min_sec=3, max_sec=8):
    """每次 API 請求前隨機等待，讓請求模式看起來像真人"""
    wait = random.uniform(min_sec, max_sec)
    time.sleep(wait)

# ─────────────────────────────────────────
# 重試包裝器（指數退避）
# ─────────────────────────────────────────
def with_retry(fn, max_retries=3, base_wait=15):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            is_last = attempt == max_retries - 1
            if is_last:
                raise e
            wait = base_wait * (2 ** attempt)  # 15 → 30 → 60 秒
            if "429" in err_str:
                st.warning(f"⚠️ Google 限流（第 {attempt+1} 次），等待 {wait} 秒後自動重試...")
            else:
                st.warning(f"⚠️ 連線問題，等待 {wait} 秒後重試...")
            time.sleep(wait)
    return None

# ─────────────────────────────────────────
# ── SerpApi 查詢（付費穩定版）──
# ─────────────────────────────────────────
def serpapi_fetch_trends(kw_list, timeframe, geo):
    """使用 SerpApi 抓取趨勢數據（需要 API Key）"""
    try:
        import requests
        tf_map = {
            "today 1-m": "today 1-m",
            "today 3-m": "today 3-m",
            "today 12-m": "today 12-m"
        }
        rows = []
        for kw in kw_list:
            params = {
                "engine": "google_trends",
                "q": kw,
                "geo": geo if geo else "TW",
                "date": tf_map.get(timeframe, "today 1-m"),
                "api_key": SERPAPI_KEY
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            data = resp.json()
            timeline = data.get("interest_over_time", {}).get("timeline_data", [])
            for point in timeline:
                date_str = point.get("date", "")
                value = point.get("values", [{}])[0].get("extracted_value", 0)
                rows.append({"date": date_str, "keyword": kw, "value": value})

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df_pivot = df.pivot_table(index="date", columns="keyword", values="value").reset_index()
        df_pivot.columns.name = None
        return df_pivot
    except Exception as e:
        st.error(f"SerpApi 查詢失敗：{e}")
        return pd.DataFrame()

def serpapi_fetch_related(kw_list, timeframe, geo):
    """使用 SerpApi 抓取相關搜尋"""
    try:
        import requests
        result = {}
        for kw in kw_list:
            params = {
                "engine": "google_trends",
                "q": kw,
                "geo": geo if geo else "TW",
                "date": timeframe,
                "data_type": "RELATED_QUERIES",
                "api_key": SERPAPI_KEY
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            data = resp.json()
            related = data.get("related_queries", {})
            result[kw] = {
                "rising": {"query": [], "value": []},
                "top":    {"query": [], "value": []}
            }
            for item in related.get("rising", []):
                result[kw]["rising"]["query"].append(item.get("query", ""))
                result[kw]["rising"]["value"].append(item.get("value", ""))
            for item in related.get("top", []):
                result[kw]["top"]["query"].append(item.get("query", ""))
                result[kw]["top"]["value"].append(item.get("extracted_value", 0))
        return result
    except Exception as e:
        st.error(f"SerpApi 相關詞查詢失敗：{e}")
        return {}

# ─────────────────────────────────────────
# ── pytrends 查詢（免費版）──
# ─────────────────────────────────────────
def pytrends_fetch_trends(kw_list, timeframe, geo):
    pytrends = init_pytrends()

    def _fetch():
        human_sleep(3, 8)  # 隨機延遲 3~8 秒
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        return pytrends.interest_over_time()

    df = with_retry(_fetch)
    if df is not None and not df.empty:
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        return df
    return pd.DataFrame()

def pytrends_fetch_related(kw_list, timeframe, geo):
    pytrends = init_pytrends()

    def _fetch():
        human_sleep(3, 8)
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        return pytrends.related_queries()

    related = with_retry(_fetch)
    if not related:
        return {}
    result = {}
    for kw in kw_list:
        result[kw] = {}
        for kind in ["rising", "top"]:
            df = related.get(kw, {}).get(kind)
            result[kw][kind] = df.to_dict(orient="list") if (df is not None and not df.empty) else None
    return result

def pytrends_fetch_regional(kw_list, timeframe, geo):
    pytrends = init_pytrends()

    def _fetch():
        human_sleep(3, 8)
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo)
        return pytrends.interest_by_region(resolution='CITY', inc_low_vol=True, inc_geo_code=False)

    df = with_retry(_fetch)
    return df if (df is not None and not df.empty) else pd.DataFrame()

# ─────────────────────────────────────────
# 統一入口（自動選擇資料來源 + 快取）
# ─────────────────────────────────────────
def fetch_trends(kw_list, timeframe, geo):
    cache_key = f"trends_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key, CACHE_HOURS_TRENDS)
    if cached:
        return pd.DataFrame(cached), True

    try:
        if USE_SERPAPI:
            df = serpapi_fetch_trends(kw_list, timeframe, geo)
        else:
            df = pytrends_fetch_trends(kw_list, timeframe, geo)

        if not df.empty:
            df_save = df.reset_index()
            # Timestamp → 字串，避免 JSON 序列化錯誤
            for col in df_save.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
                df_save[col] = df_save[col].astype(str)
            save_cache(cache_key, df_save.to_dict(orient="list"))
        return df, False
    except Exception as e:
        st.error(f"❌ 趨勢查詢失敗：{e}\n\n請等 5~10 分鐘後再試。")
        return pd.DataFrame(), False

def fetch_related(kw_list, timeframe, geo):
    cache_key = f"related_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key, CACHE_HOURS_RELATED)
    if cached:
        return cached, True

    try:
        if USE_SERPAPI:
            result = serpapi_fetch_related(kw_list, timeframe, geo)
        else:
            result = pytrends_fetch_related(kw_list, timeframe, geo)

        if result:
            save_cache(cache_key, result)
        return result, False
    except Exception as e:
        st.error(f"❌ 相關詞查詢失敗：{e}")
        return {}, False

def fetch_regional(kw_list, timeframe, geo):
    cache_key = f"region_{'-'.join(kw_list)}_{timeframe}_{geo}"
    cached = load_cache(cache_key, CACHE_HOURS_REGION)
    if cached:
        df = pd.DataFrame(cached)
        if "geoName" in df.columns:
            df = df.set_index("geoName")
        return df, True

    try:
        # 地區分布目前只用 pytrends（SerpApi 地區功能需另外串接）
        df = pytrends_fetch_regional(kw_list, timeframe, geo)
        if not df.empty:
            df_save = df.reset_index()
            for col in df_save.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
                df_save[col] = df_save[col].astype(str)
            save_cache(cache_key, df_save.to_dict(orient="list"))
        return df, False
    except Exception as e:
        st.error(f"❌ 地區查詢失敗：{e}")
        return pd.DataFrame(), False

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.title("🩺 PT 衛教情報站")
st.caption("掌握近期台灣民眾最關心的身體問題，找到下一篇文章的靈感")

# 資料來源標示
if USE_SERPAPI:
    st.success("✅ 目前使用 **SerpApi**（穩定模式）")
else:
    st.info("ℹ️ 目前使用 **pytrends**（免費模式）｜ 若遇到 429 錯誤，App 會自動重試")

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
    st.markdown(
        f"**⏱️ 快取有效期限**\n\n"
        f"- 熱度走勢：{CACHE_HOURS_TRENDS} 小時\n"
        f"- 飆升關鍵字：{CACHE_HOURS_RELATED} 小時\n"
        f"- 地區分布：{CACHE_HOURS_REGION} 小時\n\n"
        "快取期間開 App 不打 API，完全不會被擋。"
    )

    force_refresh = st.button("🔄 強制重新抓取")

    st.divider()

    # SerpApi 設定說明
    with st.expander("💡 如何啟用 SerpApi 穩定模式？"):
        st.markdown(
            "1. 前往 [serpapi.com](https://serpapi.com) 免費註冊\n"
            "2. 複製你的 API Key\n"
            "3. 在 Streamlit Cloud 的 App 設定頁面，點 **Secrets**\n"
            "4. 貼上以下內容：\n"
            "```\n[serpapi]\nkey = \"你的API Key\"\n```\n"
            "5. 儲存後 App 自動切換到穩定模式 ✅\n\n"
            "免費方案每月 100 次查詢，個人使用完全夠用。"
        )

# ── 解析關鍵字 ──
raw = keyword_input.replace("\n", ",")
kw_list = [x.strip() for x in raw.split(",") if x.strip()][:5]

if not kw_list:
    st.warning("請輸入至少一個關鍵字")
    st.stop()

if force_refresh:
    for f in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, f))
        except Exception:
            pass
    st.success("✅ 快取已清除，將重新抓取最新資料。")

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

        # 確保欄位只取關鍵字
        available = [k for k in kw_list if k in df_trends.columns]

        fig = px.line(
            df_trends, y=available,
            labels={"value": "搜尋熱度（0-100）", "date": "日期", "variable": "關鍵字"},
            title="關鍵字搜尋熱度走勢",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig.update_layout(hovermode="x unified", legend_title_text="關鍵字")
        st.plotly_chart(fig, use_container_width=True)

        # 平均熱度排行
        st.subheader("🏆 平均熱度排行")
        avg = df_trends[available].mean().sort_values(ascending=False).reset_index()
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
        st.warning("⏳ 若剛遇到限流，請等 5~10 分鐘後重新整理。")

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
                if rising and (isinstance(rising, dict) and rising.get("query")):
                    df_r = pd.DataFrame(rising)
                    df_r.columns = ["關鍵字", "成長幅度"]
                    st.dataframe(df_r, hide_index=True, use_container_width=True)
                else:
                    st.info("目前無飆升詞數據")

            with col_top:
                st.markdown("**📊 熱門詞（長期熱搜）**")
                top = related_data.get(kw, {}).get("top")
                if top and (isinstance(top, dict) and top.get("query")):
                    df_t = pd.DataFrame(top)
                    df_t.columns = ["關鍵字", "相對熱度"]
                    st.dataframe(df_t, hide_index=True, use_container_width=True)
                else:
                    st.info("目前無熱門詞數據")

            st.divider()

        st.info("💡 飆升詞適合當**文章標題關鍵字**，熱門詞適合放在**文章內文**中自然帶入。")

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
        st.warning("⏳ 若剛遇到限流，請等 5~10 分鐘後重新整理。")

st.divider()
st.caption("🩺 PT 衛教情報站 ｜ 數據來源：Google Trends ｜ 快取機制：24 小時自動更新")

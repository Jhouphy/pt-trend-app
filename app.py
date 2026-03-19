import streamlit as st
from urllib.parse import urlencode
import datetime
import requests
import xml.etree.ElementTree as ET
import time
from muscles_data import MUSCLES, MOVEMENTS, ALIASES, SOURCES

st.set_page_config(page_title="PT 文章發想站", page_icon="📚", layout="wide")

# ─────────────────────────────────────────
# 預設值
# ─────────────────────────────────────────
CURRENT_YEAR = datetime.datetime.now().year

# 文獻搜尋
DEFAULT_BASE = "physical therapy"
DEFAULT_EXCL = "animal, rat, mice, cadaver, pediatric"

LIT_GROUP_A = [
    "neck pain", "shoulder pain", "low back pain", "knee pain",
    "plantar fasciitis", "adhesive capsulitis", "shoulder impingement",
    "myofascial pain syndrome", "ankle sprain", "osteoarthritis",
]
LIT_GROUP_B = [
    "therapy exercises", "manual therapy",
    "guidelines", "systematic reviews", "mechanism",
]

# 社群雷達
DEFAULT_SUBREDDITS = ["physicaltherapy", "backpain", "fitness", "AskDocs"]
REDDIT_GROUP_A = [
    "neck pain", "shoulder pain", "low back pain", "knee pain",
    "plantar fasciitis", "adhesive capsulitis", "shoulder impingement",
    "myofascial pain syndrome", "ankle sprain", "osteoarthritis",
]
REDDIT_GROUP_B = [
    "exercise", "treatment", "diagnosis", "recovery", "stretching",
]

# ─────────────────────────────────────────
# Session State
# ─────────────────────────────────────────
for key, default in [
    ("lit_sel_a",  set()),
    ("lit_sel_b",  set()),
    ("lit_results", None),
    ("lit_last_query", ""),
    ("red_sel_a",  set()),
    ("red_sel_b",  set()),
    ("subreddits", DEFAULT_SUBREDDITS.copy()),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────
# 共用函式
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

# ─────────────────────────────────────────
# 文獻搜尋函式
# ─────────────────────────────────────────
def scholar_url(query: str, base: str, excl: list, y1: int, y2: int) -> str:
    full = query
    if base.strip():
        full += f" {base.strip()}"
    for ex in excl:
        if ex.strip():
            full += f" -{ex.strip()}"
    return "https://scholar.google.com/scholar?" + urlencode({"q": full, "as_ylo": y1, "as_yhi": y2})

def pubmed_tab_url(query: str, base: str, excl: list, y1: int, y2: int) -> str:
    full = query
    if base.strip():
        full += f" {base.strip()}"
    excl_str = " NOT ".join(ex.strip() for ex in excl if ex.strip())
    if excl_str:
        full += f" NOT ({excl_str})"
    return "https://pubmed.ncbi.nlm.nih.gov/?" + urlencode({
        "term": f"({full}) AND {y1}:{y2}[pdat]"
    })

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def pubmed_search(query: str, base: str, excl: list,
                  y1: int, y2: int, limit: int = 20) -> list:
    full = query
    if base.strip():
        full += f" {base.strip()}"
    excl_str = " NOT ".join(ex.strip() for ex in excl if ex.strip())
    if excl_str:
        full += f" NOT ({excl_str})"
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
    try:
        time.sleep(0.3)
        r2 = requests.get(EFETCH, params={
            "db": "pubmed", "id": ",".join(pmids),
            "retmode": "xml", "rettype": "abstract"
        }, timeout=20)
        r2.raise_for_status()
    except Exception as e:
        st.error(f"PubMed 抓取失敗：{e}")
        return []
    papers = []
    for art in ET.fromstring(r2.content).findall(".//PubmedArticle"):
        try:
            title_el = art.find(".//ArticleTitle")
            title    = "".join(title_el.itertext()) if title_el is not None else ""
            auths    = art.findall(".//Author")
            names    = []
            for a in auths[:3]:
                last  = a.findtext("LastName", "")
                first = a.findtext("ForeName", "")
                if last:
                    names.append(f"{last} {first}".strip())
            authors  = ", ".join(names) + (" et al." if len(auths) > 3 else "")
            journal  = art.findtext(".//Journal/Title", "") or art.findtext(".//ISOAbbreviation", "") or ""
            year_raw = art.findtext(".//PubDate/Year", "") or art.findtext(".//PubDate/MedlineDate", "") or ""
            year     = year_raw[:4]
            pmid_el  = art.find(".//PMID")
            pmid     = pmid_el.text if pmid_el is not None else ""
            abs_parts = art.findall(".//AbstractText")
            abstract  = " ".join("".join(p.itertext()) for p in abs_parts)
            doi = ""
            for el in art.findall(".//ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = el.text or ""
                    break
            link = f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}" if pmid else "")
            papers.append({"title": title, "authors": authors, "journal": journal,
                           "year": year, "abstract": abstract, "link": link})
        except Exception:
            continue
    return papers

# ─────────────────────────────────────────
# Reddit 函式
# ─────────────────────────────────────────
def reddit_search_url(query: str, subreddits: list, sort: str = "relevance") -> str:
    sr = "+".join(subreddits)
    return f"https://www.reddit.com/r/{sr}/search/?" + urlencode({
        "q": query, "sort": sort, "restrict_sr": 1, "t": "year",
    })

def reddit_hot_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/hot/"

def reddit_new_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/new/"

# ─────────────────────────────────────────
# 頁面標題
# ─────────────────────────────────────────
st.title("📚 PT 文章發想站")
st.caption("文獻搜尋 · 社群雷達 · 衛教靈感一站搞定")

# ─────────────────────────────────────────
# 頂部 Tab
# ─────────────────────────────────────────
tab_lit, tab_reddit, tab_muscle, tab_drug = st.tabs(["📖 文獻搜尋", "💬 社群雷達", "🦴 肌肉查詢", "💊 藥物查詢"])

# ══════════════════════════════════════════
# Tab 1：文獻搜尋
# ══════════════════════════════════════════
with tab_lit:

    # 側邊欄設定（只在文獻搜尋 tab 使用）
    with st.sidebar:
        st.header("⚙️ 文獻搜尋設定")
        base     = st.text_input("📌 固定包含詞", value=DEFAULT_BASE)
        excl_raw = st.text_area("🚫 排除關鍵字（逗號分隔）", value=DEFAULT_EXCL, height=80)
        excl     = [k.strip() for k in excl_raw.split(",") if k.strip()]
        c1, c2   = st.columns(2)
        y1       = c1.number_input("起始年份", min_value=2000, max_value=CURRENT_YEAR, value=2015)
        y2       = c2.number_input("結束年份", min_value=2000, max_value=CURRENT_YEAR, value=CURRENT_YEAR)
        result_limit = st.selectbox("顯示筆數", [10, 20, 30], index=1)

        st.divider()
        if st.button("🗑️ 清除文獻選取", use_container_width=True):
            st.session_state.lit_sel_a   = set()
            st.session_state.lit_sel_b   = set()
            st.session_state.lit_results = None
            st.rerun()

        st.divider()

        # 社群雷達設定
        st.header("⚙️ 社群雷達設定")
        sort_mode = st.selectbox(
            "Reddit 排序",
            options=["relevance", "top", "new", "hot"],
            format_func=lambda x: {
                "relevance": "🎯 相關度", "top": "⬆️ 高分",
                "new": "🆕 最新",        "hot": "🔥 熱門"
            }[x]
        )
        new_sub = st.text_input("➕ 新增社群", placeholder="e.g. running")
        if st.button("新增社群", use_container_width=True) and new_sub.strip():
            sub = new_sub.strip().lstrip("r/")
            if sub not in st.session_state.subreddits:
                st.session_state.subreddits.append(sub)
                st.rerun()
        if st.button("🗑️ 清除社群選取", use_container_width=True):
            st.session_state.red_sel_a = set()
            st.session_state.red_sel_b = set()
            st.rerun()

    # ── 自訂搜尋框 ──
    lit_custom = st.text_input(
        "🔍 自訂關鍵字（選填，可搭配下方 A/B 組）",
        placeholder="e.g. rotator cuff, disc herniation...",
        key="lit_custom"
    )
    st.divider()

    # ── A 組 ──
    st.markdown("**A 組：主題**　`點擊選取 / 再點取消`")
    cols_a = st.columns(5)
    for i, topic in enumerate(LIT_GROUP_A):
        is_sel = topic in st.session_state.lit_sel_a
        label  = f"✅ {topic}" if is_sel else topic
        if cols_a[i % 5].button(label, key=f"lit_a_{topic}", use_container_width=True):
            st.session_state.lit_sel_a.discard(topic) if is_sel else st.session_state.lit_sel_a.add(topic)
            st.rerun()

    st.divider()

    # ── B 組 ──
    st.markdown("**B 組：文獻類型**　`點擊選取 / 再點取消`")
    cols_b = st.columns(5)
    for i, btype in enumerate(LIT_GROUP_B):
        is_sel = btype in st.session_state.lit_sel_b
        label  = f"✅ {btype}" if is_sel else btype
        if cols_b[i].button(label, key=f"lit_b_{btype}", use_container_width=True):
            st.session_state.lit_sel_b.discard(btype) if is_sel else st.session_state.lit_sel_b.add(btype)
            st.rerun()

    st.divider()

    # ── 搜尋區 ──
    lit_sel_a = sorted(st.session_state.lit_sel_a)
    lit_sel_b = sorted(st.session_state.lit_sel_b)
    has_input = lit_custom.strip() or lit_sel_a or lit_sel_b

    if has_input:
        query   = build_query(lit_custom.strip(), lit_sel_a, lit_sel_b)
        preview = query + (f" {base.strip()}" if base.strip() else "")
        st.markdown("**搜尋詞：**")
        st.code(preview)

        c1, c2, c3 = st.columns(3)
        do_search  = c1.button("🔬 PubMed（結果顯示下方）",
                               use_container_width=True, type="primary", key="lit_search")
        c2.link_button("🔗 PubMed（開新分頁）",
                       url=pubmed_tab_url(query, base, excl, y1, y2),
                       use_container_width=True)
        c3.link_button("🔗 Google Scholar（開新分頁）",
                       url=scholar_url(query, base, excl, y1, y2),
                       use_container_width=True)

        if do_search:
            with st.spinner("正在從 PubMed 抓取文獻..."):
                st.session_state.lit_results    = pubmed_search(query, base, excl, y1, y2, result_limit)
                st.session_state.lit_last_query = preview

        if st.session_state.lit_results is not None:
            papers = st.session_state.lit_results
            st.divider()
            if not papers:
                st.warning("查無文獻，請嘗試調整關鍵字或放寬年份範圍。")
            else:
                st.subheader(f"📋 搜尋結果（共 {len(papers)} 篇）")
                st.caption(f"搜尋詞：`{st.session_state.lit_last_query}`")
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

# ══════════════════════════════════════════
# Tab 2：社群雷達
# ══════════════════════════════════════════
with tab_reddit:
    st.subheader("💬 PT 社群雷達")
    st.caption("快速產生 Reddit 搜尋連結，瀏覽民眾討論的身體健康問題")

    # ── 各社群快速入口 ──
    st.markdown("**📌 社群快速入口**")
    subs      = st.session_state.subreddits
    sub_cols  = st.columns(len(subs))
    for i, sub in enumerate(subs):
        with sub_cols[i]:
            st.markdown(f"**r/{sub}**")
            st.link_button("🔥 熱門", url=reddit_hot_url(sub), use_container_width=True)
            st.link_button("🆕 最新", url=reddit_new_url(sub), use_container_width=True)

    st.divider()

    # ── 自訂搜尋框 ──
    red_custom = st.text_input(
        "🔍 自訂關鍵字（選填，可搭配下方 A/B 組）",
        placeholder="e.g. herniated disc, dry needling...",
        key="red_custom"
    )
    st.divider()

    # ── A 組 ──
    st.markdown("**A 組：主題**　`點擊選取 / 再點取消`")
    r_cols_a = st.columns(5)
    for i, topic in enumerate(REDDIT_GROUP_A):
        is_sel = topic in st.session_state.red_sel_a
        label  = f"✅ {topic}" if is_sel else topic
        if r_cols_a[i % 5].button(label, key=f"red_a_{topic}", use_container_width=True):
            st.session_state.red_sel_a.discard(topic) if is_sel else st.session_state.red_sel_a.add(topic)
            st.rerun()

    st.divider()

    # ── B 組 ──
    st.markdown("**B 組：討論類型**　`點擊選取 / 再點取消`")
    r_cols_b = st.columns(5)
    for i, btype in enumerate(REDDIT_GROUP_B):
        is_sel = btype in st.session_state.red_sel_b
        label  = f"✅ {btype}" if is_sel else btype
        if r_cols_b[i].button(label, key=f"red_b_{btype}", use_container_width=True):
            st.session_state.red_sel_b.discard(btype) if is_sel else st.session_state.red_sel_b.add(btype)
            st.rerun()

    st.divider()

    # ── 搜尋區 ──
    red_sel_a  = sorted(st.session_state.red_sel_a)
    red_sel_b  = sorted(st.session_state.red_sel_b)
    red_input  = red_custom.strip() or red_sel_a or red_sel_b

    if red_input:
        red_query = build_query(red_custom.strip(), red_sel_a, red_sel_b)
        st.markdown("**搜尋詞：**")
        st.code(red_query)

        # 各社群分別搜尋
        st.markdown("**分別搜尋各社群：**")
        btn_cols = st.columns(len(subs))
        for i, sub in enumerate(subs):
            btn_cols[i].link_button(
                f"r/{sub}",
                url=reddit_search_url(red_query, [sub], sort_mode),
                use_container_width=True,
                key=f"search_{sub}"
            )

        # 全部合併搜尋
        st.link_button(
            f"🔍 全部社群合併搜尋（{', '.join(f'r/{s}' for s in subs)}）",
            url=reddit_search_url(red_query, subs, sort_mode),
            use_container_width=True
        )
    else:
        st.info("☝️ 輸入自訂關鍵字，或點選上方 A/B 組的標籤，搜尋按鈕會出現在這裡。")


# ══════════════════════════════════════════
# Tab 3：肌肉查詢
# ══════════════════════════════════════════
with tab_muscle:
    st.subheader("🦴 肌肉骨骼查詢")
    st.caption("查詢動作的主動肌/協同肌/拮抗肌，或搜尋特定肌肉的起止點、神經支配、功能")

    muscle_tab1, muscle_tab2 = st.tabs(["🔄 動作查詢", "🔍 肌肉查詢"])

    # ── 動作查詢 ──
    with muscle_tab1:
        st.markdown("**輸入關節動作，查詢相關肌肉**")

        # 動作分類快速選取
        JOINT_GROUPS = {
            "髖關節 Hip":     ["hip flexion", "hip extension", "hip abduction", "hip adduction", "hip internal rotation", "hip external rotation"],
            "膝關節 Knee":    ["knee flexion", "knee extension", "knee internal rotation", "knee external rotation"],
            "踝關節 Ankle":   ["ankle dorsiflexion", "ankle plantarflexion", "foot inversion", "foot eversion"],
            "肩關節 Shoulder":["shoulder flexion", "shoulder extension", "shoulder abduction", "shoulder adduction", "shoulder internal rotation", "shoulder external rotation", "shoulder horizontal abduction", "shoulder horizontal adduction"],
            "肩胛骨 Scapular":["scapular elevation", "scapular depression", "scapular retraction", "scapular protraction", "scapular upward rotation"],
            "肘/前臂 Elbow":  ["elbow flexion", "elbow extension", "forearm supination", "forearm pronation"],
            "腕關節 Wrist":   ["wrist flexion", "wrist extension", "wrist radial deviation", "wrist ulnar deviation"],
            "脊椎 Spine":     ["trunk flexion", "trunk extension", "trunk rotation", "trunk lateral flexion"],
            "頸椎 Cervical":  ["neck flexion", "neck extension", "neck rotation", "neck lateral flexion"],
        }

        # 選擇關節分類
        joint_sel = st.selectbox(
            "選擇關節",
            options=list(JOINT_GROUPS.keys()),
            key="joint_group"
        )

        # 選擇動作
        actions = JOINT_GROUPS[joint_sel]
        action_sel = st.selectbox(
            "選擇動作",
            options=actions,
            format_func=lambda x: f"{MOVEMENTS[x]['zh']}  ({x})" if x in MOVEMENTS else x,
            key="action_sel"
        )

        if action_sel and action_sel in MOVEMENTS:
            mv = MOVEMENTS[action_sel]
            st.divider()
            st.markdown(f"### {mv['zh']}　`{action_sel}`")
            st.caption(f"關節：{mv['joint']}")

            col_a, col_s, col_ant = st.columns(3)

            def show_muscle_list(col, title, color, muscle_list):
                with col:
                    st.markdown(f"**{title}**")
                    for m in muscle_list:
                        m_key = m.lower().split(" (")[0].strip()
                        info = MUSCLES.get(m_key)
                        zh   = info["zh"] if info else ""
                        label = f"{zh}  " if zh else ""
                        note  = f" *({m.split('(')[-1].rstrip(')')})*" if "(" in m else ""
                        if info:
                            with st.expander(f"{label}{m_key}{note}"):
                                st.markdown(f"**起點：** {info['origin']}")
                                st.markdown(f"**止點：** {info['insertion']}")
                                st.markdown(f"**神經：** {info['innervation']}")
                                st.markdown(f"**功能：** {'; '.join(info['functions'])}")
                                if info.get("antagonists"):
                                    st.markdown(f"**拮抗肌：** {', '.join(info['antagonists'])}")
                        else:
                            st.markdown(f"- {m}")

            show_muscle_list(col_a,   "🔴 主動肌 Agonists",    "red",   mv["agonists"])
            show_muscle_list(col_s,   "🟡 協同肌 Synergists",  "orange",mv["synergists"])
            show_muscle_list(col_ant, "🔵 拮抗肌 Antagonists", "blue",  mv["antagonists"])

    # ── 肌肉查詢 ──
    with muscle_tab2:
        st.markdown("**輸入肌肉名稱查詢詳細資料**")
        st.caption("支援英文全名、中文名、常用縮寫（如 hamstrings、rotator cuff、旋轉肌袖）")

        muscle_query = st.text_input(
            "搜尋肌肉",
            placeholder="e.g. biceps brachii / 肱二頭肌 / hamstrings / 旋轉肌袖",
            key="muscle_search"
        ).strip().lower()

        if muscle_query:
            # 檢查別名
            expanded = ALIASES.get(muscle_query, [muscle_query])
            found = []
            for q in expanded:
                # 完整比對
                if q in MUSCLES:
                    found.append((q, MUSCLES[q]))
                else:
                    # 部分比對
                    matches = [(k, v) for k, v in MUSCLES.items()
                               if q in k or q in v.get("zh", "").lower()]
                    found.extend(matches)

            # 去重
            seen  = set()
            unique = []
            for k, v in found:
                if k not in seen:
                    seen.add(k)
                    unique.append((k, v))

            if unique:
                st.success(f"找到 {len(unique)} 筆結果")
                for muscle_name, info in unique:
                    with st.expander(f"**{info['zh']}**　{muscle_name}　｜　{info['region']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**🟢 起點 Origin：**")
                            st.info(info["origin"])
                            st.markdown(f"**🔴 止點 Insertion：**")
                            st.info(info["insertion"])
                        with col2:
                            st.markdown(f"**⚡ 神經支配 Innervation：**")
                            st.info(info["innervation"])
                            st.markdown(f"**🎯 功能 Functions：**")
                            st.info("\n".join(f"• {f}" for f in info["functions"]))
                        if info.get("antagonists"):
                            st.markdown(f"**↔️ 拮抗肌 Antagonists：** {', '.join(info['antagonists'])}")
                        st.markdown(f"[🔗 Wikipedia 查看完整資料](https://en.wikipedia.org/wiki/{muscle_name.replace(' ', '_')})")
            else:
                st.warning(f"找不到「{muscle_query}」的資料，請嘗試英文全名或部分關鍵字。")
                # 顯示部分建議
                suggestions = [k for k in MUSCLES if muscle_query[:4] in k][:5]
                if suggestions:
                    st.caption("您是否在找：" + "、".join(suggestions))

        # 按 Region 瀏覽
        st.divider()
        st.markdown("**或依部位瀏覽所有肌肉：**")
        regions = sorted(set(v["region"] for v in MUSCLES.values()))
        region_sel = st.selectbox("選擇部位", ["（請選擇）"] + regions, key="region_browse")
        if region_sel != "（請選擇）":
            region_muscles = {k: v for k, v in MUSCLES.items() if v["region"] == region_sel}
            st.caption(f"共 {len(region_muscles)} 條肌肉")
            for muscle_name, info in region_muscles.items():
                with st.expander(f"{info['zh']}　{muscle_name}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**起點：**")
                        st.info(info["origin"])
                        st.markdown("**止點：**")
                        st.info(info["insertion"])
                    with c2:
                        st.markdown("**神經：**")
                        st.info(info["innervation"])
                        st.markdown("**功能：**")
                        st.info("\n".join(f"• {f}" for f in info["functions"]))
                    if info.get("antagonists"):
                        st.markdown(f"**拮抗肌：** {', '.join(info['antagonists'])}")

    # ── 資料來源 ──
    st.divider()
    st.markdown("**📖 資料來源**")
    for src in SOURCES:
        st.markdown(f"- [{src['name']}]({src['url']})　*{src['note']}*")


# ══════════════════════════════════════════
# Tab 4：藥物查詢
# ══════════════════════════════════════════
with tab_drug:
    st.subheader("💊 藥物查詢")
    st.caption("查詢藥物的適應症、副作用、禁忌症、注意事項")

    OPENFDA_URL   = "https://api.fda.gov/drug/label.json"
    TAIWAN_FDA_URL = "https://info.fda.gov.tw/MLMS/H0001.aspx"

    def search_openfda(query: str, limit: int = 5) -> list:
        try:
            r = requests.get(OPENFDA_URL, params={
                "search": (f'openfda.brand_name:"{query}" OR '
                           f'openfda.generic_name:"{query}" OR '
                           f'openfda.substance_name:"{query}"'),
                "limit": limit
            }, timeout=15)
            if r.status_code == 200 and r.json().get("results"):
                return r.json()["results"]
            # 退而求其次：模糊搜尋
            r2 = requests.get(OPENFDA_URL, params={
                "search": f'openfda.generic_name:({query})',
                "limit": limit
            }, timeout=15)
            if r2.status_code == 200:
                return r2.json().get("results", [])
        except Exception as e:
            st.error(f"openFDA 查詢失敗：{e}")
        return []

    def parse_field(result: dict, *fields, max_len: int = 600) -> str:
        for field in fields:
            val = result.get(field)
            if val:
                text = val[0] if isinstance(val, list) else str(val)
                text = " ".join(text.split())
                return text[:max_len] + ("…" if len(text) > max_len else "")
        return "（無資料）"

    # ── 常用藥物快速選取 ──
    # 藥物中英對照
    DRUG_ZH = {
        "ibuprofen": "布洛芬", "naproxen": "萘普生", "diclofenac": "待克菲那",
        "celecoxib": "西樂葆", "indomethacin": "消炎痛",
        "cyclobenzaprine": "環苯紮林", "baclofen": "巴氯芬",
        "tizanidine": "替紮尼定", "methocarbamol": "甲氧卡巴莫",
        "acetaminophen": "乙醯氨酚/普拿疼", "tramadol": "曲馬多",
        "gabapentin": "加巴噴丁", "pregabalin": "普瑞巴林",
        "prednisone": "普賴松", "methylprednisolone": "甲基培尼皮質醇",
        "dexamethasone": "地塞米松",
        "lidocaine": "利多卡因", "capsaicin": "辣椒素",
        "diclofenac gel": "待克菲那凝膠",
    }

    COMMON_DRUGS = {
        "NSAIDs 非類固醇消炎藥": ["ibuprofen", "naproxen", "diclofenac", "celecoxib"],
        "肌肉鬆弛劑": ["cyclobenzaprine", "baclofen", "tizanidine", "methocarbamol"],
        "止痛/神經痛藥": ["acetaminophen", "tramadol", "gabapentin", "pregabalin"],
        "類固醇": ["prednisone", "methylprednisolone", "dexamethasone"],
        "外用藥": ["lidocaine", "capsaicin", "diclofenac gel"],
    }

    # ── 翻譯函式（使用 deep-translator，不需要 API Key）──
    def translate_to_zh(text: str) -> str:
        """將英文翻譯為繁體中文，藥物名稱不翻譯"""
        if not text or text == "（無資料）":
            return text
        try:
            from deep_translator import GoogleTranslator
            # 限制長度避免超過 API 限制
            if len(text) > 4500:
                text = text[:4500] + "..."
            return GoogleTranslator(source="en", target="zh-TW").translate(text)
        except Exception as e:
            return f"（翻譯失敗：{e}）"

    if "drug_quick" not in st.session_state:
        st.session_state.drug_quick = ""

    # ── 搜尋框（放在快速選取上方，更直覺）──
    drug_query = st.text_input(
        "🔍 輸入藥品名稱（英文學名、商品名或中文）",
        value=st.session_state.drug_quick,
        placeholder="e.g. ibuprofen / 布洛芬 / naproxen / gabapentin",
        key="drug_input"
    ).strip()

    st.divider()
    st.markdown("**或從常見 PT 相關藥物快速選取：**")
    for cat_idx, (category, drugs) in enumerate(COMMON_DRUGS.items()):
        st.caption(f"**{category}**")
        d_cols = st.columns(len(drugs))
        for i, d in enumerate(drugs):
            zh = DRUG_ZH.get(d, "")
            label = f"{d}\n{zh}" if zh else d
            # key 加入 cat_idx 避免跨分類重複
            if d_cols[i].button(d, key=f"dq_{cat_idx}_{d}", use_container_width=True,
                                help=zh if zh else None):
                st.session_state.drug_quick = d
                st.rerun()

    st.divider()

    if drug_query:
        c1, c2 = st.columns(2)
        c1.link_button(
            "🇹🇼 台灣食藥署查詢（開新分頁）",
            url=f"{TAIWAN_FDA_URL}?drugName={drug_query.replace(' ', '+')}",
            use_container_width=True
        )
        c2.link_button(
            "🌐 Drugs.com（開新分頁）",
            url=f"https://www.drugs.com/search.php?searchterm={drug_query.replace(' ', '+')}",
            use_container_width=True
        )

        st.divider()
        st.markdown(f"**📋 openFDA 資料庫查詢結果：`{drug_query}`**")

        with st.spinner("查詢中..."):
            results = search_openfda(drug_query)

        if not results:
            st.warning(
                f"openFDA 找不到 '{drug_query}'。 建議：改用英文學名查詢，或點上方按鈕到台灣食藥署查中文藥品。"
            )
        else:
            st.success(f"找到 {len(results)} 筆資料")
            for i, res in enumerate(results, 1):
                openfda = res.get("openfda", {})
                brand   = "、".join(openfda.get("brand_name",   ["未知商品名"])[:2])
                generic = "、".join(openfda.get("generic_name", ["未知學名"])[:2])
                manuf   = "、".join(openfda.get("manufacturer_name", ["未知廠商"])[:1])

                with st.expander(f"#{i}　{brand}　｜　{generic}"):
                    st.caption(f"製造商：{manuf}")

                    show_zh = st.toggle(
                        "🌐 顯示中文翻譯（原文保留）",
                        value=False,
                        key=f"tr_{i}_{drug_query[:10]}"
                    )

                    fields = [
                        ("🎯 適應症 Indications",        "info",    parse_field(res, "indications_and_usage", "purpose")),
                        ("🚫 禁忌症 Contraindications",  "warning", parse_field(res, "contraindications")),
                        ("⚠️ 副作用 Adverse Reactions",  "error",   parse_field(res, "adverse_reactions", "warnings_and_cautions", "warnings")),
                        ("📌 注意事項 Warnings",         "warning", parse_field(res, "warnings_and_cautions", "precautions", "information_for_patients")),
                        ("💊 劑量 Dosage & Administration", "info", parse_field(res, "dosage_and_administration")),
                    ]

                    col_a, col_b = st.columns(2)
                    for fi, (label, color, eng_text) in enumerate(fields):
                        col = col_a if fi % 2 == 0 else col_b
                        with col:
                            st.markdown(f"**{label}**")
                            getattr(st, color)(eng_text)
                            if show_zh and eng_text != "（無資料）":
                                with st.spinner("翻譯中..."):
                                    zh_text = translate_to_zh(eng_text)
                                st.caption(f"📝 **中文：** {zh_text}")

        st.divider()
        st.caption(
            "⚠️ 以上資訊僅供專業人員參考，不構成醫療建議。"
            "實際用藥請遵照醫師處方及藥師指示。"
        )
        st.caption(
            "📖 資料來源：[openFDA](https://open.fda.gov/)（美國 FDA 開放資料）　｜　"
            "[台灣食藥署](https://www.fda.gov.tw/)　｜　"
            "[Drugs.com](https://www.drugs.com/)"
        )
    else:
        st.info("☝️ 點選上方常用藥物，或輸入藥品名稱開始查詢。")


st.divider()
st.caption("📚 PT 文章發想站　｜　PubMed · Google Scholar · Reddit　｜　完全免費，不需要 API Key")

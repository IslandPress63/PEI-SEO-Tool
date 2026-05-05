import re, os
import streamlit as st

try:
    import yake
    YAKE_OK = True
except ImportError:
    YAKE_OK = False

try:
    from pytrends.request import TrendReq
    PYTRENDS_OK = True
except ImportError:
    PYTRENDS_OK = False

try:
    from anthropic import Anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

st.set_page_config(page_title="PEI News | SEO Headline Generator", page_icon="📰", layout="wide")

st.markdown("""
<style>
    .tip  { background:#e8f4fd; border-left:4px solid #3498db; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:0.9em; }
    .warn { background:#fff3cd; border-left:4px solid #f0ad4e; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:0.9em; }
</style>
""", unsafe_allow_html=True)

PEI_TERMS = ["PEI","Prince Edward Island","Charlottetown","Summerside","Stratford","Montague","Souris","Island","Islander"]
POWER_WORDS = ["new","first","how","why","local","exclusive","breaking","update","top","best","opens","closes","announces","launches","wins","record","historic","community","residents"]

def score_headline(headline):
    score = 0
    issues = []
    tips = []
    length = len(headline)
    if 50 <= length <= 65:
        score += 25
    elif 40 <= length <= 75:
        score += 15
        tips.append(f"Headline is {length} chars — aim for 50-65 for best Google display.")
    else:
        issues.append(f"Length is {length} chars — ideal is 50-65 characters.")
        score += 5
    if re.search(r'\d', headline):
        score += 15
    else:
        tips.append("Adding a specific number boosts click-through rates.")
    if any(w.lower() in headline.lower() for w in POWER_WORDS):
        score += 15
    if any(t.lower() in headline.lower() for t in PEI_TERMS):
        score += 20
    else:
        tips.append("Add a local identifier (PEI, Charlottetown, Island) to strengthen local SEO.")
    if len(headline.split()) >= 4:
        score += 10
    elif len(headline.split()) >= 2:
        score += 5
    if headline.strip().endswith("?"):
        score += 5
    if ":" in headline or "-" in headline:
        score += 5
    if headline == headline.upper() and len(headline) > 3:
        issues.append("Avoid ALL-CAPS headlines.")
        score = max(score - 15, 0)
    return min(score, 100), issues, tips

def score_emoji(score):
    if score >= 80: return "🟢"
    elif score >= 60: return "🟡"
    elif score >= 40: return "🟠"
    else: return "🔴"

def extract_keywords(text, max_kw=12):
    if not YAKE_OK or not text.strip():
        return []
    kw_extractor = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=max_kw)
    results = kw_extractor.extract_keywords(text)
    return [kw for kw, _ in sorted(results, key=lambda x: x[1])]

def get_trends(keywords, geo="CA-PE"):
    if not PYTRENDS_OK or not keywords:
        return {}
    try:
        pt = TrendReq(hl="en-US", tz=240, timeout=(10, 25))
        kw_batch = keywords[:5]
        pt.build_payload(kw_batch, cat=16, timeframe="today 3-m", geo=geo)
        df = pt.interest_over_time()
        if df.empty:
            pt.build_payload(kw_batch, cat=16, timeframe="today 3-m", geo="CA")
            df = pt.interest_over_time()
        if not df.empty:
            return {k: float(df[k].mean()) for k in kw_batch if k in df.columns}
    except Exception:
        pass
    return {}

def generate_headlines(topic, summary, keywords, trending, paper, api_key):
    if not api_key:
        return []
    client = Anthropic(api_key=api_key)
    kw_str = ", ".join(keywords[:8]) if keywords else topic
    trend_str = ""
    if trending:
        top = sorted(trending.items(), key=lambda x: x[1], reverse=True)[:3]
        trend_str = f"\nTrending in PEI: {', '.join(t[0] for t in top)}"
    paper_note = f"\nPaper: {paper}" if paper != "General / All Papers" else ""
    prompt = f"""Generate exactly 6 SEO-optimized web headlines for this PEI news story.
Topic: {topic}
Summary: {summary}
Key terms: {kw_str}{trend_str}{paper_note}
Rules: 50-65 chars, front-load keywords, include PEI location, be specific with names/numbers, active voice.
Return ONLY the 6 headlines numbered 1-6."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="You are an SEO editor for community newspapers in Prince Edward Island, Canada. Write clear, honest, compelling headlines optimised for Google News.",
        messages=[{"role": "user", "content": prompt}],
    )
    headlines = []
    for line in msg.content[0].text.strip().splitlines():
        cleaned = re.sub(r"^\d+[\.\)\-]\s*", "", line.strip()).strip()
        if cleaned:
            headlines.append(cleaned)
    return headlines

def generate_meta(topic, summary, api_key):
    if not api_key:
        return ""
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": f"Write a single SEO meta description (150-160 chars max) for this PEI news article. Topic: {topic}. Summary: {summary}. Return only the description."}],
    )
    return msg.content[0].text.strip()

def generate_tags(topic, summary, api_key):
    if not api_key:
        return []
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": f"Suggest 8 SEO tags for this PEI news article as a comma-separated list. Include geographic tags (PEI, Charlottetown etc). Topic: {topic}. Summary: {summary}"}],
    )
    return [t.strip() for t in msg.content[0].text.strip().split(",") if t.strip()]

st.title("📰 PEI News — SEO Headline Generator")
st.caption("Open-source stack: YAKE · PyTrends · Claude AI · Streamlit")

_secret_key = ""
try:
    _secret_key = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    _secret_key = os.environ.get("ANTHROPIC_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Configuration")
    if _secret_key:
        api_key = _secret_key
        st.success("✅ API key configured", icon="🔑")
    else:
        api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-…")
    paper = st.selectbox("Select Paper", ["General / All Papers","Eastern Graphic (Kings County)","Montague / Georgetown area","Summerside / West Prince area","Charlottetown / Queens County area"])
    check_trends = st.toggle("Check Google Trends", value=True)
    gen_meta = st.toggle("Generate meta description", value=True)
    gen_tags = st.toggle("Suggest article tags", value=True)
    st.divider()
    st.markdown("**SEO Score Key**")
    st.markdown("🟢 80-100 Excellent · 🟡 60-79 Good · 🟠 40-59 Fair · 🔴 0-39 Needs work")

col_in, col_out = st.columns([1, 1.1], gap="large")

with col_in:
    st.subheader("📝 Article Details")
    topic = st.text_input("Topic / Subject Line *", placeholder="e.g. New pedestrian bridge approved for Charlottetown waterfront")
    summary = st.text_area("Article Text or Key Facts *", placeholder="Paste your article or key bullet points here...", height=220)
    original = st.text_input("Existing Headline to Compare (optional)")
    go = st.button("🚀 Generate SEO Headlines", type="primary", use_container_width=True, disabled=(not topic and not summary))

with col_out:
    if go and (topic or summary):
        with st.spinner("Extracting keywords…"):
            keywords = extract_keywords(f"{topic} {summary}")
        if keywords:
            st.subheader("🔑 Keywords Detected")
            st.markdown("  ".join(f"`{kw}`" for kw in keywords[:10]))
        trending = {}
        if check_trends and keywords:
            with st.spinner("Checking Google Trends for PEI…"):
                trending = get_trends(keywords)
            if trending:
                st.subheader("📈 Google Trends (PEI, last 90 days)")
                for term, val in sorted(trending.items(), key=lambda x: -x[1])[:5]:
                    st.progress(max(int(val),1), text=f"{term} — {int(val)}/100")
        if original:
            st.subheader("🔍 Your Existing Headline")
            sc, iss, tps = score_headline(original)
            st.markdown(f"**{score_emoji(sc)} SEO Score: {sc}/100**")
            for i in iss: st.markdown(f'<div class="warn">⚠️ {i}</div>', unsafe_allow_html=True)
            for t in tps: st.markdown(f'<div class="tip">💡 {t}</div>', unsafe_allow_html=True)
            st.divider()
        if not api_key:
            st.warning("⚠️ Enter your Anthropic API key in the sidebar.")
        else:
            with st.spinner("Generating 6 SEO-optimized headlines…"):
                headlines = generate_headlines(topic, summary, keywords, trending, paper, api_key)
            if headlines:
                st.subheader("✨ Optimized Headlines")
                for i, hl in enumerate(headlines, 1):
                    sc, iss, tps = score_headline(hl)
                    char_count = len(hl)
                    with st.expander(f"{score_emoji(sc)} {sc}/100 · {char_count} chars · {hl}", expanded=(i==1)):
                        st.code(hl, language=None)
                        st.caption(f"Characters: {char_count}/65 {'✅' if char_count <= 65 else '⚠️'}")
                        for item in iss: st.markdown(f'<div class="warn">⚠️ {item}</div>', unsafe_allow_html=True)
                        for item in tps: st.markdown(f'<div class="tip">💡 {item}</div>', unsafe_allow_html=True)
            if gen_meta:
                with st.spinner("Writing meta description…"):
                    meta = generate_meta(topic, summary, api_key)
                if meta:
                    st.subheader("📋 Meta Description")
                    st.text_area("Copy to CMS:", meta, height=90, key="meta_out")
                    st.caption(f"Characters: {len(meta)}/160 {'✅' if len(meta) <= 160 else '⚠️'}")
            if gen_tags:
                with st.spinner("Suggesting tags…"):
                    tags = generate_tags(topic, summary, api_key)
                if tags:
                    st.subheader("🏷️ Suggested Tags")
                    st.markdown("  ".join(f"`{t}`" for t in tags))
    elif go:
        st.warning("Please enter a topic or article text.")
    else:
        st.info("👈 Fill in your article details and click Generate SEO Headlines.")

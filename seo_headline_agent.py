"""
PEI News SEO Headline Generator
================================
Open-source components used:
  - YAKE       : keyword extraction  (MIT licence)
  - PyTrends   : unofficial Google Trends API  (MIT licence)
  - Streamlit  : web UI framework  (Apache 2.0)
  - Anthropic  : Claude API for LLM generation

To run:
  streamlit run seo_headline_agent.py
"""

import re
import streamlit as st

# ── Optional imports (graceful degradation) ──────────────────────────────────
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

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PEI News | SEO Headline Generator",
    page_icon="📰",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .score-box { padding: 4px 10px; border-radius: 6px; font-weight: bold; display: inline-block; }
    .score-green  { background:#d4edda; color:#155724; }
    .score-yellow { background:#fff3cd; color:#856404; }
    .score-orange { background:#ffe5b4; color:#7a4a00; }
    .score-red    { background:#f8d7da; color:#721c24; }
    .tip  { background:#e8f4fd; border-left:4px solid #3498db; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:0.9em; }
    .warn { background:#fff3cd; border-left:4px solid #f0ad4e; padding:8px 12px; margin:4px 0; border-radius:0 6px 6px 0; font-size:0.9em; }
</style>
""", unsafe_allow_html=True)


# ── SEO SCORING ───────────────────────────────────────────────────────────────

PEI_TERMS = [
    "PEI", "Prince Edward Island", "Charlottetown", "Summerside",
    "Stratford", "Montague", "Souris", "Island", "Islander",
    "The Guardian", "Journal Pioneer", "Eastern Graphic",
]

POWER_WORDS = [
    "new", "first", "how", "why", "what", "when", "where", "who",
    "local", "exclusive", "breaking", "update", "guide", "top", "best",
    "alert", "opens", "closes", "announces", "launches", "wins", "loses",
    "warning", "record", "historic", "community", "residents",
]


def score_headline(headline: str) -> tuple[int, list[str], list[str]]:
    """Return (score 0-100, issues list, tips list)."""
    score = 0
    issues: list[str] = []
    tips: list[str] = []

    length = len(headline)

    # Length (25 pts)
    if 50 <= length <= 65:
        score += 25
    elif 40 <= length <= 75:
        score += 15
        if length < 50:
            tips.append(f"Headline is {length} chars — aim for 50–65 for best Google display.")
        else:
            tips.append(f"Headline is {length} chars — Google truncates around 65; consider trimming.")
    else:
        issues.append(f"Length is {length} chars — well outside the ideal 50–65 character window.")
        score += 5

    # Numbers (15 pts)
    if re.search(r'\d', headline):
        score += 15
    else:
        tips.append("Adding a specific number (e.g. '3 new jobs…', '$1.2M grant…') boosts click-through rates.")

    # Power / action words (15 pts)
    found = [w for w in POWER_WORDS if w.lower() in headline.lower()]
    if found:
        score += 15

    # Local PEI signal (20 pts)
    if any(t.lower() in headline.lower() for t in PEI_TERMS):
        score += 20
    else:
        tips.append("Add a local identifier (PEI, Charlottetown, Island, etc.) to strengthen local SEO.")

    # Keyword front-loading heuristic (10 pts)
    words = headline.split()
    if len(words) >= 4:
        score += 10
    elif len(words) >= 2:
        score += 5

    # Question bonus (5 pts) — good for featured snippets
    if headline.strip().endswith("?"):
        score += 5
        tips.append("Questions can win Google's 'People also ask' boxes — nice work!")

    # Colon / dash structure bonus (5 pts)
    if ":" in headline or "—" in headline or " - " in headline:
        score += 5

    # Penalise ALL CAPS
    if headline == headline.upper() and len(headline) > 3:
        issues.append("Avoid ALL-CAPS headlines — they hurt readability and can signal spam.")
        score = max(score - 15, 0)

    # Penalise excessive punctuation
    if headline.count("!") > 1:
        issues.append("Multiple exclamation marks look clickbait-y — use one at most.")
        score = max(score - 10, 0)

    return min(score, 100), issues, tips


def score_colour(score: int) -> str:
    if score >= 80:
        return "green", "🟢"
    elif score >= 60:
        return "yellow", "🟡"
    elif score >= 40:
        return "orange", "🟠"
    else:
        return "red", "🔴"


# ── KEYWORD EXTRACTION ────────────────────────────────────────────────────────

def extract_keywords(text: str, max_kw: int = 12) -> list[str]:
    if not YAKE_OK or not text.strip():
        return []
    kw_extractor = yake.KeywordExtractor(
        lan="en",
        n=2,          # up to bigrams
        dedupLim=0.7,
        top=max_kw,
    )
    results = kw_extractor.extract_keywords(text)
    # YAKE: lower score = more relevant
    return [kw for kw, _ in sorted(results, key=lambda x: x[1])]


# ── GOOGLE TRENDS ─────────────────────────────────────────────────────────────

def get_trends(keywords: list[str], geo: str = "CA-PE") -> dict[str, float]:
    """Return avg interest (0-100) per keyword over last 90 days."""
    if not PYTRENDS_OK or not keywords:
        return {}
    kw_batch = keywords[:5]  # Trends API accepts max 5 at once
    try:
        pt = TrendReq(hl="en-US", tz=240, timeout=(10, 25))
        pt.build_payload(kw_batch, cat=16, timeframe="today 3-m", geo=geo)
        df = pt.interest_over_time()
        if df.empty and geo != "CA":
            pt.build_payload(kw_batch, cat=16, timeframe="today 3-m", geo="CA")
            df = pt.interest_over_time()
        if not df.empty:
            return {k: float(df[k].mean()) for k in kw_batch if k in df.columns}
    except Exception:
        pass
    return {}


# ── LLM HEADLINE GENERATION ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an experienced SEO editor for a community newspaper network in Prince Edward Island (PEI), Canada.
Your papers serve tight-knit communities and compete for local search traffic.
You write clear, honest, compelling headlines — never clickbait.
You understand Google News ranking signals and local search intent."""


def _build_user_prompt(topic: str, summary: str, keywords: list[str], trending: dict, paper: str) -> str:
    kw_str = ", ".join(keywords[:8]) if keywords else topic
    trend_str = ""
    if trending:
        top = sorted(trending.items(), key=lambda x: x[1], reverse=True)[:3]
        trend_str = f"\nCurrently trending on Google in PEI region: {', '.join(t[0] for t in top)}"

    paper_note = f"\nPaper context: {paper}" if paper != "General / All Papers" else ""

    return f"""Generate exactly 6 SEO-optimized web headlines for the following PEI news story.

Topic: {topic}
Summary: {summary}
Extracted key terms: {kw_str}{trend_str}{paper_note}

Rules:
1. Target length: 50–65 characters (absolute maximum 70)
2. Front-load the most important keyword (first 3 words matter most to Google)
3. Be specific — use proper names, dollar amounts, locations, vote counts, etc.
4. Include a PEI local identifier where natural (PEI, Charlottetown, Island, etc.)
5. Use active voice and present/future tense where possible
6. Mix styles across the 6: declarative statement, question, "How to…", numbered list
7. Avoid: vague words ("Things", "Stuff"), passive voice, all-caps, excessive punctuation
8. Optimise for Google News (no SEO-stuffing, no invented facts)

Return ONLY the 6 headlines, one per line, numbered 1–6. No explanations, no extra text."""


def generate_headlines(topic: str, summary: str, keywords: list[str], trending: dict, paper: str, api_key: str) -> list[str]:
    if not api_key:
        return []
    client = Anthropic(api_key=api_key)
    prompt = _build_user_prompt(topic, summary, keywords, trending, paper)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    headlines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r"^\d+[\.\)\-]\s*", "", line).strip()
        if cleaned:
            headlines.append(cleaned)
    return headlines


def generate_meta(topic: str, summary: str, api_key: str) -> str:
    if not api_key:
        return ""
    client = Anthropic(api_key=api_key)
    prompt = f"""Write a single SEO meta description for this news article.

Topic: {topic}
Summary: {summary}

Requirements:
- 150–160 characters maximum
- Include the primary keyword naturally in the first half
- Mention PEI or Island context if relevant
- One or two short sentences; no em-dash or quotes
- Entice clicks without overpromising

Return ONLY the meta description text, nothing else."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def generate_tags(topic: str, summary: str, api_key: str) -> list[str]:
    if not api_key:
        return []
    client = Anthropic(api_key=api_key)
    prompt = f"""Suggest 8 SEO tags/categories for this PEI news article.

Topic: {topic}
Summary: {summary}

Return ONLY the tags as a comma-separated list. Include 2-3 local geographic tags (e.g. PEI, Charlottetown),
2-3 topic tags, and 2-3 broader subject tags. Short and lowercase."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    return [t.strip() for t in raw.split(",") if t.strip()]


# ── UI ─────────────────────────────────────────────────────────────────────────

st.title("📰 PEI News — SEO Headline Generator")
st.caption("Open-source stack: YAKE · PyTrends · Claude AI (Haiku) · Streamlit")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        help="Get yours at console.anthropic.com. The key is never stored.",
        placeholder="sk-ant-…",
    )

    paper = st.selectbox(
        "Select Paper",
        [
            "General / All Papers",
            "Eastern Graphic (Kings County)",
            "Montague / Georgetown area",
            "Summerside / West Prince area",
            "Charlottetown / Queens County area",
        ],
    )

    check_trends = st.toggle("Check Google Trends (PEI region)", value=True)
    gen_meta = st.toggle("Generate meta description", value=True)
    gen_tags = st.toggle("Suggest article tags", value=True)

    st.divider()
    st.markdown("**SEO Score Key**")
    st.markdown("🟢 **80–100** — Excellent")
    st.markdown("🟡 **60–79** — Good")
    st.markdown("🟠 **40–59** — Fair")
    st.markdown("🔴 **0–39** — Needs work")
    st.divider()
    st.markdown("**Open-source tools used**")
    st.markdown("- [YAKE](https://github.com/LIAAD/yake) — keyword extraction")
    st.markdown("- [PyTrends](https://github.com/GeneralMills/pytrends) — Google Trends")
    st.markdown("- [Streamlit](https://streamlit.io) — UI framework")
    st.markdown("- [Claude Haiku](https://anthropic.com) — LLM generation")

# ── Main columns ──────────────────────────────────────────────────────────────
col_in, col_out = st.columns([1, 1.1], gap="large")

with col_in:
    st.subheader("📝 Article Details")

    topic = st.text_input(
        "Topic / Subject Line *",
        placeholder="e.g.  New pedestrian bridge approved for Charlottetown waterfront",
    )

    summary = st.text_area(
        "Article Text or Key Facts *",
        placeholder=(
            "Paste your draft article, lede, or bullet points.\n\n"
            "The more detail you give, the better the headlines.\n\n"
            "Example:\n"
            "• City council voted 7-2 in favour\n"
            "• $2.4M provincial grant announced\n"
            "• Construction starts spring 2026\n"
            "• Located at Victoria Row end"
        ),
        height=220,
    )

    original = st.text_input(
        "Existing Headline to Compare (optional)",
        placeholder="Paste your current working headline here",
    )

    go = st.button(
        "🚀 Generate SEO Headlines",
        type="primary",
        use_container_width=True,
        disabled=(not topic and not summary),
    )

with col_out:
    if go and (topic or summary):
        # ── Step 1: Keywords ──────────────────────────────────────────────
        with st.spinner("Extracting keywords…"):
            keywords = extract_keywords(f"{topic} {summary}")

        if keywords:
            st.subheader("🔑 Keywords Detected")
            st.markdown("  ".join(f"`{kw}`" for kw in keywords[:10]))
        else:
            st.info("YAKE not installed — keyword extraction skipped.")
            keywords = []

        # ── Step 2: Google Trends ─────────────────────────────────────────
        trending = {}
        if check_trends and keywords:
            with st.spinner("Checking Google Trends for PEI region…"):
                trending = get_trends(keywords)
            if trending:
                st.subheader("📈 Google Trends (PEI, last 90 days)")
                for term, val in sorted(trending.items(), key=lambda x: -x[1])[:5]:
                    bar_val = max(int(val), 1)
                    st.progress(bar_val, text=f"{term}  —  {bar_val}/100")
            elif not PYTRENDS_OK:
                st.info("PyTrends not installed — trends check skipped.")

        # ── Step 3: Original headline audit ──────────────────────────────
        if original:
            st.subheader("🔍 Your Existing Headline")
            score, issues, tips = score_headline(original)
            colour, emoji = score_colour(score)
            st.markdown(f"**{emoji} SEO Score: {score}/100**")
            for iss in issues:
                st.markdown(f'<div class="warn">⚠️ {iss}</div>', unsafe_allow_html=True)
            for tip in tips:
                st.markdown(f'<div class="tip">💡 {tip}</div>', unsafe_allow_html=True)
            st.divider()

        # ── Step 4: Generate headlines ────────────────────────────────────
        if not api_key:
            st.warning("⚠️ Enter your Anthropic API key in the sidebar to generate AI headlines.")
        else:
            with st.spinner("Generating 6 SEO-optimized headlines with Claude Haiku…"):
                headlines = generate_headlines(topic, summary, keywords, trending, paper, api_key)

            if headlines:
                st.subheader("✨ Optimized Headlines")
                for i, hl in enumerate(headlines, 1):
                    sc, iss, tps = score_headline(hl)
                    colour, emoji = score_colour(sc)
                    char_count = len(hl)
                    char_ok = "✅" if char_count <= 65 else "⚠️"

                    with st.expander(f"{emoji} {sc}/100  ·  {char_count} chars  ·  {hl}", expanded=(i == 1)):
                        st.code(hl, language=None)
                        st.caption(f"Characters: {char_count}/65 {char_ok}")
                        for iss_item in iss:
                            st.markdown(f'<div class="warn">⚠️ {iss_item}</div>', unsafe_allow_html=True)
                        for tip_item in tps:
                            st.markdown(f'<div class="tip">💡 {tip_item}</div>', unsafe_allow_html=True)

            # ── Step 5: Meta description ──────────────────────────────────
            if gen_meta:
                with st.spinner("Writing meta description…"):
                    meta = generate_meta(topic, summary, api_key)
                if meta:
                    st.subheader("📋 Meta Description")
                    meta_len = len(meta)
                    meta_ok = "✅" if meta_len <= 160 else "⚠️ too long"
                    st.text_area("Copy to CMS:", meta, height=90, key="meta_out")
                    st.caption(f"Characters: {meta_len}/160 {meta_ok}")

            # ── Step 6: Tags ──────────────────────────────────────────────
            if gen_tags:
                with st.spinner("Suggesting tags…"):
                    tags = generate_tags(topic, summary, api_key)
                if tags:
                    st.subheader("🏷️ Suggested Tags / Categories")
                    st.markdown("  ".join(f"`{t}`" for t in tags))

    elif go:
        st.warning("Please enter a topic or article text before generating.")
    else:
        st.info("👈 Fill in your article details and click **Generate SEO Headlines**.")
        st.markdown("""
**What this tool does, step by step:**

1. **Extracts keywords** from your text using YAKE (open-source NLP)
2. **Checks Google Trends** to see what people in PEI are actually searching
3. **Scores your existing headline** against SEO best practices
4. **Generates 6 optimized alternatives** using Claude Haiku
5. **Scores each new headline** and flags issues
6. **Writes a meta description** ready to paste into your CMS
7. **Suggests article tags** for categories and internal linking
        """)

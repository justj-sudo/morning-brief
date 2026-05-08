#!/usr/bin/env python3
"""
Morning Brief Generator
Pulls: Alpaca (market data) + Perplexity (macro/news) → Claude (synthesis) → HTML + PDF
"""

import os
import json
import requests
from datetime import datetime, date
import pytz

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
ALPACA_API_KEY     = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY  = os.environ["ALPACA_SECRET_KEY"]
PERPLEXITY_API_KEY = os.environ["PERPLEXITY_API_KEY"]

ALPACA_BASE   = "https://data.alpaca.markets/v2"
ALPACA_TRADE  = "https://api.alpaca.markets/v2"
ALPACA_HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

ET = pytz.timezone("America/New_York")
TODAY = date.today().strftime("%Y-%m-%d")
NOW   = datetime.now(ET).strftime("%A, %B %d, %Y — %I:%M %p ET")

# ── Macro + Index tickers ─────────────────────────────────────────────────────
INDEX_TICKERS   = ["SPY", "QQQ", "IWM", "XLK"]
MACRO_TICKERS   = ["SPY", "QQQ", "IWM", "XLK", "VIX", "TLT", "UUP", "USO", "BITO"]
SECTOR_ETFS     = ["XLK","XLF","XLE","XLV","XLI","XLY","XLP","XLB","XLU","XLRE","XLC"]
SCREEN_UNIVERSE = [
    # Mega cap
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","JPM","V",
    "MA","UNH","XOM","LLY","JNJ","WMT","PG","HD","MRK","CVX",
    # High-beta / momentum
    "AMD","SMCI","PLTR","IONQ","MSTR","COIN","HOOD","RBLX","UBER","LYFT",
    "SNOW","DDOG","CRWD","ZS","NET","ANET","ARM","ASML","TSM","MU",
    # Sector leaders
    "GS","BAC","MS","C","WFC","XOM","COP","SLB","HAL","OXY",
    "LMT","RTX","NOC","BA","CAT","DE","FCX","NEM","GLD","SLV",
    # ETFs
    "TQQQ","SOXL","ARKK","XBI","IBB","GDX","GDXJ","HYG","TLT","SHY",
    # Mid-cap momentum
    "DUOL","CELH","GLBE","AXON","FTNT","MELI","SHOP","TTD","ENPH","SEDG"
]

# ── Step 1: Alpaca — fetch bars + premarket snapshot ─────────────────────────
def fetch_alpaca_snapshots(tickers: list[str]) -> dict:
    """Fetch latest snapshot (quote, bar, daily change) for a list of tickers."""
    symbols = ",".join(tickers)
    url = f"{ALPACA_BASE}/stocks/snapshots?symbols={symbols}&feed=iex"
    resp = requests.get(url, headers=ALPACA_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()

def fetch_premarket_quotes(tickers: list[str]) -> dict:
    """Fetch latest trade for premarket context."""
    symbols = ",".join(tickers[:50])  # Alpaca limit per call
    url = f"{ALPACA_BASE}/stocks/trades/latest?symbols={symbols}&feed=iex"
    resp = requests.get(url, headers=ALPACA_HEADERS, timeout=20)
    if resp.status_code == 200:
        return resp.json().get("trades", {})
    return {}

def compute_volume_ratio(snapshot: dict) -> float:
    """Relative volume = today's volume vs daily average (approx from prev close data)."""
    try:
        daily  = snapshot.get("dailyBar", {})
        prev   = snapshot.get("prevDailyBar", {})
        vol_today = daily.get("v", 0)
        vol_prev  = prev.get("v", 1)
        return round(vol_today / vol_prev, 2) if vol_prev else 0.0
    except Exception:
        return 0.0

def screen_universe(snapshots: dict) -> list[dict]:
    """Filter universe down to high-conviction candidates."""
    candidates = []
    for ticker, snap in snapshots.items():
        try:
            daily   = snap.get("dailyBar", {})
            prev    = snap.get("prevDailyBar", {})
            quote   = snap.get("latestQuote", {})
            trade   = snap.get("latestTrade", {})

            close   = daily.get("c", 0)
            prev_c  = prev.get("c", 0)
            vol_ratio = compute_volume_ratio(snap)
            pct_chg = round((close - prev_c) / prev_c * 100, 2) if prev_c else 0

            if close < 10:
                continue
            if vol_ratio < 1.2:   # some pre-market data may be low; keep threshold modest
                continue

            candidates.append({
                "ticker":    ticker,
                "price":     round(close, 2),
                "change_pct": pct_chg,
                "vol_ratio": vol_ratio,
                "volume":    daily.get("v", 0),
                "high":      daily.get("h", 0),
                "low":       daily.get("l", 0),
                "open":      daily.get("o", 0),
            })
        except Exception:
            continue

    # Sort by vol_ratio desc, take top 30 for Claude to further filter
    candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    return candidates[:30]

# ── Step 2: Perplexity — macro + catalyst intelligence ───────────────────────
def query_perplexity(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a macro research analyst. Be concise, data-rich, and current. Today is " + NOW},
            {"role": "user",   "content": prompt}
        ],
        "max_tokens": 1200,
    }
    resp = requests.post("https://api.perplexity.ai/chat/completions",
                         headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def gather_macro_intelligence() -> dict:
    """Run targeted Perplexity queries for macro context."""
    print("📡 Querying Perplexity for macro intelligence...")

    macro = query_perplexity(
        "Give me today's macro picture: S&P 500 premarket, VIX level, 10Y Treasury yield, "
        "DXY dollar index, crude oil price, Bitcoin price. Include any overnight catalysts, "
        "Fed commentary, or geopolitical events moving markets right now. Be specific with numbers."
    )

    sectors = query_perplexity(
        "What sectors and ETFs are showing unusual institutional activity, options flow, "
        "or momentum today? Which sectors are leading vs lagging? Any notable dark pool prints "
        "or block trades reported overnight or premarket? Focus on actionable rotation signals."
    )

    catalysts = query_perplexity(
        "List the most important earnings reports, economic data releases, FDA decisions, "
        "M&A news, or analyst upgrades/downgrades moving individual stocks today. "
        "Focus on names with high options activity or premarket volume spikes."
    )

    return {"macro": macro, "sectors": sectors, "catalysts": catalysts}

# ── Step 3: Claude — synthesize into full brief ───────────────────────────────
SYSTEM_PROMPT = """You are an institutional-grade CIO portfolio strategist, options flow and derivatives analyst, sector rotation engine, momentum and swing trading system, and premium income / wheel strategist.

Your purpose is to generate HIGH-CONVICTION, TRADEABLE INTELLIGENCE — not commentary.

Portfolio Context:
- Total capital: $50,000
- Position Trading: 50% | Income Trading: 20% | Wheel/Premium Selling: 30%
- No margin. No naked options.

Risk Rules (NON-NEGOTIABLE):
- Max position size: 8–10% ($4,000–$5,000)
- Max ticker exposure: 10%
- Portfolio risk-off trigger: -6%
- No stocks under $10
- Let winners run | Trim 2.5% for every +8% above +10% gain

VIX Regime Logic: <15=complacent | 15–20=healthy trend | 20–25=caution | 25–30=defensive | 30+=risk-off

OUTPUT FORMAT: Respond in valid JSON only. No markdown. No prose outside JSON.

JSON structure:
{
  "date": "YYYY-MM-DD",
  "generated_at": "time string",
  "regime": "Risk-On | Neutral | Risk-Off",
  "cio_summary": ["bullet1", "bullet2", "bullet3", "bullet4", "bullet5"],
  "macro_dashboard": {
    "spy_trend": "", "qqq_trend": "", "iwm_trend": "", "vix": "", "vix_regime": "",
    "yield_10y": "", "dollar_trend": "", "oil_trend": "", "crypto_sentiment": "",
    "tactical_bias": "Buy Dips | Fade Strength | Neutral"
  },
  "institutional_setups": [
    {"ticker":"","catalyst":"","setup":"","entry":"","stop":"","target":"","conviction":"High|Med|Low"}
  ],
  "watchlist": [
    {"ticker":"","catalyst":"","premarket_action":"","support":"","resistance":"","pattern":"","priority":"1-15"}
  ],
  "position_actions": [
    {"action":"BUY|ADD|HOLD|TRIM|EXIT|HEDGE","ticker":"","reasoning":""}
  ],
  "wheel_book": [
    {"ticker":"","sector":"","iv_rank_est":"","delta":"","dte":"","strike_zone":"","assignment_risk":"Low|Med|High","priority":""}
  ],
  "risk_alerts": ["alert1", "alert2"],
  "cio_verdict": {
    "risk_posture": "Aggressive | Neutral | Defensive",
    "capital_flow": "",
    "avoid": ""
  }
}"""

def generate_brief_with_claude(macro_intel: dict, screened: list[dict], index_snaps: dict) -> dict:
    """Send all data to Claude and get back the structured brief."""
    print("🧠 Sending to Claude for synthesis...")

    # Format index data cleanly
    index_summary = []
    for t in INDEX_TICKERS:
        snap = index_snaps.get(t, {})
        daily = snap.get("dailyBar", {})
        prev  = snap.get("prevDailyBar", {})
        close = daily.get("c", 0)
        prev_c = prev.get("c", 1)
        pct = round((close - prev_c) / prev_c * 100, 2) if prev_c else 0
        index_summary.append(f"{t}: ${close} ({'+' if pct >= 0 else ''}{pct}%)")

    user_message = f"""Today: {NOW}

=== INDEX SNAPSHOT ===
{chr(10).join(index_summary)}

=== MACRO INTELLIGENCE (Perplexity) ===
MACRO/YIELDS/COMMODITIES:
{macro_intel['macro']}

SECTOR ROTATION & FLOW:
{macro_intel['sectors']}

INDIVIDUAL CATALYSTS:
{macro_intel['catalysts']}

=== SCREENED UNIVERSE (Top candidates by relative volume) ===
{json.dumps(screened[:25], indent=2)}

Based on all of the above, generate the complete morning brief JSON. 
- Watchlist: 15 names max, ranked by priority
- Institutional setups: 10–15 names, highest conviction only
- Wheel book: only quality names with good IV and support structure
- Risk alerts: be specific, not generic
- All price levels must be realistic given the data provided"""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}]
    }

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    resp = requests.post("https://api.anthropic.com/v1/messages",
                         headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    raw = resp.json()["content"][0]["text"].strip()

    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)

# ── Step 4: Render HTML ───────────────────────────────────────────────────────
def regime_color(regime: str) -> str:
    return {"Risk-On": "#00c896", "Neutral": "#f0a500", "Risk-Off": "#ff4d4d"}.get(regime, "#aaa")

def conviction_badge(c: str) -> str:
    colors = {"High": "#00c896", "Med": "#f0a500", "Low": "#ff6b6b"}
    return f'<span class="badge" style="background:{colors.get(c,"#555")}">{c}</span>'

def action_badge(a: str) -> str:
    colors = {"BUY":"#00c896","ADD":"#4ecdc4","HOLD":"#a0a0a0","TRIM":"#f0a500","EXIT":"#ff4d4d","HEDGE":"#c792ea"}
    return f'<span class="badge" style="background:{colors.get(a,"#555")}">{a}</span>'

def render_html(brief: dict) -> str:
    md = brief.get("macro_dashboard", {})
    regime = brief.get("regime", "Neutral")
    rc = regime_color(regime)

    # CIO Summary bullets
    summary_html = "".join(f"<li>{b}</li>" for b in brief.get("cio_summary", []))

    # Macro dashboard
    macro_rows = "".join(f"""
        <div class="macro-item">
            <div class="macro-label">{k.replace('_',' ').upper()}</div>
            <div class="macro-value">{v}</div>
        </div>""" for k, v in md.items())

    # Institutional setups table
    setup_rows = "".join(f"""
        <tr>
            <td><strong>{s['ticker']}</strong></td>
            <td>{s['catalyst']}</td>
            <td>{s['setup']}</td>
            <td>{s['entry']}</td>
            <td>{s['stop']}</td>
            <td>{s['target']}</td>
            <td>{conviction_badge(s['conviction'])}</td>
        </tr>""" for s in brief.get("institutional_setups", []))

    # Watchlist table
    watch_rows = "".join(f"""
        <tr>
            <td><strong>#{w['priority']}</strong></td>
            <td><strong>{w['ticker']}</strong></td>
            <td>{w['catalyst']}</td>
            <td>{w['premarket_action']}</td>
            <td>{w['support']}</td>
            <td>{w['resistance']}</td>
            <td>{w['pattern']}</td>
        </tr>""" for w in brief.get("watchlist", []))

    # Position actions
    actions_html = "".join(f"""
        <div class="action-card">
            {action_badge(a['action'])}
            <span class="action-ticker">{a['ticker']}</span>
            <span class="action-reason">{a['reasoning']}</span>
        </div>""" for a in brief.get("position_actions", []))

    # Wheel book
    wheel_rows = "".join(f"""
        <tr>
            <td><strong>{w['ticker']}</strong></td>
            <td>{w['sector']}</td>
            <td>{w['iv_rank_est']}</td>
            <td>{w['delta']}</td>
            <td>{w['dte']}</td>
            <td>{w['strike_zone']}</td>
            <td>{conviction_badge(w['assignment_risk'])}</td>
            <td>{w['priority']}</td>
        </tr>""" for w in brief.get("wheel_book", []))

    # Risk alerts
    risk_html = "".join(f'<div class="risk-alert">⚠️ {r}</div>' for r in brief.get("risk_alerts", []))

    verdict = brief.get("cio_verdict", {})
    posture = verdict.get("risk_posture", "Neutral")
    posture_color = {"Aggressive":"#00c896","Neutral":"#f0a500","Defensive":"#ff4d4d"}.get(posture,"#aaa")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief — {brief.get('date', TODAY)}</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #21262d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; line-height: 1.5; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}

  /* Header */
  .header {{ display: flex; justify-content: space-between; align-items: center;
             border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }}
  .header-left h1 {{ font-size: 22px; font-weight: 700; color: var(--accent); }}
  .header-left .subtitle {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
  .regime-pill {{ padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 13px;
                  background: {rc}22; color: {rc}; border: 1px solid {rc}; }}

  /* Sections */
  .section {{ margin-bottom: 28px; }}
  .section-title {{ font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
                    color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 14px; }}

  /* Cards */
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .summary-list {{ list-style: none; }}
  .summary-list li {{ padding: 6px 0; border-bottom: 1px solid var(--border); color: var(--text); }}
  .summary-list li:last-child {{ border-bottom: none; }}
  .summary-list li::before {{ content: "▸ "; color: var(--accent); }}

  /* Macro grid */
  .macro-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }}
  .macro-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; }}
  .macro-label {{ font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
  .macro-value {{ font-size: 13px; font-weight: 600; color: var(--text); }}

  /* Tables */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: var(--border); color: var(--muted); font-size: 10px; letter-spacing: 1px;
        text-transform: uppercase; padding: 8px 12px; text-align: left; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover td {{ background: #ffffff08; }}

  /* Badges */
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; color: #fff; }}

  /* Actions */
  .action-card {{ display: flex; align-items: flex-start; gap: 10px; padding: 10px;
                  border-bottom: 1px solid var(--border); }}
  .action-card:last-child {{ border-bottom: none; }}
  .action-ticker {{ font-weight: 700; min-width: 60px; color: var(--accent); }}
  .action-reason {{ color: var(--muted); font-size: 13px; }}

  /* Risk */
  .risk-alert {{ background: #ff4d4d18; border-left: 3px solid #ff4d4d; padding: 8px 12px;
                 margin-bottom: 8px; border-radius: 0 4px 4px 0; font-size: 13px; }}

  /* Verdict */
  .verdict-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  .verdict-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }}
  .verdict-label {{ font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }}
  .verdict-value {{ font-size: 13px; color: var(--text); }}
  .posture-value {{ font-size: 18px; font-weight: 700; color: {posture_color}; }}

  /* Two-col layout */
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} .verdict-grid {{ grid-template-columns: 1fr; }} }}

  /* Print */
  @media print {{ body {{ background: white; color: black; }} .card, .macro-item {{ border: 1px solid #ccc; }} }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1>🦉 Morning Brief</h1>
      <div class="subtitle">{brief.get('generated_at', NOW)} &nbsp;·&nbsp; $50,000 Portfolio</div>
    </div>
    <div class="regime-pill">{regime}</div>
  </div>

  <!-- CIO Summary + Macro Dashboard side by side -->
  <div class="two-col">
    <div class="section">
      <div class="section-title">CIO Executive Summary</div>
      <div class="card"><ul class="summary-list">{summary_html}</ul></div>
    </div>
    <div class="section">
      <div class="section-title">Macro Dashboard</div>
      <div class="macro-grid">{macro_rows}</div>
    </div>
  </div>

  <!-- Institutional Setups -->
  <div class="section">
    <div class="section-title">Top Institutional Setups</div>
    <div class="card table-wrap">
      <table>
        <thead><tr><th>Ticker</th><th>Catalyst</th><th>Setup</th><th>Entry</th><th>Stop</th><th>Target</th><th>Conviction</th></tr></thead>
        <tbody>{setup_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Dynamic Watchlist -->
  <div class="section">
    <div class="section-title">Dynamic Watchlist — Today's Scan</div>
    <div class="card table-wrap">
      <table>
        <thead><tr><th>#</th><th>Ticker</th><th>Catalyst</th><th>Premarket Action</th><th>Support</th><th>Resistance</th><th>Pattern</th></tr></thead>
        <tbody>{watch_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Position Actions + Wheel Book -->
  <div class="two-col">
    <div class="section">
      <div class="section-title">Position Book Actions</div>
      <div class="card">{actions_html}</div>
    </div>
    <div class="section">
      <div class="section-title">Wheel / Premium Selling Book</div>
      <div class="card table-wrap">
        <table>
          <thead><tr><th>Ticker</th><th>Sector</th><th>IV Rank</th><th>Delta</th><th>DTE</th><th>Strike</th><th>Assign Risk</th><th>Priority</th></tr></thead>
          <tbody>{wheel_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Risk Alerts -->
  <div class="section">
    <div class="section-title">Risk Alerts</div>
    {risk_html}
  </div>

  <!-- CIO Verdict -->
  <div class="section">
    <div class="section-title">Final CIO Verdict</div>
    <div class="verdict-grid">
      <div class="verdict-item">
        <div class="verdict-label">Risk Posture</div>
        <div class="posture-value">{posture}</div>
      </div>
      <div class="verdict-item">
        <div class="verdict-label">Capital Should Flow To</div>
        <div class="verdict-value">{verdict.get('capital_flow','')}</div>
      </div>
      <div class="verdict-item">
        <div class="verdict-label">Avoid Completely</div>
        <div class="verdict-value">{verdict.get('avoid','')}</div>
      </div>
    </div>
  </div>

</div>
</body>
</html>"""

# ── Step 5: Save PDF ──────────────────────────────────────────────────────────
def save_pdf(html_path: str, pdf_path: str):
    """Convert HTML to PDF using weasyprint if available, else skip."""
    try:
        from weasyprint import HTML
        HTML(filename=html_path).write_pdf(pdf_path)
        print(f"📄 PDF saved: {pdf_path}")
    except ImportError:
        print("⚠️  weasyprint not installed — skipping PDF. Run: pip install weasyprint")
    except Exception as e:
        print(f"⚠️  PDF generation failed: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🌅 Morning Brief Generator — {NOW}\n")

    # 1. Fetch market data
    print("📊 Fetching Alpaca market data...")
    all_tickers = list(set(SCREEN_UNIVERSE + INDEX_TICKERS + SECTOR_ETFS + MACRO_TICKERS))
    snapshots = fetch_alpaca_snapshots(all_tickers)

    index_snaps  = {t: snapshots.get(t, {}) for t in INDEX_TICKERS + MACRO_TICKERS}
    screened     = screen_universe({t: snapshots.get(t, {}) for t in SCREEN_UNIVERSE})
    print(f"   → {len(screened)} candidates passed volume screen")

    # 2. Macro intelligence
    macro_intel = gather_macro_intelligence()

    # 3. Claude synthesis
    brief = generate_brief_with_claude(macro_intel, screened, index_snaps)
    brief["date"]         = TODAY
    brief["generated_at"] = NOW

    # 4. Render & save
    os.makedirs("output", exist_ok=True)
    html_path = f"output/brief_{TODAY}.html"
    pdf_path  = f"output/brief_{TODAY}.pdf"
    index_path = "output/index.html"   # always overwrite for GitHub Pages

    html_content = render_html(brief)

    with open(html_path,  "w") as f: f.write(html_content)
    with open(index_path, "w") as f: f.write(html_content)  # GitHub Pages root

    with open(f"output/brief_{TODAY}.json", "w") as f:
        json.dump(brief, f, indent=2)

    save_pdf(html_path, pdf_path)

    print(f"\n✅ Brief saved:")
    print(f"   HTML  → {html_path}")
    print(f"   Index → {index_path}")
    print(f"   JSON  → output/brief_{TODAY}.json")
    print(f"\n🦉 Regime: {brief.get('regime')} | Posture: {brief.get('cio_verdict',{}).get('risk_posture')}\n")

if __name__ == "__main__":
    main()

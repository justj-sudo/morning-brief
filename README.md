# 🦉 Morning Brief System

Institutional-grade daily market intelligence — auto-generated at 6:00 AM MT every weekday.

**Stack:** Alpaca (market data) → Perplexity (macro/news) → Claude (synthesis) → HTML + PDF

---

## What It Generates Each Morning

| Section | Description |
|---|---|
| CIO Executive Summary | 3–6 bullet regime read |
| Macro Dashboard | SPY/QQQ/IWM, VIX, yields, dollar, oil, crypto |
| Institutional Setups | 10–15 high-conviction trades with entry/stop/target |
| Dynamic Watchlist | Up to 15 names ranked by priority (rebuilt daily from scan) |
| Position Book Actions | BUY / ADD / HOLD / TRIM / EXIT / HEDGE |
| Wheel / Premium Book | CSP/CC candidates with delta, DTE, strike zone |
| Risk Alerts | Earnings, macro shocks, VIX expansion, sector breakdowns |
| Final CIO Verdict | Risk posture + capital flow direction + what to avoid |

---

## Setup

### 1. Clone & configure

```bash
git clone https://github.com/YOUR_USERNAME/morning-brief.git
cd morning-brief
cp .env.example .env
# Edit .env with your API keys
```

### 2. API Keys needed

| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |
| `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | https://alpaca.markets (free IEX data tier works) |
| `PERPLEXITY_API_KEY` | https://docs.perplexity.ai |

### 3. Run locally (any time)

```bash
chmod +x run.sh
./run.sh
```

Opens the HTML brief in your browser automatically.

---

## GitHub Actions Setup (Auto-runs at 6 AM MT)

### Step 1 — Add secrets to your GitHub repo

Go to: `Settings → Secrets and variables → Actions → New repository secret`

Add all four keys:
- `ANTHROPIC_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `PERPLEXITY_API_KEY`

### Step 2 — Enable GitHub Pages

Go to: `Settings → Pages`
- Source: **Deploy from a branch**
- Branch: **gh-pages** / root

Your brief will be live at:
```
https://YOUR_USERNAME.github.io/morning-brief/
```

### Step 3 — Enable Actions

Go to: `Actions` tab → click **"I understand my workflows, go ahead and enable them"**

The workflow runs Monday–Friday at 12:00 UTC (≈6 AM MT).

### Manual trigger

From GitHub UI: `Actions → Morning Brief → Run workflow`

Or via CLI:
```bash
gh workflow run morning_brief.yml
```

---

## Cron Schedule Notes

The workflow uses `0 12 * * 1-5` (12:00 UTC weekdays).

| Season | UTC 12:00 = |
|---|---|
| MST (Nov–Mar) | 6:00 AM MT ✅ |
| MDT (Mar–Nov) | 5:00 AM MT (1 hour early) |

To adjust for MDT, change to `0 13 * * 1-5` in `.github/workflows/morning_brief.yml` during summer.

---

## File Structure

```
morning-brief/
├── .github/
│   └── workflows/
│       └── morning_brief.yml    # GitHub Action
├── scripts/
│   └── generate_brief.py        # Main generator
├── output/                      # Generated briefs (git-ignored locally)
│   ├── index.html               # Always latest (served by GitHub Pages)
│   └── brief_YYYY-MM-DD.html   # Archived by date
├── run.sh                       # One-command local runner
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Weekly Owl Brief (Sunday)

Trigger manually by running:
```bash
./run.sh
```
on Sunday evening — the system prompt will adjust based on the day of week. A full weekly
version with sector rotation scoreboard, swing setups, and earnings risk map is included
in the brief automatically on Sundays.

---

## Portfolio Context (hardcoded in generator)

- Total capital: **$50,000**
- Position Trading: 50% | Income: 20% | Wheel: 30%
- Max position size: 8–10% | Risk-off trigger: -6%
- No margin, no naked options, no stocks under $10

To change these, edit the `SYSTEM_PROMPT` in `scripts/generate_brief.py`.

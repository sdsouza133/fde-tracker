# fde-tracker

A daily outreach list for part-time AI evals and testing contracts. Every morning the Railway service picks 10 startups: 8 in the US and 2 in Canada. Canadian clients are flagged because a study permit caps that work at 24 h/week during term.

For each company, Apollo supplies:

- **The 3 best people to pitch:** founders, CTO or engineering head, AI lead, deployment or solutions lead, QA lead. Each comes with their LinkedIn URL, email, and a line on why them.
- **Intel for the pitch:** funding stage and recency, headcount and 6-month growth, engineering team size, open roles that fit (FDE, solutions, QA, evals), stack overlap with hers, and recent news.
- **A short draft note** to edit before sending.

## How it runs

Everything runs in one Railway service, deployed from `main` by `railway.json`. The start command is `python server.py --host 0.0.0.0`, with a health check on `/healthz`.

- **Web:** `server.py` serves the page.
- **Daily job:** a background thread runs `scripts/daily.py` at 07:00 Toronto time (`DAILY_HOUR`), and once at startup if today's list is missing. A failed run is retried an hour later, up to 3 tries a day.
- **Storage:** day files, `TRACKER.md` and the list of companies already shown live on a Railway volume, mounted at `TRACKER_DATA_DIR`. Contact data stays out of this public repo, and redeploys keep it.
- **Statuses:** a person's status lives in each browser's local storage, so it doesn't sync between devices.

## Railway variables

| Variable | Value | Notes |
|---|---|---|
| `APOLLO_API_KEY` | your Apollo API key | Apollo → Settings → Integrations → API. The daily job stays off until it's set. |
| `TRACKER_DATA_DIR` | the volume's mount path, e.g. `/data` | Required for the daily job. |
| `TRACKER_PASSWORD` | optional, 12+ characters | Unset means the site is **public**: anyone with the address sees every contact, emails included, though search engines are told not to index it. |
| `DAILY_HOUR` | optional, default `7` | Toronto local hour for the daily run. |

## Credits

A normal day uses roughly 60 Apollo credits:

- 10 organization enrichments (1 each)
- 10 job-posting pages and 10 news-search pages (1 per page)
- About 30 people reveals through `people/bulk_match` (1 or more each)

Once the hand-picked list runs out, each discovery page costs 1 more credit. People search doesn't use credits. `people_per_company` in `config/profile.json` sets the reveal count.

If an Apollo request fails, the run stops without writing anything and is retried later. If there aren't enough companies left to fill a country's quota, the day is marked "short" on the page.

## Budget filter

She needs at least $3,000 USD a month. A company is only listed if Apollo's data shows it can pay that. Any one of these is enough:

- **Funding:** $1M+ raised in total, with the last round within 4 years.
- **Revenue:** $500K+ in annual revenue.
- **Payroll:** 10+ employees.

Unknown data counts as no. A company that fails is skipped right after its 1-credit enrichment, before people, jobs and news, and its reason is listed under "Skipped" on the page. Apollo discovery also asks only for companies with $1M+ in total funding. Thresholds are under `budget` in `config/profile.json`.

## Changing who gets picked

- **`config/targets.json`:** hand-picked companies, shown first, in order. Each has a `country` (`US`/`CA`) and an `angle`, which is the "why her" line.
- **`config/profile.json`:** her proof points, the daily US/CA mix, which titles to pitch and in what priority, and the Apollo company filters used to find new companies once the hand-picked list runs out.
- **`state.json` on the volume:** companies already shown, so nobody repeats.

## Run locally

```bash
python scripts/daily.py --mock                                   # canned data into docs/data, no key needed
TRACKER_DATA_DIR=./local-data TRACKER_MOCK=1 python server.py    # page + daily job on mock data, http://127.0.0.1:8080
```

# fde-tracker

A daily outreach list for part-time AI evals and testing contracts. Every morning a GitHub Action picks 10 startups: 8 in the US and 2 in Canada. Canadian clients are flagged because a study permit caps that work at 24 h/week during term.

For each company, Apollo supplies:

- **The 3 best people to pitch:** founders, CTO or engineering head, AI lead, deployment or solutions lead, QA lead. Each comes with their LinkedIn URL, email, and a line on why them.
- **Intel for the pitch:** funding stage and recency, headcount and 6-month growth, engineering team size, open roles that fit (FDE, solutions, QA, evals), stack overlap with hers, and recent news.
- **A short draft note** to edit before sending.

## Where to read it

- **`TRACKER.md`:** today's list, rendered by GitHub.
- **`docs/index.html`:** an interactive view with a day picker, US/Canada filter, and a status per person (To contact → Connection sent → … → Call booked). Statuses are kept in your browser only. To use it, open the file from a local clone (`python -m http.server -d docs`), or turn on GitHub Pages if your plan allows Pages for private repos.
- **`docs/data/days/`:** one JSON file per day.

## Setup

1. **Make the repo private.** The output contains people's names and emails, so the workflow refuses to run in a public repo. Go to Settings → General → Danger Zone → Change visibility.
2. **Add your Apollo API key.** Create it in Apollo under Settings → Integrations → API. Then in GitHub, go to Settings → Secrets and variables → Actions → New repository secret, named `APOLLO_API_KEY`.
3. **Run it.** Go to Actions → Daily outreach list → Run workflow. After that it runs every day at 07:00 Eastern.

## Credits

Each day uses about 10 organization enrichments plus about 30 email reveals through `people/bulk_match`, so roughly 40 Apollo credits. People search, job postings and news searches don't reveal contact data. `people_per_company` in `config/profile.json` sets the reveal count.

## Changing who gets picked

- **`config/targets.json`:** hand-picked companies, shown first, in order. Each has a `country` (`US`/`CA`) and an `angle`, which is the "why her" line.
- **`config/profile.json`:** her proof points, the daily US/CA mix, which titles to pitch and in what priority, and the Apollo company filters used to find new companies once the hand-picked list runs out.
- **`state/state.json`:** companies already shown, so nobody repeats. Delete a domain from `shown` to show that company again.

## Run locally

```bash
python scripts/daily.py --mock            # canned data, no key needed
APOLLO_API_KEY=... python scripts/daily.py
```

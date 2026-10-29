"""Pick today's 10 companies, find who to pitch at each through Apollo, and write the tracker data.

Run: APOLLO_API_KEY=... python scripts/daily.py [--date YYYY-MM-DD] [--mock]
On Railway, server.py runs this every morning and TRACKER_DATA_DIR points at the service's volume,
so contact data never lands in the repo. Without it, output goes into docs/data and state/.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
OUT = os.environ.get("TRACKER_DATA_DIR")
DATA = Path(OUT) / "data" if OUT else ROOT / "docs" / "data"
STATE = Path(OUT) / "state.json" if OUT else ROOT / "state" / "state.json"
TRACKER_MD = Path(OUT) / "TRACKER.md" if OUT else ROOT / "TRACKER.md"
API = "https://api.apollo.io/api/v1"
MAX_DISCOVERY_PAGES = 50


class ApolloError(Exception):
    """A request Apollo refused or that kept failing; the run stops without writing anything."""


def arrays(filters):
    """Apollo's search endpoints take list filters as repeated `name[]` query parameters."""
    return {f"{k}[]" if isinstance(v, list) else k: v for k, v in filters.items()}


class Apollo:
    def __init__(self, key):
        self.key = key

    def _req(self, method, path, params=None, body=None):
        """Return the parsed answer; {} only for 404 (nothing known). Anything else that fails raises."""
        url = f"{API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "X-Api-Key": self.key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        })
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return {}
                last = f"{e.code}: {e.read()[:200]!r}"
                if e.code != 429 and e.code < 500:
                    break
            except urllib.error.URLError as e:
                last = str(e)
            time.sleep(5 * (attempt + 1))
        raise ApolloError(f"{method} {path} -> {last}")

    def enrich_org(self, domain):
        return self._req("GET", "/organizations/enrich", {"domain": domain}).get("organization") or {}

    def job_postings(self, org_id):
        return self._req("GET", f"/organizations/{org_id}/job_postings", {"per_page": 50}).get("organization_job_postings") or []

    def news(self, org_id):
        params = arrays({"organization_ids": [org_id], "per_page": 5})
        return self._req("POST", "/news_articles/search", params).get("news_articles") or []

    def search_people(self, domain, titles):
        params = arrays({"q_organization_domains_list": [domain], "person_titles": titles, "per_page": 25})
        return self._req("POST", "/mixed_people/api_search", params).get("people") or []

    def reveal(self, ids):
        if not ids:
            return []
        body = {"details": [{"id": i} for i in ids]}
        return self._req("POST", "/people/bulk_match", {"reveal_personal_emails": "false"}, body).get("matches") or []

    def search_companies(self, filters, page):
        params = arrays(dict(filters, page=page, per_page=25))
        return self._req("POST", "/mixed_companies/search", params).get("organizations") or []


class MockApollo(Apollo):
    """Offline stand-in with Apollo-shaped answers, for testing the pipeline and the page."""

    def __init__(self):
        super().__init__("mock")

    def enrich_org(self, domain):
        if domain in os.environ.get("MOCK_BROKE", "").split(","):  # a company that can't afford her
            return {"id": f"org-{domain}", "name": domain.split(".")[0].title(), "estimated_num_employees": 3,
                    "total_funding": 150000, "latest_funding_round_date": "2025-07-01"}
        return {"id": f"org-{domain}", "name": domain.split(".")[0].title(), "primary_domain": domain,
                "estimated_num_employees": 12, "organization_headcount_six_month_growth": 0.25,
                "total_funding": 6000000, "total_funding_printed": "6M", "latest_funding_stage": "Seed",
                "latest_funding_round_date": "2026-03-01", "founded_year": 2024, "city": "New York",
                "country": "United States", "short_description": f"{domain} builds AI agents.",
                "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                "departmental_head_count": {"engineering": 4, "sales": 2},
                "current_technologies": [{"name": "Python"}, {"name": "Node.js"}, {"name": "Azure"}]}

    def job_postings(self, org_id):
        return [{"title": "Forward Deployed Engineer", "url": "https://example.com/job/1", "posted_at": "2026-10-20"},
                {"title": "Account Executive", "url": "https://example.com/job/2", "posted_at": "2026-10-18"}]

    def news(self, org_id):
        return [{"title": "Startup raises seed round to make AI agents safe", "url": "https://example.com/news", "published_at": "2026-09-30"}]

    def search_people(self, domain, titles):
        if domain in os.environ.get("MOCK_FAIL", "").split(","):
            raise ApolloError(f"mock failure for {domain}")
        if domain in os.environ.get("MOCK_NOBODY", "").split(","):
            return []
        return [{"id": f"{domain}-1", "first_name": "Ada", "last_name_obfuscated": "L***", "title": "Co-Founder & CEO"},
                {"id": f"{domain}-2", "first_name": "Grace", "last_name_obfuscated": "H***", "title": "CTO"},
                {"id": f"{domain}-3", "first_name": "Alan", "last_name_obfuscated": "T***", "title": "Account Executive"},
                {"id": f"{domain}-4", "first_name": "Kat", "last_name_obfuscated": "J***", "title": "Head of AI"}]

    def reveal(self, ids):
        out = []
        for i in ids:
            first = {"1": "Ada", "2": "Grace", "4": "Kat"}.get(i[-1], "X")
            out.append({"id": i, "name": f"{first} Example", "first_name": first,
                        "email": f"{first.lower()}@{i.rsplit('-', 1)[0]}", "email_status": "verified",
                        "linkedin_url": f"https://www.linkedin.com/in/{first.lower()}-example"})
        return out

    def search_companies(self, filters, page):
        if page > int(os.environ.get("MOCK_PAGES", "50")):
            return []
        tag = filters["organization_locations"][0][:2].lower()
        return [{"primary_domain": f"found-{tag}{page}-{n}.ai", "name": f"Found {tag}{page}-{n}"} for n in range(3)]


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_text(path, text):
    """Write via a temp file and rename, so a crash never leaves a half-written file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_json(path, obj):
    save_text(path, json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def role_for(title, profile):
    t = (title or "").lower()
    for rule in profile["role_priority"]:
        if any(m in t for m in rule["match"]):
            return rule["weight"], rule["why"]
    return 0, None


def discover(country, profile, state, apollo, seen):
    """Pull the next Apollo search page into the country's backlog. Returns the new entries; [] once exhausted."""
    page = state["discovery_page"].get(country, 0) + 1
    if page > MAX_DISCOVERY_PAGES:
        return []
    orgs = apollo.search_companies(profile["discovery"][country], page)
    if not orgs:
        return []  # exhausted: leave the saved page where it is
    state["discovery_page"][country] = page
    new = []
    for org in orgs:
        d = org.get("primary_domain")
        if d and d not in seen:
            seen.add(d)
            new.append({"domain": d, "name": org.get("name") or d, "country": country, "angle": None})
    state["backlog"].setdefault(country, []).extend(new)  # kept for later days if today doesn't need it
    return new or [None]  # a page of known companies still isn't the end of the search


def select(profile, targets, state, apollo, today):
    """Fill each country's quota with companies that have someone to pitch, discovering more as needed."""
    state.setdefault("discovery_page", {})
    state.setdefault("backlog", {})
    for country in profile["daily_mix"]:  # a saved page only means something for the filters that produced it
        key = json.dumps(profile["discovery"][country], sort_keys=True)
        if state.setdefault("discovery_filters", {}).get(country) != key:
            state["discovery_page"][country] = 0
            state["discovery_filters"][country] = key
            state["backlog"][country] = []  # found under the old filters
    shown = set(state["shown"])
    seen = set(shown)
    queues = {}
    for country in profile["daily_mix"]:  # build every queue first so countries can't claim each other's companies
        backlog = [b for b in state["backlog"].get(country, []) if b["domain"] not in shown]
        state["backlog"][country] = backlog
        q = [t for t in targets if t["country"] == country and t["domain"] not in seen] + backlog
        seen |= {t["domain"] for t in q}
        queues[country] = deque(q)

    companies, unmet, skipped = [], [], []
    for country, n in profile["daily_mix"].items():
        queue, got = queues[country], 0
        while got < n:
            if not queue:
                new = discover(country, profile, state, apollo, seen)
                if not new:
                    break
                queue.extend(t for t in new if t)
                continue
            t = queue.popleft()
            if t["domain"] in shown:
                continue
            print(f"[{country}] {t['domain']}")
            c = build_company(t, apollo, profile, today)
            shown.add(t["domain"])
            state["shown"].append(t["domain"])  # never retry a company with nobody to pitch
            if c["people"]:
                companies.append(c)
                got += 1
            elif c.get("skipped"):
                skipped.append({"domain": c["domain"], "name": c["name"], "country": country, "reason": c["skipped"]})
        if got < n:
            unmet.append(f"{country}: {got} of {n} (no more companies to try)")
    return companies, unmet, skipped


def money(n):
    return f"${n / 1e6:.1f}M" if n >= 1e6 else f"${n / 1e3:.0f}K"


def budget(org, profile, today):
    """Can the company pay her min_monthly_usd? (ok, reason). Unknown data counts as no."""
    b = profile["budget"]
    pay = f"${b['min_monthly_usd']:,}/month"
    funding = org.get("total_funding") or 0
    revenue = org.get("annual_revenue") or 0
    size = org.get("estimated_num_employees") or 0
    when = org.get("latest_funding_round_date")
    recent = when and (today - dt.date.fromisoformat(when[:10])).days <= b["max_funding_age_years"] * 365
    if funding >= b["min_total_funding"] and recent:
        return True, f"{money(funding)} raised, last round {when[:10]}: {pay} is easily covered"
    if revenue >= b["min_annual_revenue"]:
        return True, f"~{money(revenue)} annual revenue: {pay} is easily covered"
    if size >= b["min_employees"]:
        return True, f"~{size} people on payroll: {pay} is within budget"
    seen = [x for x in (funding and f"{money(funding)} raised" + ("" if recent else " (no recent round)"),
                        revenue and f"{money(revenue)} revenue", size and f"{size} {'person' if size == 1 else 'people'}") if x]
    return False, f"can't confirm budget for {pay}: " + (", ".join(seen) if seen else "no funding, revenue or headcount data")


def intel(org, jobs, news, profile, today):
    out = []
    stage, total, when = org.get("latest_funding_stage"), org.get("total_funding_printed"), org.get("latest_funding_round_date")
    if stage or total:
        line = f"Funding: {stage or 'round'}" + (f", ${total} total" if total else "") + (f", last round {when[:10]}" if when else "")
        if when and (today - dt.date.fromisoformat(when[:10])).days <= 365:
            line += ". Fresh money in the last year, so there is budget for contractors"
        out.append(line)
    growth = org.get("organization_headcount_six_month_growth")
    size = org.get("estimated_num_employees")
    if size:
        g = f", {growth:+.0%} in 6 months" if isinstance(growth, (int, float)) else ""
        out.append(f"Team: ~{size} people{g}" + (". Growing fast; a contractor bridges hiring gaps" if isinstance(growth, (int, float)) and growth >= 0.15 else ""))
    eng = (org.get("departmental_head_count") or {}).get("engineering")
    if eng is not None and eng <= 8:
        out.append(f"Engineering team of {eng}: a part-time evaluator adds testing capacity without a full-time hire")
    kws = profile["relevant_job_keywords"]
    rel = [j for j in jobs if any(k in (j.get("title") or "").lower() for k in kws)]
    if rel:
        fde = any("forward deployed" in (j.get("title") or "").lower() or "fde" in (j.get("title") or "").lower() for j in rel)
        roles = "; ".join((j.get("title") or "") for j in rel[:4])
        out.append(f"Open roles that fit: {roles}" + (". They are hiring an FDE: pitch a contract that covers the gap while they search" if fde else ""))
    elif jobs:
        out.append(f"{len(jobs)} open role{'' if len(jobs) == 1 else 's'}, none in testing or deployment yet: pitch her as the first person to own evals")
    techs = [t.get("name") for t in org.get("current_technologies") or [] if t.get("name")] or org.get("technology_names") or []
    overlap = sorted({t for t in techs if any(s == t.lower() or s in t.lower().split() for s in profile["her_stack"])})
    if overlap:
        out.append(f"Stack overlap with hers: {', '.join(overlap[:6])}")
    for a in news[:2]:
        out.append(f"News ({(a.get('published_at') or '')[:10]}): {a.get('title')}")
    return out, [{"title": j.get("title"), "url": j.get("url"), "posted": (j.get("posted_at") or "")[:10]} for j in rel[:6]]


def opener(org_name):
    return (f"Hi {{first}}, I'm finishing an MS in AI safety at uOttawa after 3 years as an engineer at Marsh McLennan, "
            f"where I also tested Mercer's billing system. I'd like to help {org_name} as a part-time remote contractor "
            f"on evals and pre-launch testing of your AI. Open to a 15-minute chat?")


def build_company(t, apollo, profile, today):
    org = apollo.enrich_org(t["domain"])
    ok, why_budget = budget(org, profile, today)
    if not ok:  # stop before people, jobs and news: no credits spent on a company that can't pay
        print(f"  skip: {why_budget}")
        return {"domain": t["domain"], "name": org.get("name") or t["name"], "people": [], "skipped": why_budget}
    org_id = org.get("id")
    jobs = apollo.job_postings(org_id) if org_id else []
    news = apollo.news(org_id) if org_id else []
    candidates = []
    for p in apollo.search_people(t["domain"], profile["person_titles"]):
        w, why = role_for(p.get("title"), profile)
        if w:
            candidates.append((w, why, p))
    candidates.sort(key=lambda c: -c[0])
    top = candidates[: profile["people_per_company"]]
    revealed = {m.get("id"): m for m in apollo.reveal([c[2]["id"] for c in top]) if m}
    people = []
    for w, why, p in top:
        m = revealed.get(p["id"], {})
        people.append({
            "name": m.get("name") or f"{p.get('first_name', '')} {p.get('last_name_obfuscated', '')}".strip(),
            "title": p.get("title"),
            "apollo_id": p.get("id"),
            "linkedin": m.get("linkedin_url"),
            "email": m.get("email"),
            "email_status": m.get("email_status"),
            "why": why,
        })
    angle = t.get("angle") or org.get("short_description")
    bullets, roles = intel(org, jobs, news, profile, today)
    bullets.insert(0, f"Budget: {why_budget}")
    name = org.get("name") or t["name"]
    return {
        "domain": t["domain"],
        "name": name,
        "country": t["country"],
        "flag": profile["ca_flag"] if t["country"] == "CA" else None,
        "location": ", ".join(x for x in [org.get("city"), org.get("country")] if x),
        "linkedin": org.get("linkedin_url"),
        "description": org.get("short_description"),
        "angle": angle,
        "intel": bullets,
        "roles": roles,
        "people": people,
        "opener": opener(name),
    }


def markdown(day):
    """TRACKER.md: the latest day as a page GitHub renders, so a private repo needs no Pages site."""
    md = [f"# FDE outreach: {day['date']}", "",
          "Ten companies a day. US first; Canadian clients are capped at 24 h/week during term. "
          "Older days are in `docs/data/days/`; `docs/index.html` is the interactive view.", ""]
    if day.get("unmet"):
        md += [f"> **Short today:** {'; '.join(day['unmet'])}. Add companies to `config/targets.json` "
               "or widen `discovery` in `config/profile.json`.", ""]
    for country, label in (("US", "United States"), ("CA", "Canada (24 h/week cap)")):
        group = [c for c in day["companies"] if c["country"] == country]
        if not group:
            continue
        md += [f"## {label}", ""]
        for c in group:
            md += [f"### {c['name']} ({c['domain']})", ""]
            if c.get("angle"):
                md.append(f"**Why her:** {c['angle']}")
            md += [f"- {i}" for i in c.get("intel", [])]
            md += ["", "| Person | LinkedIn | Email | Why them |", "|---|---|---|---|"]
            for p in c["people"]:
                email = p.get("email") or "—"
                if p.get("email") and p.get("email_status") not in (None, "verified"):
                    email += f" ({p['email_status']})"
                li = f"[profile]({p['linkedin']})" if p.get("linkedin") else "—"
                md.append(f"| {p['name']}, {p.get('title') or ''} | {li} | {email} | {p['why']} |")
            md += ["", f"> {c['opener']}", ""]
    if day.get("skipped"):
        md += ["## Skipped: budget", ""] + [f"- {s['name']} ({s['domain']}): {s['reason']}" for s in day["skipped"]] + [""]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--mock", action="store_true", help="use canned Apollo answers, no API key needed")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.date)

    if args.mock:
        apollo = MockApollo()
    else:
        key = os.environ.get("APOLLO_API_KEY")
        if not key:
            sys.exit("APOLLO_API_KEY is not set")
        apollo = Apollo(key)

    profile = load_json(CONFIG / "profile.json", {})
    targets = load_json(CONFIG / "targets.json", [])
    state = load_json(STATE, {"shown": []})
    day_file = DATA / "days" / f"{args.date}.json"
    index = load_json(DATA / "index.json", {"days": []})
    if args.date in index["days"]:  # the index entry is written last, so it marks a finished run
        print(f"{args.date} already done; nothing to do")
        return

    if day_file.exists():  # an earlier run died after saving the day: finish it, no new Apollo calls
        day = load_json(day_file, {})
        print(f"finishing interrupted run for {args.date}")
    else:
        try:
            companies, unmet, skipped = select(profile, targets, state, apollo, today)
        except ApolloError as e:
            sys.exit(f"Apollo request failed, nothing written so the run can be retried: {e}")
        for u in unmet:
            print(f"quota not met, {u}", file=sys.stderr)
        day = {"date": args.date, "companies": companies, "unmet": unmet, "skipped": skipped}
        save_json(STATE, state)  # before the day file, so a finished day never repeats its companies
        save_json(day_file, day)

    save_text(TRACKER_MD, markdown(day) + "\n")
    index["days"] = sorted(set(index["days"]) | {args.date}, reverse=True)
    save_json(DATA / "index.json", index)
    print(f"wrote {day_file}: {len(day['companies'])} companies, "
          f"{sum(len(c['people']) for c in day['companies'])} people")


if __name__ == "__main__":
    main()

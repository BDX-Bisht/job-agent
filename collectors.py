"""Fetch jobs from public ATS job-board APIs (Greenhouse, Lever, Ashby)."""
import csv
import html
import re
import time
from datetime import datetime, timezone

import httpx

HEADERS = {"User-Agent": "personal-job-agent/1.0 (+personal use)"}
TIMEOUT = 25


def _iso(v):
    """Normalise a timestamp (ISO string or epoch ms) to UTC ISO; None if unknown."""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)):
            dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OSError):
        return None


def _text(raw):
    raw = html.unescape(raw or "")
    raw = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(raw)).strip()


def fetch_greenhouse(client, name, slug):
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "company": name, "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""), "apply_url": j.get("absolute_url", ""),
            # updated_at is NOT a posting date, so only first_published is trusted.
            "posted_at": _iso(j.get("first_published")),
            "description": _text(j.get("content")), "source": "greenhouse",
        })
    return out


def fetch_lever(client, name, slug):
    r = client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    r.raise_for_status()
    out = []
    for j in r.json():
        out.append({
            "company": name, "title": j.get("text", ""),
            "location": (j.get("categories") or {}).get("location", "") or "",
            "url": j.get("hostedUrl", ""), "apply_url": j.get("applyUrl") or j.get("hostedUrl", ""),
            "posted_at": _iso(j.get("createdAt")),
            "description": j.get("descriptionPlain") or _text(j.get("description")), "source": "lever",
        })
    return out


def fetch_ashby(client, name, slug):
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append({
            "company": name, "title": j.get("title", ""),
            "location": j.get("location", "") or "",
            "url": j.get("jobUrl", ""), "apply_url": j.get("applyUrl") or j.get("jobUrl", ""),
            "posted_at": _iso(j.get("publishedAt")),
            "description": j.get("descriptionPlain") or _text(j.get("descriptionHtml")), "source": "ashby",
        })
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def load_companies(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("name") and r.get("ats") and r.get("slug")]


def fetch_all(companies, on_progress=None, delay=0.4):
    """Returns (jobs_by_company, errors). One failing company never stops the rest."""
    results, errors = {}, []
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for i, c in enumerate(companies):
            fetcher = FETCHERS.get(c["ats"].strip().lower())
            try:
                if not fetcher:
                    raise ValueError(f"unsupported ATS '{c['ats']}'")
                results[c["name"]] = fetcher(client, c["name"], c["slug"].strip())
            except Exception as e:  # network error, 404 (wrong slug), bad JSON...
                errors.append(f"{c['name']} ({c['ats']}/{c['slug']}): {e}")
            if on_progress:
                on_progress(i + 1, len(companies), c["name"])
            time.sleep(delay)
    return results, errors

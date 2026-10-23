"""Job Agent UI:  streamlit run app.py"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import collectors
import db
import resume

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(BASE, "master_profile.json")
COMPANIES_PATH = os.path.join(BASE, "companies.csv")

st.set_page_config(page_title="Job Agent", page_icon="💼", layout="wide")
db.init()


def ago(iso):
    s = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    if s < 3600:
        return f"{max(int(s // 60), 1)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} hours ago"
    d = int(s // 86400)
    return f"{d} day{'s' if d > 1 else ''} ago"


def load_profile():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------- sidebar ----------------
st.sidebar.title("💼 Job Agent")
fetch_clicked = st.sidebar.button("🔄 Fetch Jobs", type="primary", use_container_width=True)
st.sidebar.divider()
st.sidebar.subheader("Filters")
q = st.sidebar.text_input("Title / keyword", placeholder="e.g. machine learning")
loc = st.sidebar.text_input("Location contains", placeholder="e.g. India, Remote")
window = st.sidebar.selectbox("Posted within", ["Any time", "Last 24 hours", "Last 7 days", "Last 30 days"])

# ---------------- fetch ----------------
if fetch_clicked:
    companies = collectors.load_companies(COMPANIES_PATH)
    bar = st.progress(0.0, text="Starting...")
    results, errors = collectors.fetch_all(
        companies, on_progress=lambda i, n, name: bar.progress(i / n, text=f"{name} ({i}/{n})"))
    new_total = 0
    for name, jobs in results.items():
        new_total += db.upsert(jobs)
        db.mark_closed(name, jobs)
    bar.empty()
    st.success(f"Fetched {sum(len(j) for j in results.values())} jobs from {len(results)} companies "
               f"- {new_total} new.")
    if errors:
        with st.expander(f"{len(errors)} companies failed (check slug in companies.csv)"):
            st.write("\n".join(f"- {e}" for e in errors))

# ---------------- listing ----------------
jobs = db.list_jobs()
if not jobs:
    st.info("Abhi koi job nahi hai. Sidebar mein **Fetch Jobs** dabao.")
    st.stop()

df = pd.DataFrame(jobs)
if q:
    df = df[df["title"].str.contains(q, case=False, na=False)]
if loc:
    df = df[df["location"].str.contains(loc, case=False, na=False)]
if window != "Any time":
    days = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30}[window]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    df = df[df["sort_at"] >= cutoff]
df = df.reset_index(drop=True)

st.title("Latest jobs")
st.caption(f"{len(df)} jobs - newest first. 'first seen' = source gives no posting date, "
           "so the date this app first found it is used.")

view = pd.DataFrame({
    "When": df["sort_at"].map(ago),
    "Date type": df["date_kind"],
    "Company": df["company"],
    "Title": df["title"],
    "Location": df["location"],
    "Apply": df["apply_url"],
})
event = st.dataframe(
    view, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
    column_config={"Apply": st.column_config.LinkColumn("Apply link", display_text="Apply ↗")},
)

# ---------------- selected job ----------------
sel = event.selection.rows
if not sel:
    st.info("Table mein kisi job ki row select karo: description dikhega aur resume generate kar sakte ho.")
    st.stop()

job = df.iloc[sel[0]].to_dict()
st.divider()
st.subheader(f"{job['title']} - {job['company']}")
c1, c2 = st.columns([1, 3])
c1.link_button("Open apply page ↗", job["apply_url"], use_container_width=True)
c2.caption(f"{job['location']} | {job['date_kind']} {ago(job['sort_at'])}")
with st.expander("Job description"):
    st.text(job["description"] or "(no description)")

if not os.path.exists(PROFILE_PATH):
    st.error("master_profile.json nahi mila.")
    st.stop()
profile = load_profile()
if profile["personal"]["name"].strip().lower() in ("your name", ""):
    st.warning("master_profile.json abhi template hai. Apni real details bharo, phir resume banao.")

cache = st.session_state.setdefault("tailored", {})
if st.button("📄 Generate custom resume", type="primary"):
    with st.spinner("AI JD padh raha hai..."):
        try:
            cache[job["id"]] = resume.tailor(profile, job)
        except Exception as e:
            st.error(f"Resume generation failed: {e}")

t = cache.get(job["id"])
if t:
    m1, m2 = st.columns(2)
    m1.metric("Match score", f"{t['score']}%")
    m2.write("**Matched:** " + (", ".join(t["matched"]) or "-"))
    if t["missing"]:
        st.warning("**Missing skills (resume mein NAHI jodi gayi):** " + ", ".join(t["missing"]))

    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"{profile['personal']['name']}_{job['company']}_{job['title']}")[:80]
    html_str = resume.build_html(profile, t)
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇ DOCX", resume.build_docx(profile, t), f"{fname}.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    d2.download_button("⬇ HTML (print to PDF)", html_str, f"{fname}.html", "text/html")
    pdf = resume.build_pdf(html_str)
    if pdf:
        d3.download_button("⬇ PDF", pdf, f"{fname}.pdf", "application/pdf")
    with st.expander("Resume preview"):
        st.components.v1.html(html_str, height=700, scrolling=True)

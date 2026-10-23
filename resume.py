"""JD-tailored resume: the LLM only SELECTS and ORDERS items from the master profile.
Code then verifies every id, bullet and skill against the profile, so nothing invented can reach the resume.
"""
import html
import io
import json
import re

import ai

PROMPT = """You tailor a resume to a job description. Use ONLY facts from the candidate profile below.
Never invent skills, tools, employers, dates, numbers or achievements.

CANDIDATE PROFILE (experience/projects have ids; bullets are numbered from 0):
{profile_view}

JOB: {title} at {company}
JOB DESCRIPTION:
{jd}

Return JSON with exactly these keys:
- "jd_requirements": list of the 6-15 most important skills/tools/requirements in the JD. Each item is
  {{"term": "<requirement as written in JD>", "profile_skill": "<EXACT string from the profile's skills list that
  genuinely covers it, or null if the candidate does not have it>"}}. Only map when the candidate really has it.
- "summary": 2-3 sentence professional summary using ONLY profile facts, phrased in the JD's vocabulary where the
  profile supports it.
- "experience": list of {{"id": "<experience id>", "bullets": [<bullet numbers, most relevant first>]}}
- "projects": up to 3 of {{"id": "<project id>", "bullets": [<bullet numbers>]}}, most relevant first
"""


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _profile_view(p):
    v = {
        "headline": p.get("headline"), "summary": p.get("summary"), "skills": p.get("skills", []),
        "experience": [
            {"id": e["id"], "title": e["title"], "company": e["company"],
             "bullets": {i: b for i, b in enumerate(e.get("bullets", []))}}
            for e in p.get("experience", [])
        ],
        "projects": [
            {"id": x["id"], "name": x["name"], "tech": x.get("tech", []),
             "bullets": {i: b for i, b in enumerate(x.get("bullets", []))}}
            for x in p.get("projects", [])
        ],
    }
    return json.dumps(v, ensure_ascii=False, indent=1)


def _pick(items, raw_list, limit=None, fallback_bullets=3):
    """Validate LLM picks against real items; keep only valid ids/bullet numbers."""
    by_id = {it["id"]: it for it in items}
    out, used = [], set()
    for entry in raw_list if isinstance(raw_list, list) else []:
        it = by_id.get(entry.get("id")) if isinstance(entry, dict) else None
        if not it or it["id"] in used:
            continue
        n = len(it.get("bullets", []))
        idx = [i for i in entry.get("bullets", []) if isinstance(i, int) and 0 <= i < n]
        idx = list(dict.fromkeys(idx)) or list(range(min(n, fallback_bullets)))
        out.append({"item": it, "bullets": [it["bullets"][i] for i in idx]})
        used.add(it["id"])
    if not out:  # model gave nothing usable -> keep profile order
        for it in items[: limit or len(items)]:
            out.append({"item": it, "bullets": it.get("bullets", [])[:fallback_bullets]})
    return out[:limit] if limit else out


def tailor(profile, job):
    raw = ai.ask_json(PROMPT.format(
        profile_view=_profile_view(profile), title=job["title"], company=job["company"],
        jd=(job.get("description") or "")[:8000]))

    prof_skills = {_norm(s): s for s in profile.get("skills", [])}
    matched, missing = [], []
    for req in raw.get("jd_requirements", []):
        if not isinstance(req, dict) or not req.get("term"):
            continue
        real = prof_skills.get(_norm(req.get("profile_skill") or ""))
        (matched if real else missing).append((req["term"], real))

    matched_skills = list(dict.fromkeys(real for _, real in matched))
    rest = [s for s in profile.get("skills", []) if s not in matched_skills]
    total = len(matched) + len(missing)

    summary = raw.get("summary") if isinstance(raw.get("summary"), str) and raw["summary"].strip() \
        else profile.get("summary", "")
    return {
        "summary": summary,
        "skills": matched_skills + rest,           # only skills that exist in the master profile
        "experience": _pick(profile.get("experience", []), raw.get("experience")),
        "projects": _pick(profile.get("projects", []), raw.get("projects"), limit=3),
        "matched": [t for t, _ in matched],
        "missing": [t for t, _ in missing],       # shown to you, NEVER added to the resume
        "score": round(100 * len(matched) / total) if total else 0,
    }


# ---------- rendering ----------
def _contact(p):
    pers = p.get("personal", {})
    parts = [pers.get("email"), pers.get("phone"), pers.get("location")] + list(pers.get("links", {}).values())
    return " | ".join(x for x in parts if x)


def _dates(e):
    return " - ".join(x for x in [e.get("start"), e.get("end")] if x)


def build_docx(profile, t):
    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading(profile["personal"]["name"], 0)
    if profile.get("headline"):
        d.add_paragraph(profile["headline"])
    d.add_paragraph(_contact(profile))
    if t["summary"]:
        d.add_heading("Summary", 1)
        d.add_paragraph(t["summary"])
    d.add_heading("Skills", 1)
    d.add_paragraph(", ".join(t["skills"]))
    if t["experience"]:
        d.add_heading("Experience", 1)
        for x in t["experience"]:
            e = x["item"]
            para = d.add_paragraph()
            para.add_run(f"{e['title']}, {e['company']}").bold = True
            para.add_run(f"  ({_dates(e)})" + (f" - {e['location']}" if e.get("location") else ""))
            for b in x["bullets"]:
                d.add_paragraph(b, style="List Bullet")
    if t["projects"]:
        d.add_heading("Projects", 1)
        for x in t["projects"]:
            p = x["item"]
            para = d.add_paragraph()
            para.add_run(p["name"]).bold = True
            if p.get("tech"):
                para.add_run("  |  " + ", ".join(p["tech"]))
            for b in x["bullets"]:
                d.add_paragraph(b, style="List Bullet")
    if profile.get("education"):
        d.add_heading("Education", 1)
        for e in profile["education"]:
            line = f"{e.get('degree', '')}, {e.get('institution', '')}  ({_dates(e)})"
            if e.get("score"):
                line += f" - {e['score']}"
            d.add_paragraph(line)
    if profile.get("certifications"):
        d.add_heading("Certifications", 1)
        for c in profile["certifications"]:
            d.add_paragraph(c, style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def build_html(profile, t):
    h = html.escape
    out = ["<html><head><meta charset='utf-8'><style>",
           "body{font-family:Arial,sans-serif;font-size:11pt;max-width:800px;margin:24px auto;color:#111}",
           "h1{margin-bottom:0}h2{border-bottom:1px solid #999;margin-top:18px;font-size:13pt}",
           "ul{margin:4px 0 8px 18px}.sub{color:#444}</style></head><body>",
           f"<h1>{h(profile['personal']['name'])}</h1>",
           f"<div class='sub'>{h(profile.get('headline', ''))}</div><div class='sub'>{h(_contact(profile))}</div>"]
    if t["summary"]:
        out.append(f"<h2>Summary</h2><p>{h(t['summary'])}</p>")
    out.append(f"<h2>Skills</h2><p>{h(', '.join(t['skills']))}</p>")
    if t["experience"]:
        out.append("<h2>Experience</h2>")
        for x in t["experience"]:
            e = x["item"]
            out.append(f"<b>{h(e['title'])}, {h(e['company'])}</b> <span class='sub'>({h(_dates(e))})</span><ul>"
                       + "".join(f"<li>{h(b)}</li>" for b in x["bullets"]) + "</ul>")
    if t["projects"]:
        out.append("<h2>Projects</h2>")
        for x in t["projects"]:
            p = x["item"]
            out.append(f"<b>{h(p['name'])}</b> <span class='sub'>{h(', '.join(p.get('tech', [])))}</span><ul>"
                       + "".join(f"<li>{h(b)}</li>" for b in x["bullets"]) + "</ul>")
    if profile.get("education"):
        out.append("<h2>Education</h2><ul>" + "".join(
            f"<li>{h(e.get('degree', ''))}, {h(e.get('institution', ''))} ({h(_dates(e))})"
            + (f" - {h(str(e['score']))}" if e.get("score") else "") + "</li>"
            for e in profile["education"]) + "</ul>")
    if profile.get("certifications"):
        out.append("<h2>Certifications</h2><ul>" + "".join(f"<li>{h(c)}</li>" for c in profile["certifications"]) + "</ul>")
    out.append("</body></html>")
    return "\n".join(out)


def build_pdf(html_str):
    """Optional: needs `pip install weasyprint` (+ system libs). Returns None if unavailable."""
    try:
        from weasyprint import HTML
        return HTML(string=html_str).write_pdf()
    except Exception:
        return None

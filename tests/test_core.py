import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["JOBS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

import collectors  # noqa: E402
import db  # noqa: E402
import resume  # noqa: E402

PROFILE = {
    "personal": {"name": "Test User", "email": "t@x.com", "links": {}},
    "summary": "Python dev.", "skills": ["Python", "SQL"],
    "experience": [{"id": "e1", "company": "Acme", "title": "Dev", "start": "2022", "end": "2024",
                    "bullets": ["Built APIs", "Wrote tests", "Cut costs 10%"]}],
    "projects": [{"id": "p1", "name": "Bot", "tech": ["Python"], "bullets": ["Made a bot"]}],
    "education": [], "certifications": [],
}


class DbTests(unittest.TestCase):
    def test_newest_first_and_dedupe(self):
        db.init()
        mk = lambda t, p: {"company": "A", "title": t, "location": "X", "url": "u/" + t,
                           "apply_url": "u/" + t, "posted_at": p, "description": "", "source": "t"}
        jobs = [mk("old", "2024-01-01T00:00:00+00:00"), mk("new", "2026-10-01T00:00:00+00:00"), mk("nodate", None)]
        self.assertEqual(db.upsert(jobs), 3)
        self.assertEqual(db.upsert(jobs), 0)  # dedupe
        titles = [j["title"] for j in db.list_jobs()]
        self.assertEqual(titles[0], "nodate")  # first_seen = now -> newest
        self.assertLess(titles.index("new"), titles.index("old"))
        db.mark_closed("A", jobs[:1])
        self.assertEqual([j["title"] for j in db.list_jobs()], ["old"])


class CollectorTests(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(collectors._iso(1700000000000), "2023-11-14T22:13:20+00:00")
        self.assertEqual(collectors._iso("2024-05-01T12:00:00-04:00"), "2024-05-01T16:00:00+00:00")
        self.assertIsNone(collectors._iso(None))

    def test_text(self):
        self.assertEqual(collectors._text("&lt;p&gt;Hi&lt;/p&gt;&lt;li&gt;A&lt;/li&gt;"), "Hi\nA")


class ResumeTests(unittest.TestCase):
    def test_nothing_invented(self):
        fake = {
            "jd_requirements": [{"term": "Python", "profile_skill": "Python"},
                                {"term": "Kubernetes", "profile_skill": "Kubernetes"},  # not in profile
                                {"term": "RAG", "profile_skill": None}],
            "summary": "Python developer.",
            "experience": [{"id": "e1", "bullets": [2, 99]}, {"id": "ghost", "bullets": [0]}],
            "projects": [{"id": "p1", "bullets": [0]}],
        }
        with mock.patch("resume.ai.ask_json", return_value=fake):
            t = resume.tailor(PROFILE, {"title": "ML Eng", "company": "Z", "description": "jd"})
        self.assertNotIn("Kubernetes", t["skills"])
        self.assertEqual(t["missing"], ["Kubernetes", "RAG"])
        self.assertEqual(t["matched"], ["Python"])
        self.assertEqual(t["score"], 33)
        self.assertEqual(t["skills"][0], "Python")
        self.assertEqual(len(t["experience"]), 1)  # 'ghost' dropped
        self.assertEqual(t["experience"][0]["bullets"], ["Cut costs 10%"])  # bad index 99 dropped
        self.assertGreater(len(resume.build_docx(PROFILE, t)), 1000)
        self.assertIn("Test User", resume.build_html(PROFILE, t))

    def test_empty_llm_answer_falls_back(self):
        with mock.patch("resume.ai.ask_json", return_value={}):
            t = resume.tailor(PROFILE, {"title": "x", "company": "y", "description": ""})
        self.assertEqual(t["skills"], ["Python", "SQL"])
        self.assertEqual(t["score"], 0)
        self.assertEqual(len(t["experience"][0]["bullets"]), 3)


if __name__ == "__main__":
    unittest.main()

# Job Agent

AI/IT companies ki jobs fetch karo (latest pehle), apply link lo, aur har JD ke hisaab se custom resume download karo.
**Auto-apply nahi hai**: apply tum khud karoge.

## Setup (5 min)

```bash
cd job-agent
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
```

1. `.env` kholo aur free Gemini key daalo (https://aistudio.google.com/apikey). Ya Ollama use karo (local, unlimited).
2. `master_profile.json` mein **apni real details** bharo. Resume sirf yahin se banega.
3. Run:

```bash
streamlit run app.py
```

## Kaise use karein

1. Sidebar mein **Fetch Jobs** dabao. Jobs sabse nayi upar aayengi.
2. Filters: keyword, location, last 24h / 7 days / 30 days.
3. Table mein job select karo, phir **Open apply page** ya **Generate custom resume**.
4. Resume DOCX / HTML (print to PDF) / PDF mein download karo, aur company ki site pe khud apply karo.

## Date kaise nikalti hai

- Lever / Ashby / Greenhouse (jahan `first_published` ho): asli posting date.
- Jahan source date nahi deta: "first seen" date (jab is app ne job pehli baar dekhi). Table mein *Date type* column dikhata hai.

## Resume mein jhooth kyun nahi jata

AI sirf master profile se **chunta aur order karta hai**. Code har id, bullet number aur skill ko profile se verify karta hai.
JD ki jo skills tumhare profile mein nahi hain, wo **Missing skills** mein dikhti hain, resume mein nahi jaati.
Dhyan: *summary* AI likhta hai, isliye download se pehle ek baar padh lo.

## Companies add karna

`companies.csv` mein row jodo: `name,ats,slug`. Slug career page URL se milta hai:

| ATS | URL pattern | slug |
|---|---|---|
| greenhouse | `boards.greenhouse.io/<slug>` | `<slug>` |
| lever | `jobs.lever.co/<slug>` | `<slug>` |
| ashby | `jobs.ashbyhq.com/<slug>` | `<slug>` |

Galat slug par sirf us company ka error dikhta hai, baaki chalti rehti hain. Workday / custom pages (TCS, Infosys jaisi) v1 mein nahi hain.

## Files

| File | Kaam |
|---|---|
| `app.py` | Streamlit UI |
| `collectors.py` | Greenhouse / Lever / Ashby fetchers |
| `db.py` | SQLite, dedupe, newest-first |
| `ai.py` | Gemini / Ollama |
| `resume.py` | Tailoring + verification + DOCX/HTML/PDF |
| `tests/test_core.py` | Offline tests (`python -m unittest`) |

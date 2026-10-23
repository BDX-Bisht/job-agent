"""LLM access. Provider is chosen by LLM_PROVIDER in .env: 'gemini' (free API) or 'ollama' (local)."""
import json
import os
import re

import httpx


def _gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing. Put it in .env (free key: aistudio.google.com).")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _ollama(prompt):
    r = httpx.post(
        os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/generate",
        json={"model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"), "prompt": prompt,
              "format": "json", "stream": False, "options": {"temperature": 0.2}},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


def ask_json(prompt):
    """Send a prompt, return the parsed JSON object the model answered with."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    raw = _ollama(prompt) if provider == "ollama" else _gemini(prompt)
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    return json.loads(raw)

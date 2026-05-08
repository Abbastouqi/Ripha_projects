"""
grader.py — AI-powered subjective answer grader
Optimised: 2 API calls per question (was 3), questions graded in parallel.
Pipeline: OpenAI ideal answer → single combined grading + analysis call
"""

import json
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv(Path(__file__).parent / ".env")

_api_key = os.getenv("OPENAI_API_KEY", "")
_model   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not _api_key or _api_key == "your_openai_api_key_here":
    print("WARNING: OPENAI_API_KEY not set in .env — grader will not work.")
    _client = None
else:
    _client = OpenAI(api_key=_api_key)
    print(f"INFO: OpenAI grader loaded (model: {_model})")


def _chat(prompt: str) -> str:
    if _client is None:
        raise RuntimeError("OPENAI_API_KEY is not set in .env file.")
    resp = _client.chat.completions.create(
        model=_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def _clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _extract_keywords(text: str, top_n: int = 15) -> list:
    try:
        vec = TfidfVectorizer(stop_words='english', max_features=top_n, ngram_range=(1, 2))
        vec.fit([text])
        return list(vec.get_feature_names_out())
    except Exception:
        return []


def _tfidf_sim(text_a: str, text_b: str) -> float:
    try:
        vec = TfidfVectorizer(stop_words='english')
        mat = vec.fit_transform([text_a, text_b])
        return float(cosine_similarity(mat[0:1], mat[1:2])[0][0])
    except Exception:
        return 0.0


# ── Question extraction ────────────────────────────────────────────────────────

def extract_questions_from_text(text: str) -> list:
    prompt = f"""You are an exam paper parser. Extract all questions from the exam paper text below.

For each question:
- Extract the full question text
- Identify the marks allocated (look for patterns like "(5 marks)", "[10]", "Marks: 3", "5 pts" etc.)
- If no marks are specified, default to 5

Return ONLY a valid JSON array with NO markdown, NO explanation:
[
  {{"title": "Full question text here", "type": "subjective", "marks": 5}},
  {{"title": "Another question", "type": "subjective", "marks": 10}}
]

EXAM PAPER TEXT:
{text[:8000]}"""

    try:
        raw = _clean_json(_chat(prompt))
        questions = json.loads(raw)
        result = []
        for q in questions:
            if isinstance(q, dict) and q.get("title"):
                result.append({
                    "title": str(q["title"]).strip(),
                    "type": "subjective",
                    "marks": max(1, int(q.get("marks", 5)))
                })
        return result
    except Exception as e:
        err = str(e)
        if 'insufficient_quota' in err or '429' in err:
            raise RuntimeError("OpenAI quota exceeded. Please check your billing at platform.openai.com/usage")
        if 'invalid_api_key' in err or '401' in err:
            raise RuntimeError("Invalid OpenAI API key. Please check the key in your .env file.")
        print(f"[grader] extract_questions error: {e}")
        return []


# ── Grade + analyse ONE question in a single combined API call ─────────────────

def _grade_one(question: str, student_answer: str, marks: int) -> dict:
    """
    Two-call pipeline (was three):
      Call 1 — generate ideal answer (short)
      Call 2 — combined grading + full analysis in one JSON response
    Returns the full result dict including keyword fields.
    """
    import time
    q_short = question[:60]
    if not student_answer or not student_answer.strip():
        return {
            "score": 0.0, "feedback": "No answer was provided.",
            "ideal_answer": "", "solution": "",
            "correct_points": [], "mistakes": ["No answer was provided."],
            "matching_keywords": [], "missing_keywords": [],
            "semantic_score": 0.0,
        }

    # ── Call 1: ideal answer ───────────────────────────────────────────────────
    ideal_answer = ""
    try:
        t1 = time.time()
        ideal_answer = _chat(
            f"Write a concise ideal exam answer for this question (2-4 sentences max):\n{question}"
        )
        print(f"[grader]   ideal_answer call: {time.time()-t1:.1f}s  q='{q_short}...'")
    except Exception as e:
        print(f"[grader] ideal answer error: {e}")

    # ── TF-IDF keyword analysis (local, no API) ───────────────────────────────
    ideal_kw   = set(_extract_keywords(ideal_answer)) if ideal_answer else set()
    student_kw = set(_extract_keywords(student_answer))
    matching_keywords = sorted(ideal_kw & student_kw)
    missing_keywords  = sorted(ideal_kw - student_kw)
    tfidf_sim = _tfidf_sim(ideal_answer, student_answer) if ideal_answer else 0.0
    semantic_score = round(tfidf_sim * 100, 1)

    # ── Call 2: combined grading + analysis ───────────────────────────────────
    t2 = time.time()
    combined_prompt = (
        f"You are an expert, fair exam evaluator. Grade and analyse this student answer.\n\n"
        f"Question: {question}\n"
        f"Total Marks: {marks}\n"
        f"Ideal Answer: {ideal_answer}\n"
        f"Student Answer: {student_answer}\n"
        f"TF-IDF keyword similarity (0-1): {tfidf_sim:.2f}\n\n"
        f"Return ONLY valid JSON, no markdown:\n"
        f'{{"score": <number 0 to {marks}>, '
        f'"feedback": "<2-3 sentence constructive feedback>", '
        f'"solution": "<complete 3-6 sentence model answer>", '
        f'"correct_points": ["point student got right"], '
        f'"mistakes": ["specific mistake or missing concept"]}}\n\n'
        f"Rules:\n"
        f"- Award partial credit for partially correct answers\n"
        f"- Consider semantic meaning, not just keywords\n"
        f"- Be constructive and specific\n"
        f"- If fully correct, mistakes = []"
    )

    try:
        raw = _clean_json(_chat(combined_prompt))
        print(f"[grader]   grade+analysis call: {time.time()-t2:.1f}s  q='{q_short}...'")
        result = json.loads(raw)
        score = round(min(float(result.get("score", 0)), float(marks)), 1)
        return {
            "score":            score,
            "feedback":         str(result.get("feedback", "")).strip(),
            "ideal_answer":     ideal_answer,
            "solution":         str(result.get("solution", ideal_answer)).strip(),
            "correct_points":   result.get("correct_points", []),
            "mistakes":         result.get("mistakes", []),
            "matching_keywords": matching_keywords,
            "missing_keywords":  missing_keywords,
            "semantic_score":    semantic_score,
        }
    except Exception as e:
        print(f"[grader] combined grading error: {e}")
        score = round(tfidf_sim * marks, 1)
        return {
            "score":            score,
            "feedback":         f"Auto-graded based on content similarity ({tfidf_sim:.0%} match).",
            "ideal_answer":     ideal_answer,
            "solution":         ideal_answer,
            "correct_points":   [],
            "mistakes":         [],
            "matching_keywords": matching_keywords,
            "missing_keywords":  missing_keywords,
            "semantic_score":    semantic_score,
        }


# ── Grade full submission — questions processed in parallel ────────────────────

def grade_submission(questions: list, answers: dict) -> list:
    """
    Grade all subjective answers in parallel (one thread per question).
    questions: list of question dicts (type=subjective)
    answers:   dict {question_index: answer_text}
    Returns:   list of grading results per question (ordered)
    """
    tasks = []
    for i, q in enumerate(questions):
        if q.get("type") != "subjective":
            continue
        student_ans = answers.get(str(i), answers.get(i, ""))
        tasks.append((i, q["title"], student_ans, int(q.get("marks", 5))))

    results_map = {}

    with ThreadPoolExecutor(max_workers=min(len(tasks), 5)) as pool:
        future_to_idx = {
            pool.submit(_grade_one, title, ans, marks): idx
            for idx, title, ans, marks in tasks
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results_map[idx] = future.result()
            except Exception as e:
                print(f"[grader] question {idx} failed: {e}")
                results_map[idx] = {
                    "score": 0.0, "feedback": "Grading failed.",
                    "ideal_answer": "", "solution": "",
                    "correct_points": [], "mistakes": [],
                    "matching_keywords": [], "missing_keywords": [],
                    "semantic_score": 0.0,
                }

    results = []
    for idx, title, ans, marks in tasks:
        r = results_map.get(idx, {})
        results.append({
            "question_index":   idx,
            "question":         title,
            "marks":            marks,
            "student_answer":   ans,
            "score":            r.get("score", 0.0),
            "feedback":         r.get("feedback", ""),
            "ideal_answer":     r.get("ideal_answer", ""),
            "solution":         r.get("solution", ""),
            "correct_points":   r.get("correct_points", []),
            "mistakes":         r.get("mistakes", []),
            "matching_keywords": r.get("matching_keywords", []),
            "missing_keywords":  r.get("missing_keywords", []),
            "semantic_score":    r.get("semantic_score", 0.0),
        })
    return results


# ── Legacy helpers kept for backwards compatibility ────────────────────────────

def grade_answer(question: str, student_answer: str, marks: int) -> dict:
    r = _grade_one(question, student_answer, marks)
    return {"score": r["score"], "feedback": r["feedback"], "ideal_answer": r["ideal_answer"]}


def analyze_answer(question: str, student_answer: str, ideal_answer: str) -> dict:
    ideal_kw   = set(_extract_keywords(ideal_answer))
    student_kw = set(_extract_keywords(student_answer))
    matching   = sorted(ideal_kw & student_kw)
    missing    = sorted(ideal_kw - student_kw)
    sim = _tfidf_sim(ideal_answer, student_answer)
    return {
        "correct_points": [], "mistakes": [],
        "solution": ideal_answer,
        "matching_keywords": matching,
        "missing_keywords":  missing,
        "semantic_score":    round(sim * 100, 1),
    }

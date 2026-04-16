#!/opt/bin/python3
# -*- coding: utf-8 -*-
"""
Comprova les pàgines d’Informe d’usuari de Moodle i avisa per Telegram.

– Al teu xat (CHAT_ID) rep totes les modificacions amb nota.
– Als xats indicats a FRIEND_CHAT_IDS rep només l’avís “nova nota” (sense nota).

Requereix:
    .env (TOKEN, CHAT_ID, FRIEND_CHAT_IDS, MoodleSession)
    grades.json     (es crea la 1a execució)
"""
import json, sys, re, requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from bs4 import BeautifulSoup, FeatureNotFound
from moodle_login_requests import refresh_cookie

# ─── CONSTANTS ──────────────────────────────────────────────────────
THIS_DIR   = Path(__file__).resolve().parent
STATE_FILE = THIS_DIR / "grades.json"
COURSES_FILE = THIS_DIR / "courses.json"
CREDENTIALS_FILE = THIS_DIR / ".env"
TIMEOUT    = 20

# ─── CREDENTIALS ────────────────────────────────────────────────────
def load_credentials(fp: Path):
    token = chat = cookie = user = pwd = None
    for line in fp.read_text().splitlines():
        k, _, v = line.partition("=")
        if k == "TOKEN":          token  = v.strip()
        elif k == "CHAT_ID":      chat   = int(v.strip())
        elif k == "MoodleSession": cookie = v.strip()
        elif k == "USERNAME":      user   = v.strip()
        elif k == "PASSWORD":      pwd    = v.strip()
    if not all((token, chat, cookie, user, pwd)):
        sys.exit("Falten camps a .env")
    return token, chat, cookie, user, pwd

# ─── COURSE CONFIG ──────────────────────────────────────────────────
def load_courses(fp: Path) -> Dict[int, Dict]:
    """
    Llegeix courses.json i torna:
    {cid (int): {"name": str|None, "friends": [chatIDs]}}
    """
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit("courses.json no existeix")
    courses = {}
    for cid_str, info in data.items():
        cid = int(cid_str)
        courses[cid] = {
            "name":   info.get("name"),
            "friends": [int(x) for x in info.get("friends", [])],
        }
    if not courses:
        sys.exit("courses.json buit – res a fer")
    return courses

# ─── TELEGRAM ───────────────────────────────────────────────────────
def send_telegram(token: str, chat: int, text: str):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
        timeout=TIMEOUT,
    ).raise_for_status()

# ─── UTILITATS ──────────────────────────────────────────────────────
def clean_course_name(raw: str) -> str:
    txt = re.sub(r"<[^>]+>", "", raw).strip()
    txt = re.sub(r"^(User report|Informe d'usuari)\s*[–-]\s*", "", txt, flags=re.I)
    txt = re.sub(r"^\d+\s*[-–]\s*", "", txt)
    txt = re.split(r"[:(]", txt, 1)[0].split("|", 1)[-1].strip()
    return txt

# ─── SCRAPER ────────────────────────────────────────────────────────
def fetch_grades(cookie: str, cid: int):
    url = f"https://moodle.udg.edu/grade/report/user/index.php?id={cid}"
    try:
        r = requests.get(
            url,
            cookies={"MoodleSession": cookie},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.exceptions.TooManyRedirects:
        raise RuntimeError("cookie expired (redirect loop)")

    if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
        raise RuntimeError("cookie expired (redirect)")

    r.raise_for_status()
    html = r.text

    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    raw_name = h1.get_text(" ", strip=True) if h1 else str(cid)

    grades = {}
    for span in soup.select(".gradeitemheader"):
        title = span.get_text(strip=True)
        row   = span.find_parent("tr")
        g_td  = row.select_one("td.column-grade")
        if g_td:
            grades[title] = g_td.get_text(strip=True)

    return grades, raw_name

# ─── STATE (grades.json) ────────────────────────────────────────────
def read_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}

def write_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── MAIN ───────────────────────────────────────────────────────────
def main():
    TOKEN, OWNER_CHAT, cookie, user, pwd = load_credentials(CREDENTIALS_FILE)
    courses = load_courses(COURSES_FILE)          # dict cid → info
    old_state = read_state()                      # cid(str) → {title: grade}
    new_state = {}
    owner_changes: List[str] = []                # missatges complets
    friend_msgs: Dict[int, List[str]] = {}       # chat_id → msg list

    for cid, info in courses.items():
        try:
            grades, raw_name = fetch_grades(cookie, cid)
        except RuntimeError as e:
            if "cookie expired" in str(e):
                print("Cookie expirada – refrescant…")
                cookie = refresh_cookie(CREDENTIALS_FILE)
                grades, raw_name = fetch_grades(cookie, cid)
            else:
                raise

        course_name = info["name"] or clean_course_name(raw_name)
        new_state[cid] = grades
        prev_grades = old_state.get(str(cid), {})

        for title, new in grades.items():
            old = prev_grades.get(title)
            # Quan la nota no estava penjada → "-" (o None)
            was_empty = old in (None, "-")
            is_now_ok = new not in ("", "-")

            if is_now_ok and was_empty:
                owner_changes.append(f"• *{course_name}*: “{title}” = *{new}* _(nou)_")
                for friend in info["friends"]:
                    friend_msgs.setdefault(friend, []).append(
                        f"• *{course_name}*: “{title}” – nota publicada"
                    )
            elif is_now_ok and new != old:
                owner_changes.append(f"• *{course_name}*: “{title}” {old} → *{new}*")

    # ── Enviament a Telegram ──────────────────────────────────────
    if owner_changes:
        header = f"📊 *Actualització de notes* ({datetime.now():%d/%m %H:%M}):\n"
        text = header + "\n".join(owner_changes)
        try:
            send_telegram(TOKEN, OWNER_CHAT, text)
            print("Missatge enviat a mi mateix:")
            print(text)
            print() #fem newline

        except Exception as e:
            print("Telegram error (owner):", e, file=sys.stderr)

    for chat_id, msgs in friend_msgs.items():
        # (els amics només reben info quan hi ha nota nova, no actualització)
        try:
            header = f"ℹ️ *Hi ha notes noves!* ({datetime.now():%d/%m %H:%M}):\n"
            text   = header + "\n".join(msgs)
            send_telegram(TOKEN, chat_id, text)
            print(f"Missatge enviat a amic {chat_id}:")
            print(text)
            print() #fem newline

        except Exception as e:
            print(f"Telegram error (amic {chat_id}):", e, file=sys.stderr)

    if not owner_changes and not friend_msgs:
        print("Sense canvis – no s’envia Telegram.\n")

    write_state(new_state)


if __name__ == "__main__":
    print()
    print("/////////////////////////    \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\")
    print("x--------     gradesChecker (versio 1.2)     --------x")
    print()
    try:
        main()
    except:
        print("\nExecució fallida.")
    horaExecucio = f"{datetime.now():%d/%m %H:%M}"
    print("x--------  fi execucio - hora:", horaExecucio, "  --------x")
    print("\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\    /////////////////////////")
    print()

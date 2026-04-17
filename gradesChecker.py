#!/opt/bin/python3
# -*- coding: utf-8 -*-
"""
Comprova les pàgines d’Informe d’usuari de Moodle i avisa per Telegram.

– Al teu xat (CHAT_ID) rep totes les modificacions amb nota.
– Als xats indicats a FRIEND_CHAT_IDS rep només l’avís “nova nota” (sense nota).

Requereix:
    credentials.txt (TOKEN, CHAT_ID, FRIEND_CHAT_IDS, MoodleSession)
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
    import os
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=fp)
    token = os.getenv("TOKEN")
    chat_str = os.getenv("CHAT_ID")
    chat = int(chat_str) if chat_str else None
    user = os.getenv("USERNAME")
    pwd = os.getenv("PASSWORD")
    if not all((token, chat, user, pwd)):
        sys.exit("Falten camps a .env")
    return token, chat, user, pwd

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
def fetch_grades(sess: requests.Session, cid: int):
    url = f"https://moodle.udg.edu/grade/report/user/index.php?id={cid}"
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
    except requests.exceptions.TooManyRedirects:
        raise RuntimeError("cookie expired (redirect loop)")

    r.raise_for_status()
    html = r.text

    # Detectem si hem acabat a la pàgina de login (cookie expirada)
    if "adAS_username" in html or "SAMLRequest" in html or "/login/index.php" in r.url:
        raise RuntimeError("cookie expired (redirect)")

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
    TOKEN, OWNER_CHAT, user, pwd = load_credentials(CREDENTIALS_FILE)
    courses = load_courses(COURSES_FILE)          # dict cid → info
    old_state = read_state()                      # cid(str) → {title: grade}
    new_state = {}
    owner_changes: List[str] = []                # missatges complets
    friend_msgs: Dict[int, List[str]] = {}       # chat_id → msg list

    # Creem una sessió amb les cookies guardades
    sess = requests.Session()
    cookies_file = CREDENTIALS_FILE.with_name("cookies.json")
    if cookies_file.exists():
        try:
            sess.cookies.update(json.loads(cookies_file.read_text()))
        except Exception:
            pass

    for cid, info in courses.items():
        try:
            grades, raw_name = fetch_grades(sess, cid)
        except RuntimeError as e:
            if "cookie expired" in str(e):
                print("Cookie expirada – refrescant…")
                sess = refresh_cookie(CREDENTIALS_FILE)
                grades, raw_name = fetch_grades(sess, cid)
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
    print("x--------     gradesChecker (versio 1.2FA)     --------x")
    print()
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nExecució fallida. ({e})")
    horaExecucio = f"{datetime.now():%d/%m %H:%M}"
    print("x--------  fi execucio - hora:", horaExecucio, "  --------x")
    print("\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\    /////////////////////////")
    print()

# /opt/bin/python3
import pathlib, re, sys, html
import requests
from bs4 import BeautifulSoup   # pip3 install beautifulsoup4


LOGIN_USER_FIELD = "adAS_username"   # comprova-ho a DevTools
LOGIN_PASS_FIELD = "adAS_password"

def refresh_cookie(creds_path: pathlib.Path, test_course: int = 41306) -> str:
    # ── 1. Llegeix credencials
    creds = dict(
        line.strip().split("=", 1)          # 'KEY=value'
        for line in creds_path.read_text().splitlines()
        if "=" in line
    )
    user, pwd = creds.get("USERNAME"), creds.get("PASSWORD")
    if not user or not pwd:
        sys.exit("Falten USERNAME/PASSWORD a .env")

    sess = requests.Session()
    target = f"https://moodle.udg.edu/grade/report/user/index.php?id={test_course}"

    # ── 2. Primer GET → redirecció a SSO
    r1 = sess.get(target, allow_redirects=True)

    # Si ja hem arribat al formulari de login (té el camp de user), passem-hi directament.
    # Si no, potser és un pas intermig (Hidden SAMLRequest) → també l'agafarem igualment.
    html1 = r1.text
    if LOGIN_USER_FIELD not in html1 and "SAMLRequest" not in html1:
        raise RuntimeError("No trobo ni el camp de user ni SAMLRequest – revisa el flux de login.")


    # ── 3. Omple formulari de login
    soup = BeautifulSoup(r1.text, "html.parser")
    form = soup.find("form")
    action = form["action"]
    data = {i["name"]: i.get("value", "") for i in form("input") if i.get("name")}
    data[LOGIN_USER_FIELD] = user
    data[LOGIN_PASS_FIELD] = pwd

    r2 = sess.post(action, data=data, allow_redirects=True)

    # ── 4. Formulari amb SAMLResponse (auto-POST)
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.find("form")
    if form2:
        # Si trobem la forma SAML, en recollim tots els inputs i fem POST
        inputs = form2.find_all("input", attrs={"name": True})
        data2 = { inp["name"]: inp.get("value", "") for inp in inputs }
        post_url = form2["action"]
        r3 = sess.post(post_url, data=data2, allow_redirects=True)
    else:
        # Si no hi ha cap formulari SAML (ja som dins Moodle), reutilitzem r2
        r3 = r2


    # ── 5. Ha d’acabar de nou a Moodle i tenir cookie
    if "MoodleSession" not in sess.cookies:
        raise RuntimeError("No s'ha obtingut MoodleSession")

    cookie_val = sess.cookies["MoodleSession"]

    # ── 6. Actualitza .env
    lines = []
    found = False
    for ln in creds_path.read_text().splitlines():
        if ln.startswith("MoodleSession="):
            lines.append(f"MoodleSession={cookie_val}")
            found = True
        else:
            lines.append(ln)
    if not found:
        lines.append(f"MoodleSession={cookie_val}")
    creds_path.write_text("\n".join(lines) + "\n")

    return cookie_val


if __name__ == "__main__":
    here = pathlib.Path(__file__).with_name(".env")
    print(refresh_cookie(here))

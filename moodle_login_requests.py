# /opt/bin/python3
import pathlib, re, sys, html
import requests
import pyotp
from bs4 import BeautifulSoup   # pip3 install beautifulsoup4


LOGIN_USER_FIELD = "adAS_username"   # comprova-ho a DevTools
LOGIN_PASS_FIELD = "adAS_password"

def refresh_cookie(creds_path: pathlib.Path, test_course: int = 41306) -> requests.Session:
    """
    Fa login complet a Moodle (SSO + 2FA) i retorna la requests.Session
    amb totes les cookies necessàries.
    També actualitza MoodleSession a credentials.txt.
    """
    import os
    from dotenv import load_dotenv

    # ── 1. Llegeix credencials des de .env
    load_dotenv(dotenv_path=creds_path)
    
    user = os.getenv("USERNAME")
    pwd = os.getenv("PASSWORD")
    secret = os.getenv("SECRET_KEY")

    if not user or not pwd:
        sys.exit("Falten USERNAME/PASSWORD a .env")
    if not secret:
        sys.exit("Falta SECRET_KEY (TOTP) a .env")

    sess = requests.Session()
    target = f"https://moodle.udg.edu/grade/report/user/index.php?id={test_course}"

    # ── 2. Primer GET → redirecció a SSO
    r1 = sess.get(target, allow_redirects=True)

    html1 = r1.text
    if LOGIN_USER_FIELD not in html1 and "SAMLRequest" not in html1:
        raise RuntimeError("No trobo ni el camp de user ni SAMLRequest – revisa el flux de login.")


    # ── 3. Omple formulari de login (usuari + contrasenya)
    soup = BeautifulSoup(r1.text, "html.parser")
    form = soup.find("form")
    action = form["action"]
    data = {i["name"]: i.get("value", "") for i in form("input") if i.get("name")}
    data[LOGIN_USER_FIELD] = user
    data[LOGIN_PASS_FIELD] = pwd

    r2 = sess.post(action, data=data, allow_redirects=True)

    # ── 3b. 2FA / TOTP ──────────────────────────────────────────────
    soup_2fa = BeautifulSoup(r2.text, "html.parser")
    otp_field = soup_2fa.find("input", id="input2factor")

    if otp_field:
        print("Detectat formulari 2FA (JS) – enviant codi TOTP…")
        clean_secret = secret.split('&')[0].strip()
        totp = pyotp.TOTP(clean_secret)
        code = totp.now()

        btn = soup_2fa.find("a", id="notification_2factor_button_ok")
        if not btn or not btn.get("href"):
            raise RuntimeError("No s'ha trobat el botó d'acceptar 2FA per extraure la URL")
            
        action_2fa = btn.get("href")
        from urllib.parse import urljoin
        if not action_2fa.startswith("http"):
            action_2fa = urljoin(r2.url, action_2fa)

        # Construïm el POST tal com ho fa el codi JS incrustat
        data_2fa = {
            "adAS_authn_module": "otp_module",
            "adAS_mode": "authn",
            "adAS_otp_code": code
        }

        r2 = sess.post(action_2fa, data=data_2fa, allow_redirects=True)
        print("Codi TOTP enviat.")

    # ── 4. Formulari amb SAMLResponse (auto-POST)
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.find("form")
    if form2:
        inputs = form2.find_all("input", attrs={"name": True})
        data2 = { inp["name"]: inp.get("value", "") for inp in inputs }
        post_url = form2["action"]
        r3 = sess.post(post_url, data=data2, allow_redirects=True)
    else:
        r3 = r2


    # ── 5. Ha d'acabar de nou a Moodle i tenir cookie
    if "MoodleSession" not in sess.cookies:
        raise RuntimeError("No s'ha obtingut MoodleSession")

    # ── 6. Desa tot el cookie jar (inclosos SSO i idpsession)
    import json
    import os
    
    shared_dir = os.getenv("SHARED_COOKIE_DIR")
    if shared_dir:
        cookies_file = pathlib.Path(shared_dir) / "cookies.json"
    else:
        cookies_file = creds_path.with_name("cookies.json")

    with open(cookies_file, "w") as f:
        json.dump(requests.utils.dict_from_cookiejar(sess.cookies), f)

    return sess


if __name__ == "__main__":
    here = pathlib.Path(__file__).with_name(".env")
    s = refresh_cookie(here)
    print("MoodleSession:", s.cookies["MoodleSession"])

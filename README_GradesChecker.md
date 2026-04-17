# 📚 Pamusa's MoodleBot - GradesChecker (versió 1.3)

**MoodleBot GradesChecker** és un petit script en Python que comprova periòdicament l’“Informe d’usuari” de Moodle (UdG) i envia avisos per Telegram quan apareix una nota nova o quan alguna qualificació canvia.

> **Funcionalitats principals**  
> - Detecta qualificacions noves o modificades en els vostres cursos.  
> - T’avisa a tu amb la nota concreta i, en paral·lel, avisa als teus amics **sense** revelar-los la teva nota.  
> - Gestió automàtica de la sessió Moodle (suport per SSO + 2FA amb codis TOTP).  
> - Estat persistent en `grades.json` per no repetir notificacions innecessàries.  
> - Pensat per executar-se de fons mitjançant *cron* (o qualsevol altre planificador).

---

## 🖥️ Requisits

Es requereix **Python 3.8** o superior (ja instal·lat en la majoria de sistemes).

Totes les llibreries necessàries es troben a `requirements.txt`:
- `requests`
- `beautifulsoup4`
- `lxml`
- `pyotp` (generació automàtica del codi mòbil al doble-factor)
- `python-dotenv` (carregador de secrets d'entorn)

Pots instal·lar-ho tot d’un cop executant:
```bash
pip install -r requirements.txt
```

---

## 🔧 Configuració

### 1. Variables d'Entorn (`.env`)
Crea un fitxer anomenat `.env` al mateix directori que l'script `gradesChecker.py` i emplena'l així:

```env
TOKEN=            # Token del teu bot de Telegram (te'l dóna @BotFather)
CHAT_ID=          # El teu xat (obre @userinfobot per saber la teva ID)
USERNAME=         # Usuari de retorn de la UdG (exemple: uXXXXXXX)
PASSWORD=         # Contrasenya de la UdG
SECRET_KEY=       # Llavors secreta per generar els codis TOTP de 2FA 
```

> **Nota:** La galeta manual `MoodleSession` i la llista `FRIEND_CHAT_IDS` han passat a la història. Aquest MoodleBot desa tota la sessió a un fitxer protegit i gestiona els amics mitjançant el JSON local.

### 2. Fitxer `courses.json`
Els `COURSE_ID` i els amics s'organitzen en el fitxer `courses.json`. Has de posar-lo a la mateixa carpeta:

**Exemple de `courses.json`:**
```json
{
  "41311": {                    
    "name": "Robòtica",      
    "friends": [22222222]       
  },
  "41320": {
    "name": "Legislació",
    "friends": [22222222, 33333333]
  },
  "41305": {}                   
}
```
- **Clau:** És el `COURSE_ID` de la teva assignatura, tal com apareix a l’URL de Moodle sent el paràmetre `?id=X`.
- **`name`** *(opcional)*: El nom personalitzat de l'assignatura que es mostrarà a Telegram (sobreescrivint el títol web per defecte).
- **`friends`** *(opcional)*: Una llista numèrica d’IDs de xat dels teus amics. Ells **només** reben un avís curiós dient "s'ha publicat nota", però absolutament cap d'ells rep l'aprovat que has tret tu!

---

## ▶️ Ús Manual i Primera Execució

Executa l'script de forma manual per a la primera volta per comprovar que la sessió s'hagi lligat correctament i per inicialitzar el `grades.json`:

```bash
python3 gradesChecker.py
```

---

## ⏲️ Execució Periòdica amb cron

Per deixar-lo encès 24/7 a un servidor o ordinador en miniatura, programa una entrada cron per disparar el codi el temps que vulguis. Obre l'editor de cron:

```bash
sudo vim /opt/etc/crontab
```

I afegeix la línia per comprovar les notes **cada 15 minuts**, bolcant la sortida de les alertes a un arxiu "log":
```bash
*/15 * * * * usuari /RutaScripts/MoodleBot/GradesChecker/gradesChecker.py >> /RutaAlLog/cron.log 2>&1
```

> Els cinc primers camps de codificació d'espais són de Linux Cron, i signifiquen respectivament: `minut`, `hora`, `dia (mes)`, `mes`, `dia (setmana)`.

Per llegir el registre (Log) recent amb les entrades de Moodle:
```bash
tail -f /RutaAlLog/cron.log
```

---

## 🏗️ Funcionament Intern
**Això és el que fa el codi cada cop que s'engega:**
1. **SSO Segur i Transparent**: Processa l'inici de sessió al campus de la UdG resolent internament la plataforma i els codis TOTP enviats del generador automàtic per al portal de CAS.
2. **Scraping dels panells evaluatius**: Per a cada clau iterada dins `courses.json`, examina en privat si la base de taules (BeautifulSoup de `.gradeitemheader`) inclou noves valoracions per a l'alumne.
3. **Anàlisi Diferencial**: Les qualificacions vigents només es tornen a notificar al Telegram del propietari si no figuren als antics buits emmagatzemats pel memòria interna (`grades.json`) a un temps anterior.
4. **Desat local**: Guarda els punts i el nou Cookie Jar renovat per la propera consulta ràpida en menys d'un segon.

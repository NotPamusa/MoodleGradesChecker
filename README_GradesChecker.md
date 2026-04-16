# 📚 Pamusa's MoodleBot - GradesChecker (versió 1.3)

**MoodleBot GradesChecker** és un petit script en Python que comprova periòdicament l’“Informe d’usuari” de Moodle (UdG) i envia avisos per Telegram quan apareix una nota nova o quan alguna qualificació canvia.

> **Funcionalitats principals**  
> - Detecta qualificacions noves o modificades en els vostres cursos.  
> - T’avisa a tu amb la nota concreta i, en paral·lel, avisa als teus amics **sense** revelar-los la teva nota.  
> - Gestió automàtica de la sessió Moodle (renova la `MoodleSession` quan caduca).  
> - Estat persistent en `grades.json` per no repetir notificacions (exemple a `example_grades.json`).  
> - Pensat per executar-se via *cron* (o qualsevol planificador).

---

## 🖥️ Requisits

| Dependència 		    | Versió mínima | Instal·lació                          	    |
|-----------------------|---------------|-----------------------------------------------|	
| Python     	 	    | 3.8          	| ja instal·lat en la majoria de sistemes 	    |
| `requests`  		    | —           	| `pip install requests`                	    |
| `beautifulsoup4` 	    | —      	    | `pip install beautifulsoup4`          	    |
| **(opcional)** `lxml` | —  		    | `pip install lxml` — parser HTML més ràpid	|

Pots instal·lar-ho tot d’un cop amb:

```bash
pip install -r requirements.txt
```




## 🔧 Configuració

Crea el fitxer `.env` al mateix directori (pots basar-te en `example.env`):
```env
TOKEN=123456:ABCDEF…          # Token del teu bot de Telegram
CHAT_ID=111111111             # El teu xat (on reps les notes reals)
FRIEND_CHAT_IDS=22222222,33333333   # Xats d’amics (sense notes)
MoodleSession=s%3A…           # Cookie Moodle (es renova automàticament)
USERNAME=uXXXXXXX             # Usuari UdG
PASSWORD=MySuperSecretPass    # Contrasenya UdG
```

TOKEN: crea un bot amb @BotFather.
CHAT_ID: parla amb @userinfobot o envia qualsevol missatge al teu bot i consulta https://api.telegram.org/botTOKEN/getUpdates.
FRIEND_CHAT_IDS: llista separada per comes (sense espais) dels teus amics que només rebran l’avís de “hi ha nota nova a PAC1”, però no la xifra.
MoodleSession: s’obté amb les galetes del navegador un cop identificat al Moodle. El bot la refresca quan cal, però cal USERNAME i PASSWORD per poder-ho fer.
(Nota: credentials ara s'han mogut a .env per seguretat)

Primera execució manual (crea `grades.json` i comprova que no hi hagi errors):
```bash
python3 gradesChecker.py
```



    ·Fitxer courses.json

Des de la versió 1.3 els COURSE_IDs i quins amics reben avisos es configuren fora del codi, en un petit fitxer JSON col·locat al mateix directori que gradesChecker.py (pots usar example_courses.json de plantilla).

Exemple:

```json
{
  "41311": {                    // COURSE_ID (obligatori, string o número)
    "name":    "Robòtica",      // (opcional) nom de l'assignatura que es mostrarà al missatge (sinó, es posarà el codi, o el que trobi de titol l'scraper)
    "friends": [22222222]       // (opcional) xats que rebran l’avís "hi ha nota nova"
  },

  "41320": {
    "name":    "Legislació",
    "friends": [22222222,33333333]
  },

  "41305": {}                   // si no poses res més → només tu rebràs notificacions
}
```

Clau = COURSE_ID tal com apareix a l’URL de Moodle ?id=41311.
name — sobreescriu el títol que extreu automàticament el bot (útil quan el <h1> porta codi, curs acadèmic, etc.).
friends — llista d’IDs de xat (integers) dels teus amics.
Si està buida o no existeix, cap amic rebrà notificacions d’aquest curs.
Els amics només reben l’avís quan la qualificació passa de “‐” (guionet) a un valor real — mai la teva nota concreta.



## ▶️ Ús manual
En terminal: 
```bash
python3 gradesChecker.py
```


## ⏲️ Execució periòdica amb cron

obrir:
```bash
sudo vim /opt/etc/crontab
```

Afegir la línia:
```bash
*/15 * * * * usuari /dir/gradesChecker.py >> /share/Public/MoodleBot/GradesChecker/cron.log 2>&1
```

Exemple:
```bash
*/15 * * * * psm /opt/bin/python3 /share/_psm/MoodleBot/GradesChecker/gradesChecker.py >> /share/Public/MoodleBot/GradesChecker/cron.log 2>&1
```


Els cinc camps indiquen minut hora dia-mes mes dia-setmana.
Per exemple, */5 * * * * seria cada 5 min; 0 8 * * 1-5 cada dia feiner a les 08:00.


Per veure el log:
Recent:
```bash
tail -f /share/Public/MoodleBot/GradesChecker/cron.log
```

Total:
```bash
cat /share/Public/MoodleBot/GradesChecker/cron.log
```


## 🏗️ Funcionament intern

1- Per a cada COURSE_ID definides al codi:
Descarrega la taula de qualificacions amb la cookie MoodleSession.
Si rep un 3xx ➜ cookie expirada: torna a autenticar-se i repeteix.

2- Fa scraping amb BeautifulSoup:
Selecciona span.gradeitemheader (Tasca, Element manual, etc.).
Llegeix la nota de la mateixa fila <tr>.

3- Compara amb grades.json:
nova entrada ➜ avisa tothom.
nota actualitzada ➜ avisa només al propietari.

4- Envia missatges via Telegram Bot API.

5- Guarda el nou estat.

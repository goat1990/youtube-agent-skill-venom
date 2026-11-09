#!/usr/bin/env python3
"""title.py - lint a YouTube title and thumbnail pairing before you publish it.

    python3 title.py --title "..." --thumb "AI RAN IT"
    python3 title.py titles.txt            # one per line, ranked
    python3 title.py --title "..." --json
    python3 title.py --lang es titles.txt  # force Spanish (default: detected from the words)

The pairing is the unit, not the title. A title that repeats the thumbnail text wastes half the
click surface, and that is the single most common mistake this checks for.

Length: YouTube truncates around 60 characters on desktop search and around 40 on a mobile home
feed. Both limits are reported because they are different failures - a desktop truncation loses the
tail, a mobile one can lose the subject.
"""
import json, re, sys, os

DESKTOP, MOBILE, HARD = 60, 40, 100
VAGUE = {"amazing","incredible","insane","crazy","huge","massive","ultimate","best","powerful",
         "secret","revolutionary","mindblowing","epic","perfect","complete","everything"}
STOP = {"the","a","an","of","for","to","in","on","and","or","is","are","with","your","you","my","i",
        "this","that","it","how","what","why"}
VAGUE_ES = {"increíble","increíbles","impresionante","impresionantes","brutal","loco","locos","locura",
            "enorme","enormes","masivo","definitivo","definitiva","mejor","mejores","poderoso","secreto",
            "secretos","revolucionario","alucinante","épico","épica","perfecto","perfecta","completo",
            "completa","todo"}
STOP_ES = {"el","la","los","las","un","una","de","del","para","a","en","y","o","es","son","con","tu",
           "tus","te","mi","yo","esto","este","esta","eso","que","como","cómo","qué","por","lo","al",
           "se","por qué"}
LANGS = {"en": (VAGUE, STOP, r"[a-z0-9']+"), "es": (VAGUE_ES, STOP_ES, r"[a-záéíóúüñ0-9']+")}

ES_HINT = {"el","la","los","las","de","del","que","en","un","una","y","por","para","con","es","se",
           "lo","al","su","sus","tu","tus","te","nadie","más","pero","como","este","esta","son",
           "hay","qué","cómo","sin"}
EN_HINT = {"the","of","and","to","in","is","you","your","that","it","for","on","with","this","how",
           "why","what","are","was","be","i","my","we","nobody","do","not"}

def detect(t):
    """'es' when the text reads as Spanish, otherwise 'en'. Ties go to English."""
    w = re.findall(r"[a-záéíóúüñ']+", t.lower())
    es = sum(1 for x in w if x in ES_HINT) + 2 * len(re.findall(r"[áéíóúñ¿¡]", t.lower()))
    en = sum(1 for x in w if x in EN_HINT)
    return "es" if es > en else "en"

def take_lang(a):
    """Pull --lang en|es|auto out of the argument list. None means detect."""
    if "--lang" not in a: return None
    i = a.index("--lang"); v = a[i + 1] if i + 1 < len(a) else None; del a[i:i + 2]
    if v not in ("en", "es", "auto"): print("--lang takes en, es or auto"); sys.exit(1)
    return None if v == "auto" else v

def words(t, rx=r"[a-z0-9']+"): return re.findall(rx, t.lower())

MSG = {
    "en": {
        "hard": "{n} characters - YouTube's hard limit is {lim}",
        "desktop": "{n} characters - desktop search cuts near {lim}",
        "inside": "{n} characters, inside the {lim}-character desktop cut",
        "mobile": 'a mobile feed shows about "{head}..." - check the subject survives',
        "shouting": "{n} all-caps words - two is the ceiling before it reads as spam",
        "caps": "{n} all-caps word for emphasis",
        "vague": "{words} - swap for a number, a name or a date",
        "figure": "carries a concrete figure ({nums})",
        "no-number": "no number, date or name - the most reliable single fix",
        "question": "open question in the title",
        "front-load": "the first three words are all filler - move the subject forward",
        "duplicate": "thumbnail repeats the title on {words} - the thumbnail should say what the title does not",
        "different": "thumbnail and title carry different words",
        "thumb-length": "{n} words on the thumbnail - three is the ceiling at feed size",
        "header": "{n} chars   score {score}/100",
    },
    "es": {
        "hard": "{n} caracteres - el límite de YouTube es {lim}",
        "desktop": "{n} caracteres - la búsqueda en computadora corta cerca de {lim}",
        "inside": "{n} caracteres, dentro del corte de {lim} en computadora",
        "mobile": 'en el celular se ve más o menos "{head}..." - revisa que el tema quede visible',
        "shouting": "{n} palabras en mayúsculas - con más de dos parece spam",
        "caps": "{n} palabra en mayúsculas para resaltar",
        "vague": "{words} - cámbialo por un número, un nombre o una fecha",
        "figure": "trae una cifra concreta ({nums})",
        "no-number": "sin número, fecha ni nombre - es el arreglo que más ayuda",
        "question": "el título deja una pregunta abierta",
        "front-load": "las tres primeras palabras son de relleno - pon el tema antes",
        "duplicate": "la miniatura repite el título en {words} - la miniatura debe decir lo que el título no dice",
        "different": "la miniatura y el título usan palabras distintas",
        "thumb-length": "{n} palabras en la miniatura - tres es el máximo a tamaño de feed",
        "header": "{n} caracteres   puntaje {score}/100",
    },
}
NUM_WORD_ES = re.compile(r"\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince"
                         r"|diec?i\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa"
                         r"|cien|ciento|mil|millón|millones)\b", re.I)

def stem_es(w):
    """Singular and plural are the same word for a repeat: "prohibido" and "prohibidos"."""
    return w[:-2] if len(w) > 4 and w.endswith("es") else w[:-1] if len(w) > 3 and w.endswith("s") else w

def check(title, thumb=None, lang=None):
    t = title.strip()
    lang = lang or detect(f"{t} {thumb or ''}")
    vague, stop, rx = LANGS[lang]
    n = len(t)
    issues, good = [], []
    M = MSG[lang]
    if n > HARD: issues.append(("length", M["hard"].format(n=n, lim=HARD)))
    elif n > DESKTOP: issues.append(("length", M["desktop"].format(n=n, lim=DESKTOP)))
    else: good.append(M["inside"].format(n=n, lim=DESKTOP))
    if n > MOBILE:
        head = t[:MOBILE].rsplit(" ", 1)[0]
        issues.append(("mobile", M["mobile"].format(head=head)))
    caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
    if len(caps) > 2: issues.append(("shouting", M["shouting"].format(n=len(caps))))
    elif caps: good.append(M["caps"].format(n=len(caps)))
    v = [w for w in words(t, rx) if w in vague]
    if v: issues.append(("vague", M["vague"].format(words=", ".join(sorted(set(v))))))
    nums = re.findall(r"\d[\d,.]*%?", t)
    if lang == "es": nums += [m.group(0) for m in NUM_WORD_ES.finditer(t)]
    if nums: good.append(M["figure"].format(nums=", ".join(nums[:3])))
    else: issues.append(("no-number", M["no-number"]))
    if t.endswith("?"): good.append(M["question"])
    front = [w for w in words(t, rx)[:3] if w not in stop]
    if not front: issues.append(("front-load", M["front-load"]))
    if thumb:
        tw, hw = set(words(t, rx)) - stop, set(words(thumb, rx)) - stop
        shared = tw & hw
        if lang == "es":  # Spanish: a plural repeats its singular
            stems = {stem_es(w) for w in hw}
            shared = {w for w in tw if stem_es(w) in stems}
        if shared:
            issues.append(("duplicate", M["duplicate"].format(words=", ".join(sorted(shared)))))
        else:
            good.append(M["different"])
        if len(words(thumb, rx)) > 4:
            issues.append(("thumb-length", M["thumb-length"].format(n=len(words(thumb, rx)))))
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    r = {"title": t, "chars": n, "score": score, "issues": issues, "good": good}
    if lang == "es": r["lang"] = "es"
    return r

def show(r):
    print(f'\n  "{r["title"]}"')
    print("  " + MSG[r.get("lang", "en")]["header"].format(n=r["chars"], score=r["score"]))
    for k, m in r["issues"]: print(f"    x  {k:<12} {m}")
    for m in r["good"]:      print(f"    ok              {m}")

def take(a, flag, cast=str):
    """Pull `flag value` out of the argument list, in any position (None when absent). A missing or
    bad value stops with a one-line message instead of a Python error."""
    if flag not in a: return None
    i = a.index(flag)
    if i + 1 >= len(a) or a[i + 1].startswith("--"): sys.exit(f"{flag} needs a value")
    v = a.pop(i + 1); a.pop(i)
    try: return cast(v)
    except ValueError: sys.exit(f"{flag} needs a number, got {v!r}")

def first_file(a):
    """The first argument that is not an option. Help when there is none, a clear stop when it is missing."""
    files = [x for x in a if not x.startswith("--")]
    if not files: print(__doc__); sys.exit(1)
    if not os.path.exists(files[0]): sys.exit(f"file not found: {files[0]}")
    return files[0]

def main():
    a = sys.argv[1:]
    lang = take_lang(a)
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    thumb, title = take(a, "--thumb"), take(a, "--title")
    if title is not None:
        rows = [check(title, thumb, lang)]
    else:
        rows = [check(l, thumb, lang) for l in open(first_file(a), encoding="utf-8").read().splitlines() if l.strip()]
    rows.sort(key=lambda r: -r["score"])
    if as_json: print(json.dumps(rows, indent=1)); return
    for r in rows: show(r)
    print()

if __name__ == "__main__":
    main()

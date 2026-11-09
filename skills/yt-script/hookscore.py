#!/usr/bin/env python3
"""hookscore.py - score a YouTube hook before you waste a take on it.

Five properties, 0-100 each, and a verdict that is 60% the mean and 40% the weakest one. The
weakest-link weighting is deliberate: a hook with four strong properties and one dead one is a hook
that leaks at the dead one, and averaging hides that.

    python3 hookscore.py hooks.txt            # one hook per line, ranked
    python3 hookscore.py --hook "one line"    # score a single hook
    python3 hookscore.py --json hooks.txt     # machine-readable
    python3 hookscore.py --lang es hooks.txt  # force Spanish (default: detected per hook)

WHAT THIS CAN AND CANNOT TELL YOU. Measured against 74 real short-form hooks (first 15 seconds of
auto-captions, top-8 and bottom-8 by views across five channels): it separates deliberately bad
hooks from real ones well, and it separates a creator's own hits from their own misses barely at
all. Treat a low score as a reason to look again, never a high score as a promise.

SPANISH. The Spanish word lists mirror the English ones and were tuned so that each formula's
Spanish example scores close to its English original. They have NOT been measured against real
Spanish hooks with view data, so a Spanish score is a rougher signal than an English one.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMULAS = json.load(open(os.path.join(HERE, "hooks.json"), encoding="utf-8"))["hooks"]

FILLER = {"basically","actually","literally","just","really","very","so","kind","sort","like",
          "guys","hey","welcome","today","video","subscribe","channel"}
VAGUE = {"amazing","incredible","insane","crazy","huge","massive","game","changer","secret",
         "powerful","ultimate","best","revolutionary","mind","blowing","unbelievable"}
CONCRETE = re.compile(r"\b(\d[\d,.]*\s?(%|k|m|x|s|m|h)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?)\b", re.I)
YOU = re.compile(r"\b(you|your|you're|youre|yourself)\b", re.I)
STAKE = re.compile(r"\b(lose|lost|wasting|waste|quit|fail|broke|cost|risk|before|stop|never|die|dying|dead)\b", re.I)
CURIOSITY = re.compile(r"\b(why|how|what|which|until|before|but|nobody|almost|except|reason|actually)\b", re.I)
CLOSED = re.compile(r"\b(because|so that|which means)\b", re.I)

# Spanish mirrors of the lists above. Accents are optional where people often drop them.
FILLER_ES = {"básicamente","literalmente","realmente","solo","sólo","muy","pues","bueno","tipo",
             "chicos","chicas","gente","hola","bienvenidos","bienvenidas","hoy","video","vídeo",
             "suscríbete","suscribete","canal"}
VAGUE_ES = {"increíble","increíbles","impresionante","brutal","loco","locura","enorme","masivo",
            "secreto","poderoso","definitivo","mejor","revolucionario","alucinante","flipante",
            "épico","épica","impactante"}
# Numbers written as words count like digits ("cinco kilómetros" = "5 kilómetros"): scripts for an AI
# voice spell them out so the voice reads them right. A run like "treinta y tres" counts once.
# "un", "una" and "uno" are left out because they are mostly articles.
NUM_WORD = (r"(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince"
            r"|diec?i\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa"
            r"|cien|ciento|cientos|doscient\w+|trescient\w+|cuatrocient\w+|quinient\w+|seiscient\w+"
            r"|setecient\w+|ochocient\w+|novecient\w+|mil|millón|millones)")
CONCRETE_ES = re.compile(r"\b(\d[\d,.]*\s?(%|k|m|x|s|m|h)?|\$\d|\d+\s?(segundo|minuto|hora|d[ií]a|semana|mes|año)(s|es)?"
                         r"|" + NUM_WORD + r"(?:\s+(?:y\s+)?" + NUM_WORD + r")*)\b", re.I)
# Spanish often drops "tú" and puts the person in the verb, so common second-person verbs count too.
YOU_ES = re.compile(r"\b(t[uú]|tus?|te|ti|contigo|usted(es)?|vos|puedes|tienes|sabes|quieres|necesitas"
                    r"|vas|eres|est[aá]s|haces|ves|crees|sigues|deber[ií]as|imagina|mira)\b", re.I)
STAKE_ES = re.compile(r"\b(perder|pierdes|perdiste|perdido|desperdici\w*|renunci\w*|abandon\w*|deja|dejan"
                      r"|fracas\w*|quiebra|cuesta|costar|riesgo|peligro\w*|antes|nunca|morir|muere"
                      r"|mueren|murieron|muert[oa]s?|mortal"
                      # what is at stake in a mystery or danger story: forbidden, deadly, closed, caught
                      r"|prohibid\w*|ilegal\w*|venenos\w*|letal\w*|restringid\w*|cerrad[oa]s?|detien\w*"
                      r"|deten\w*|arrest\w*|dispar\w*|flechas?|desapareci\w*|desaparec\w*|sobreviv\w*"
                      r"|atrapad\w*|extinci[oó]n)\b", re.I)
# "que" without an accent is a plain connector in Spanish, so only the accented question words count.
CURIOSITY_ES = re.compile(r"(\bpor qu[eé]\b|\bcómo\b|\bqué\b|\bcuál(es)?\b|\bhasta\b|\bantes\b|\bpero\b"
                          r"|\bnadie\b|\bcasi\b|\bexcepto\b|\bsalvo\b|\braz[oó]n\b|\ben realidad\b"
                          # the open questions a mystery runs on: hidden, unexplained, refused
                          r"|\bmisterio\w*|\benigma\w*|\binexplicable\w*|\bexplicar\b|\bescond\w*|\bocult\w*"
                          r"|\bse niega\w*|\btodav[ií]a\b|\baún\b)", re.I)
CLOSED_ES = re.compile(r"\b(porque|as[ií] que|lo que significa)\b", re.I)

LANGS = {
    "en": dict(filler=FILLER, vague=VAGUE, concrete=CONCRETE, you=YOU, stake=STAKE,
               curiosity=CURIOSITY, closed=CLOSED, word=r"[a-z0-9'%$.]+", match="match"),
    "es": dict(filler=FILLER_ES, vague=VAGUE_ES, concrete=CONCRETE_ES, you=YOU_ES, stake=STAKE_ES,
               curiosity=CURIOSITY_ES, closed=CLOSED_ES, word=r"[a-záéíóúüñ0-9'%$.]+",
               match="match_es"),
}

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

def words(t, L=LANGS["en"]): return re.findall(L["word"], t.lower())

def specificity(t, L):
    w = words(t, L)
    if not w: return 0
    nums = len(L["concrete"].findall(t))
    vague = sum(1 for x in w if x in L["vague"])
    filler = sum(1 for x in w if x in L["filler"])
    s = 34 + nums * 22 - vague * 16 - filler * 5
    # proper nouns that are not sentence-initial read as named things
    s += min(18, 6 * sum(1 for x in t.split()[1:] if x[:1].isupper()))
    return max(0, min(100, s))

def address(t, L):
    n = len(L["you"].findall(t))
    first = 30 if L["you"].search(" ".join(t.split()[:6])) else 0
    return max(0, min(100, 26 + n * 20 + first))

def stakes(t, L):
    n = len(L["stake"].findall(t))
    return max(0, min(100, 22 + n * 26 + (14 if L["concrete"].search(t) else 0)))

def curiosity(t, L):
    n = len(L["curiosity"].findall(t))
    q = 18 if t.strip().endswith("?") else 0
    # a hook that resolves itself has no gap left
    closed = -18 if L["closed"].search(t) else 0
    return max(0, min(100, 24 + n * 17 + q + closed))

def brevity(t, L):
    n = len(words(t, L))
    if n == 0: return 0
    # 9-24 words is the band a spoken hook lands in at ~150wpm inside 10 seconds
    if 9 <= n <= 24: return 100
    if n < 9:  return max(30, 100 - (9 - n) * 11)
    return max(10, 100 - (n - 24) * 7)

PROPS = [("SPECIFICITY", specificity), ("ADDRESS", address), ("STAKES", stakes),
         ("CURIOSITY", curiosity), ("BREVITY", brevity)]

def classify(t, lang="en"):
    best, hits = None, 0
    key = LANGS[lang]["match"]
    for f in FORMULAS:
        n = sum(1 for p in f.get(key, []) if re.search(p, t, re.I))
        if n > hits: best, hits = f, n
    return (best["name"] if best else "Unclassified"), hits

def score(t, lang="en"):
    L = LANGS[lang]
    parts = {n: fn(t, L) for n, fn in PROPS}
    vals = list(parts.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    name, hits = classify(t, lang)
    return parts, verdict, name, hits

def band(v): return "STRONG" if v >= 72 else "WORKABLE" if v >= 55 else "WEAK"

def report(t, parts, verdict, name, hits, lang="en"):
    print(f"\n  {t.strip()}")
    print(f"  {'-' * min(72, max(20, len(t.strip())))}")
    for k, v in parts.items():
        print(f"    {k:<12} {v:3d}  {'#' * (v // 5)}")
    print(f"    {'VERDICT':<12} {verdict:3d}  {band(verdict)}")
    print(f"    formula      {name}" + (f"  ({hits} pattern{'s' if hits != 1 else ''} matched)" if hits else "  (no formula matched - that is usually a summary, not a hook)"))
    low = min(parts, key=parts.get)
    print(f"    weakest      {low} - {(FIX_ES if lang == 'es' else FIX)[low]}")

FIX = {
 "SPECIFICITY": "swap one adjective for a number, a name or a date",
 "ADDRESS": "say 'you' in the first six words",
 "STAKES": "name what it costs them to keep doing it the current way",
 "CURIOSITY": "cut the half of the sentence that answers itself",
 "BREVITY": "9 to 24 words. Read it out loud and stop where you run out of breath",
}
FIX_ES = {
 "SPECIFICITY": "cambia un adjetivo por un número, un nombre o una fecha",
 "ADDRESS": "háblale de tú en las primeras seis palabras",
 "STAKES": "di qué pierde quien mira si no se queda",
 "CURIOSITY": "corta la mitad de la frase que se responde sola",
 "BREVITY": "de 9 a 24 palabras. Léelo en voz alta y corta donde te falte el aire",
}

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
    force = None
    if "--lang" in a:
        i = a.index("--lang"); force = a[i + 1] if i + 1 < len(a) else None; del a[i:i + 2]
        if force not in ("en", "es", "auto"): print("--lang takes en, es or auto"); sys.exit(1)
        if force == "auto": force = None
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    hook = take(a, "--hook")
    if hook is not None:
        lines = [hook]
    else:
        lines = [l for l in open(first_file(a), encoding="utf-8").read().splitlines() if l.strip()]
    out = []
    for t in lines:
        lang = force or detect(t)
        parts, verdict, name, hits = score(t, lang)
        row = {"hook": t.strip(), "properties": parts, "verdict": verdict,
               "band": band(verdict), "formula": name, "matched": hits}
        if lang == "es": row["lang"] = "es"
        out.append(row)
    out.sort(key=lambda r: -r["verdict"])
    if as_json:
        print(json.dumps([{k: v for k, v in r.items() if k != "matched"} for r in out], indent=1)); return
    for r in out:
        report(r["hook"], r["properties"], r["verdict"], r["formula"], r["matched"], r.get("lang", "en"))
    if len(out) > 1:
        print(f"\n  winner: {out[0]['hook'].strip()}  ({out[0]['verdict']}, {out[0]['band']})\n")

if __name__ == "__main__":
    main()

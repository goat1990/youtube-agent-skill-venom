#!/usr/bin/env python3
"""swipe.py - rank collected videos by how far each beat its OWN channel, then name the formula.

    python3 swipe.py collected.json
    python3 swipe.py collected.json --min 2.0 --json
    python3 swipe.py ytdlp.json        # the file `yt-dlp --flat-playlist -J <channel url>` writes

Input is a list you collected - one object per video:

    [{"channel":"Some Channel","title":"...","views":412000,"url":"...","duration":613}, ...]

Raw view counts rank channel size, not ideas. A 400k video on a 2M-subscriber channel is a normal
Tuesday; a 400k video on a channel whose median is 30k is the thing worth studying. So every video
is scored as a MULTIPLE OF ITS OWN CHANNEL'S MEDIAN, which needs at least four videos per channel
to mean anything - the tool says so rather than quietly ranking on noise.

The formula comes from hooks.json (a copy of yt-script's, kept identical by tests/edge.py), matched against the TITLE. It is a judgement
about the words on screen, not a claim about why the video worked.
"""
import json, os, re, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMULAS = json.load(open(os.path.join(HERE, "hooks.json"), encoding="utf-8"))["hooks"]

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

def classify(title):
    # a Spanish title is matched against the Spanish patterns of each formula
    key = "match_es" if detect(title) == "es" else "match"
    scored = []
    for f in FORMULAS:
        n = sum(1 for p in f.get(key, []) if re.search(p, title, re.I))
        if n: scored.append((n, f["name"]))
    scored.sort(reverse=True)
    return scored[0][1] if scored else "Unclassified"

VIEWS_TEXT = re.compile(r"^([\d.,]+)\s*(k|mil|m|mill|millones|millón|b)?$")

def parse_views(v):
    """Views as a number. Accepts 412000, "412,000", "412.000", "1.2M", "1,2 M", "900K", "45 mil".
    None and empty count as 0, as before. Anything else unreadable returns None."""
    if v is None or v == "": return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = re.sub(r"\b(views|vistas|visualizaciones)\b", "", str(v).lower()).strip()
    m = VIEWS_TEXT.match(s)
    if not m: return None
    num, unit = m.group(1), m.group(2)
    if not unit: return float(re.sub(r"[.,]", "", num) or 0)
    if "," in num and "." in num:  # the last separator is the decimal one
        dec = max(num.rfind(","), num.rfind("."))
        num = re.sub(r"[.,]", "", num[:dec]) + "." + num[dec + 1:]
    num = num.replace(",", ".")
    scale = {"k": 1e3, "mil": 1e3, "m": 1e6, "mill": 1e6, "millones": 1e6, "millón": 1e6, "b": 1e9}[unit]
    try: return float(num) * scale
    except ValueError: return None

def normalize(rows):
    """The pack's own list, {"videos": [...]}, or a yt-dlp file ({"entries": [...]} with view_count,
    nested one level for a channel's tabs). Returns the rows and how many had unreadable views."""
    def flatten(items, owner):
        for r in items:
            if not isinstance(r, dict): continue
            if isinstance(r.get("entries"), list):
                yield from flatten(r["entries"], r.get("channel") or r.get("uploader") or owner)
            else:
                yield r, owner
    owner = None
    if isinstance(rows, dict):
        owner = rows.get("channel") or rows.get("uploader")
        rows = rows.get("videos") or [rows]
    out, unread = [], 0
    for r, own in flatten(rows, owner):
        raw = r["views"] if "views" in r else r.get("view_count")
        n = parse_views(raw)
        if n is None: unread += 1; continue
        out.append(dict(r, views=n, channel=r.get("channel") or r.get("uploader") or own or "?"))
    return out, unread

def main():
    a = sys.argv[1:]
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    lo = float(a[a.index("--min") + 1]) if "--min" in a else 1.5
    files = [x for x in a if not x.startswith("--") and not re.match(r"^[\d.]+$", x)]
    if not files or not os.path.exists(files[0]): print(__doc__); sys.exit(1)
    rows, unread = normalize(json.load(open(files[0], encoding="utf-8")))
    by = {}
    for r in rows: by.setdefault(r.get("channel", "?"), []).append(r)
    out, thin = [], []
    for ch, vids in by.items():
        views = [float(v.get("views", 0) or 0) for v in vids]
        med = statistics.median(views) if views else 0
        if len(vids) < 4:
            thin.append((ch, len(vids)))
            continue
        for v in vids:
            m = (float(v.get("views", 0) or 0) / med) if med else 0
            out.append({"channel": ch, "title": v.get("title", ""), "views": int(v.get("views", 0) or 0),
                        "median": int(med), "multiple": round(m, 2),
                        "formula": classify(v.get("title", "")), "url": v.get("url", "")})
    out = [r for r in out if r["multiple"] >= lo]
    out.sort(key=lambda r: -r["multiple"])
    if as_json:
        res = {"outliers": out, "skipped_thin_channels": thin}
        if unread: res["skipped_unreadable_views"] = unread
        print(json.dumps(res, indent=1)); return
    print(f"\n  {len(rows)} videos across {len(by)} channels, outliers at {lo}x or better\n")
    for r in out[:25]:
        print(f"    {r['multiple']:5.2f}x  {r['views']:>9,}  vs {r['median']:>9,} median   {r['channel'][:22]:<22} {r['title'][:52]}")
        print(f"            {r['formula']}")
    if not out: print("    nothing cleared the threshold - collect more per channel or lower --min")
    if unread: print(f"\n  skipped {unread} video(s) whose view count could not be read")
    if thin:
        print(f"\n  skipped {len(thin)} channel(s) with under 4 videos collected - a median off one or")
        print( "  two videos is not a median: " + ", ".join(f"{c} ({n})" for c, n in thin[:6]))
    counts = {}
    for r in out: counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    if counts:
        print("\n  formulas among the outliers")
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {n:2d}x  {f}")
    print()

if __name__ == "__main__":
    main()

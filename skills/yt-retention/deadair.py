#!/usr/bin/env python3
"""deadair.py - an edit decision list from a timestamped transcript.

    python3 deadair.py transcript.srt            # or .vtt, or whisper .json
    python3 deadair.py transcript.srt --floor 0.35 --json
    python3 deadair.py transcript.srt --lang es  # force Spanish (default: detected from the words)

Finds three things and prints the cuts as a list you can act on, newest problem first:
  DEAD    gaps between spoken cues longer than the floor
  FILLER  cues that are only filler ("um", "so yeah", "basically")
  REPEAT  a sentence restarted - the second take of the same opening

WHAT IT DOES NOT DO. It does not cut the file. It prints an EDL, the total it would remove, and the
runtime you would land on, and you apply it in whatever editor you use. Nothing here touches media.
"""
import json, os, re, sys

FILLER_ONLY = re.compile(r"^[\s,.-]*((um+|uh+|er+|ah+|so|okay|ok|right|yeah|like|anyway|basically|"
                         r"actually|you know|i mean|let me see|hold on)[\s,.-]*)+$", re.I)
FILLER_ONLY_ES = re.compile(r"^[\s,.¿?¡!-]*((e+h+|e+m+|m+h*|este|o sea|pues|bueno|vale|tipo|ok|okey|okay|ya|"
                            r"digamos|a ver|en plan|básicamente|basicamente|la verdad|entonces|sabes)"
                            r"[\s,.¿?¡!-]*)+$", re.I)

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

def parse_ts(s):
    s = s.strip().replace(",", ".")
    p = s.split(":")
    return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2]) if len(p) == 3 else int(p[0]) * 60 + float(p[1])

def load(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    if path.endswith(".json"):
        d = json.loads(raw)
        segs = d.get("segments", []) if isinstance(d, dict) else d  # whisper's dict, or a bare list
        return [(float(s["start"]), float(s["end"]), (s.get("text") or "").strip()) for s in segs]
    # YouTube's own auto-caption file wraps each word in timing tags and repeats the previous line
    # at the top of the next cue. Left alone, that hides fillers and doubles every sentence.
    auto = re.search(r"<\d\d:\d\d:\d\d\.\d{3}>", raw) is not None
    cues, cur = [], None
    for line in raw.splitlines():
        m = re.match(r"\s*(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", line)
        if m:
            cur = [parse_ts(m.group(1)), parse_ts(m.group(2)), []]
            cues.append(cur)
        elif cur is not None and line.strip() and not line.strip().isdigit():
            cur[2].append(re.sub(r"<[^>]+>", "", line).strip() if auto else line.strip())
    if auto:
        last = None
        for c in cues:
            c[2] = [t for t in c[2] if t]
            while c[2] and c[2][0] == last: c[2].pop(0)  # the carried-over line from the cue before
            if c[2]: last = c[2][-1]
    return [(a, b, " ".join(t)) for a, b, t in cues if t]

def declared_lang(path):
    """The language a WebVTT header names ("Language: es"), when it is English or Spanish."""
    head = open(path, encoding="utf-8", errors="replace").read(2000)
    m = re.search(r"^Language:\s*(en|es)\b", head, re.M | re.I)
    return m.group(1).lower() if m else None

def norm(t, rx=r"[^a-z ]"): return re.sub(rx, "", t.lower()).split()

def main():
    a = sys.argv[1:]
    lang = take_lang(a)
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    floor = float(a[a.index("--floor") + 1]) if "--floor" in a else 0.45
    a = [x for x in a if not x.startswith("--") and not re.match(r"^[\d.]+$", x)]
    if not a or not os.path.exists(a[0]): print(__doc__); sys.exit(1)
    cues = load(a[0])
    if not cues: print("no cues found - is this an srt, vtt or whisper json?"); sys.exit(1)
    dur = cues[-1][1]
    lang = lang or declared_lang(a[0]) or detect(" ".join(c[2] for c in cues))
    FILLER = FILLER_ONLY_ES if lang == "es" else FILLER_ONLY
    keep_rx = r"[^a-záéíóúüñ ]" if lang == "es" else r"[^a-z ]"
    cuts = []
    for i, (s, e, t) in enumerate(cues):
        if FILLER.match(t):
            cuts.append({"kind": "FILLER", "start": s, "end": e, "why": t.strip()[:48]})
        if i:
            gap = s - cues[i - 1][1]
            if gap > floor:
                keep = floor / 2
                cuts.append({"kind": "DEAD", "start": round(cues[i - 1][1] + keep, 3),
                             "end": round(s - keep, 3), "why": f"{gap:.2f}s gap"})
        # A restart is compared against the last cue that was actually SPEECH. Comparing against
        # the literal previous cue misses every retake with an "um" between the two attempts, which
        # is most of them.
        if t.strip() and not FILLER.match(t):
            j = i - 1
            while j >= 0 and (FILLER.match(cues[j][2]) or not cues[j][2].strip()): j -= 1
            if j >= 0:
                a1, b1 = norm(cues[j][2], keep_rx)[:5], norm(t, keep_rx)[:5]
                if len(a1) >= 3 and a1 == b1:
                    cuts.append({"kind": "REPEAT", "start": cues[j][0], "end": cues[j][1],
                                 "why": f'restart of "{" ".join(a1)}"'})
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: c["start"])
    removed = sum(c["end"] - c["start"] for c in cuts)
    if as_json:
        out = {"source": a[0], "duration": dur, "cuts": cuts,
               "removed": round(removed, 3), "out": round(dur - removed, 3)}
        if lang == "es": out["lang"] = "es"
        print(json.dumps(out, indent=1)); return
    print(f"\n  {a[0]}   {dur:.2f}s in, {len(cues)} cues, dead-air floor {floor}s\n")
    for c in cuts:
        print(f"    {c['kind']:<7} {c['start']:8.2f} -> {c['end']:8.2f}   {c['end']-c['start']:5.2f}s   {c['why']}")
    print(f"\n  {len(cuts)} cuts, {removed:.2f}s removed, {dur - removed:.2f}s out "
          f"({removed / dur * 100:.1f}% shorter)\n")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""chapters.py - YouTube chapters from a timestamped transcript.

    python3 chapters.py transcript.srt            # or .vtt / whisper .json
    python3 chapters.py transcript.srt --target 8 --json
    python3 chapters.py transcript.srt --lang es   # force Spanish (default: detected from the words)

Prints a description block you can paste straight under a video. YouTube's own rules, enforced here
rather than assumed: the list must start at 00:00, needs at least three entries, and each chapter
must be at least 10 seconds long. A block that breaks any of those silently does not become
chapters, which is why this checks instead of trusting.

Boundaries come from the gaps - the pauses you actually took between sections - scored by how long
the pause was and how much the vocabulary changes across it. It is a first draft you retitle, not a
summariser.
"""
import json, os, re, sys
# deadair.py here is a copy of yt-edit's, so this skill works when installed on its own.
# tests/edge.py fails if the two copies ever differ.
from deadair import load, parse_ts, detect, take_lang, declared_lang  # noqa: E402

STOP = set("the a an of for to in on and or is are was were be been with this that it as at by from "
           "you your i my we our they them he she but so if then than there here what which who how "
           "when where why not no yes do does did just really very like about into over out up down "
           "can could will would should have has had get got make made go going went one two".split())

# Spanish function words of four letters or more (shorter ones never reach the keyword list).
STOP_ES = set("para como este esta estos estas pero porque cuando donde desde hasta sobre entre todo "
              "todos toda todas también ahora aquí allí hacia sino cual cuál quien quién ellos ellas "
              "nosotros ustedes usted tiene tienen tener hace hacer hizo puede pueden poder vamos está "
              "están estar eran fueron sido será sería había mismo misma otro otra otros otras cada "
              "solo sólo bien algo nada mucho muchos mucha muchas poco pocos entonces luego después "
              "antes mientras aunque según hablemos veces cosa cosas última último".split())

def keywords(text, lang="en"):
    if lang == "es":
        return {w for w in re.findall(r"[a-záéíóúüñ']{4,}", text.lower()) if w not in STOP_ES}
    return {w for w in re.findall(r"[a-z']{4,}", text.lower()) if w not in STOP}

def mmss(t):
    t = int(t); h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

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
    target = take(a, "--target", int)
    if target is None: target = 7
    a = [first_file(a)]
    cues = load(a[0])
    if len(cues) < 6: print("too few cues to chapter"); sys.exit(1)
    dur = cues[-1][1]
    lang = lang or declared_lang(a[0]) or detect(" ".join(c[2] for c in cues))
    cand = []
    for i in range(1, len(cues)):
        gap = cues[i][0] - cues[i - 1][1]
        before = " ".join(c[2] for c in cues[max(0, i - 12):i])
        after = " ".join(c[2] for c in cues[i:i + 12])
        kb, ka = keywords(before, lang), keywords(after, lang)
        shift = 1 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0
        cand.append((gap * 1.6 + shift * 3.2, cues[i][0], i))
    cand.sort(reverse=True)
    picked, MIN = [0.0], 10.0
    for _, t, i in cand:
        if len(picked) >= target: break
        if all(abs(t - p) >= MIN for p in picked) and dur - t >= MIN:
            picked.append(t)
    picked.sort()
    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        text = " ".join(c[2] for c in cues if c[0] >= t and c[1] <= end)
        low = text.lower()
        # most frequent first; a tie goes to the word said first, so the same file gives the same titles
        kw = sorted(keywords(text, lang), key=lambda w: (-low.count(w), low.find(w), w))
        title = " ".join(w.capitalize() for w in kw[:3]) or "Section"
        chapters.append({"start": round(t, 2), "label": mmss(t), "draft_title": title,
                         "seconds": round(end - t, 2)})
    ok = len(chapters) >= 3 and chapters[0]["start"] == 0 and all(c["seconds"] >= MIN for c in chapters)
    if as_json:
        out = {"valid": ok, "chapters": chapters}
        if lang == "es": out["lang"] = "es"
        print(json.dumps(out, indent=1)); return
    print()
    for c in chapters: print(f"  {c['label']} {c['draft_title']}")
    print(f"\n  {len(chapters)} chapters"
          f"{'' if ok else '  -- INVALID: YouTube needs 3+, a 00:00 first entry and 10s minimum each'}")
    print("  Retitle every line before pasting. These are the topic words, not your words.\n")

if __name__ == "__main__":
    main()

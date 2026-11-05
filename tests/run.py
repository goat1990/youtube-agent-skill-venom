#!/usr/bin/env python3
"""run.py - check that the six tools still do what they did.

    python3 tests/run.py            # run every check, exit 1 on any failure
    python3 tests/run.py --update   # rewrite the English baseline (only on purpose)
    python3 tests/run.py --show     # print each English output instead of checking it

ENGLISH BASELINE. Every English case runs a tool on a fixture in tests/fixtures/en and compares a
fingerprint of its full output against tests/golden/en.sha256, which was recorded on the original
pack before any change. If English output moves by one character, the check fails.

SPANISH CHECKS. Spanish has no baseline to protect, so each Spanish check states what the tool must
do with Spanish text: detect it, score it on par with the English original, catch its fillers.
"""
import hashlib, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, "skills")
EN = os.path.join(ROOT, "tests", "fixtures", "en")
GOLDEN = os.path.join(ROOT, "tests", "golden", "en.sha256")

def tool(skill, script): return os.path.join(SK, skill, script)

HOOK, TITLE = tool("yt-script", "hookscore.py"), tool("yt-package", "title.py")
DEAD, CHAP = tool("yt-edit", "deadair.py"), tool("yt-chapters", "chapters.py")
RET, SWIPE = tool("yt-retention", "retention.py"), tool("yt-viral", "swipe.py")

EN_CASES = [
    ("hookscore-file", [HOOK, "hooks.txt"]),
    ("hookscore-json", [HOOK, "--json", "hooks.txt"]),
    ("hookscore-one", [HOOK, "--hook", "Stop wasting your first 30 seconds on a channel intro"]),
    ("title-file", [TITLE, "titles.txt"]),
    ("title-pair", [TITLE, "--title", "I Tested 7 AI Editors for 30 Days", "--thumb", "ONLY ONE WORKED"]),
    ("title-dup", [TITLE, "--title", "The Best AI Editor", "--thumb", "BEST EDITOR EVER", "--json"]),
    ("deadair", [DEAD, "transcript.srt"]),
    ("deadair-json", [DEAD, "transcript.srt", "--floor", "0.35", "--json"]),
    ("chapters", [CHAP, "transcript.srt", "--target", "4"]),
    ("chapters-json", [CHAP, "transcript.srt", "--json"]),
    ("retention", [RET, "retention.csv"]),
    ("retention-transcript", [RET, "retention.csv", "--duration", "600", "--transcript", "transcript.srt"]),
    ("retention-json", [RET, "retention.csv", "--json"]),
    ("swipe", [SWIPE, "collected.json", "--min", "2.0"]),
    ("swipe-json", [SWIPE, "collected.json", "--json"]),
]

def run(argv, cwd):
    # chapters.py breaks ties between title words in set order, which Python shuffles per run.
    # A fixed hash seed makes that order repeatable so the output can be compared at all.
    env = dict(os.environ, PYTHONHASHSEED="0")
    p = subprocess.run([sys.executable] + argv, cwd=cwd, env=env, capture_output=True, text=True)
    return f"exit={p.returncode}\n{p.stdout}{p.stderr}"

def fingerprint(out): return hashlib.sha256(out.encode("utf-8")).hexdigest()

def english(update, show):
    got = {name: run(argv, EN) for name, argv in EN_CASES}
    if show:
        for name, out in got.items(): print(f"===== {name}\n{out}")
        return 0
    if update:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w") as fh:
            for name, out in got.items(): fh.write(f"{fingerprint(out)}  {name}\n")
        print(f"rewrote {GOLDEN}"); return 0
    want = dict(reversed(l.split()) for l in open(GOLDEN) if l.strip())
    fails = 0
    for name, out in got.items():
        ok = want.get(name) == fingerprint(out)
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  en  {name}")
    return fails

ES = os.path.join(ROOT, "tests", "fixtures", "es")
SPANISH = []

def check(fn):
    SPANISH.append(fn); return fn

def hookscore_module():
    sys.path.insert(0, os.path.dirname(HOOK))
    import hookscore
    return hookscore

@check
def hooks_spanish_on_par_with_english():
    """Each formula's Spanish example scores within a few points of its English example."""
    h = hookscore_module()
    gaps = [h.score(f["example_es"], "es")[1] - h.score(f["example"], "en")[1] for f in h.FORMULAS]
    mean_gap = sum(abs(g) for g in gaps) / len(gaps)
    return mean_gap <= 5 and max(abs(g) for g in gaps) <= 12, f"mean gap {mean_gap:.1f}, worst {max(gaps, key=abs):+d}"

@check
def hooks_language_detected():
    h = hookscore_module()
    es = sum(h.detect(f["example_es"]) == "es" for f in h.FORMULAS)
    en = sum(h.detect(f["example"]) == "en" for f in h.FORMULAS)
    n = len(h.FORMULAS)
    return es == n and en == n, f"{es}/{n} Spanish and {en}/{n} English examples detected"

@check
def hooks_spanish_ranking():
    """A channel-intro greeting must lose to a real hook, in Spanish as in English."""
    out = json.loads(run([HOOK, "--json", "hooks.txt"], ES).split("\n", 1)[1])
    order = [r["hook"][:12] for r in out]
    greeting = next(r for r in out if r["hook"].startswith("Hola chicos"))
    return order[-1] == "Hola chicos " and greeting["band"] == "WEAK" and all(r.get("lang") == "es" for r in out), \
        f"greeting last at {greeting['verdict']}"

@check
def hooks_lang_option():
    forced = json.loads(run([HOOK, "--lang", "es", "--json", "--hook", "Stop wasting your intro"], EN).split("\n", 1)[1])
    bad = run([HOOK, "--lang", "fr", "--hook", "x"], EN)
    return forced[0].get("lang") == "es" and bad.startswith("exit=1"), "--lang es forces Spanish, --lang fr is refused"

def spanish():
    fails = 0
    for fn in SPANISH:
        try: ok, why = fn()
        except Exception as e: ok, why = False, f"crashed: {type(e).__name__}: {e}"
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  es  {fn.__name__}   ({why})")
    return fails

def main():
    a = sys.argv[1:]
    fails = english("--update" in a, "--show" in a)
    if not ("--update" in a or "--show" in a): fails += spanish()
    print(f"\n  {'all checks passed' if not fails else f'{fails} check(s) failed'}\n")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()

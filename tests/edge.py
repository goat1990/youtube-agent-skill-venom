#!/usr/bin/env python3
"""edge.py - hard cases for the six tools and the eleven skills.

    python3 tests/edge.py

Two kinds of check:
  MUST   what has to keep working. Any failure here exits 1.
  KNOWN  a problem found and not fixed yet. It is reported, not failed, so the suite stays usable.
         When a fix lands, the KNOWN check starts passing and says so: move it to MUST.

Everything is generated in a temporary folder. Nothing here needs network or paid credits.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, "skills")
TMP = tempfile.mkdtemp(prefix="yt-edge-")
TOOLS = {"yt-script": "hookscore.py", "yt-package": "title.py", "yt-edit": "deadair.py",
         "yt-chapters": "chapters.py", "yt-retention": "retention.py", "yt-viral": "swipe.py"}
MUST, KNOWN = [], []

def must(fn): MUST.append(fn); return fn
def known(fn): KNOWN.append(fn); return fn

def write(name, text):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as fh: fh.write(text)
    return p

def run(skill, *args, skills=SK):
    p = subprocess.run([sys.executable, os.path.join(skills, skill, TOOLS[skill])] + list(args),
                       cwd=TMP, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONHASHSEED="0"))
    return p.returncode, p.stdout + p.stderr

def crashed(out): return "Traceback" in out

def ts(x):
    h, m, s = int(x // 3600), int(x % 3600 // 60), x % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"

def srt(cues): return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))

# ---------------------------------------------------------------- MUST: the pack itself

@must
def every_skill_has_matching_frontmatter():
    bad = []
    for f in glob.glob(os.path.join(SK, "*", "SKILL.md")):
        head = open(f, encoding="utf-8").read().split("---")[1]
        name = os.path.basename(os.path.dirname(f))
        if f"name: {name}\n" not in head or "description:" not in head: bad.append(name)
    return not bad, f"{len(glob.glob(os.path.join(SK, '*', 'SKILL.md')))} skills, bad: {bad}"

@must
def every_file_a_skill_names_exists():
    missing = []
    for f in glob.glob(os.path.join(SK, "*", "SKILL.md")):
        d, text = os.path.dirname(f), open(f, encoding="utf-8").read()
        refs = set(re.findall(r"`(\.\./[\w-]+/[\w.-]+|[\w-]+\.(?:py|json))`", text))
        refs |= set(re.findall(r"\]\(((?:\.\./)?[\w./-]+\.(?:json|py|md))\)", text))
        missing += [f"{os.path.basename(d)} -> {r}" for r in refs if not os.path.exists(os.path.join(d, r))]
    return not missing, f"missing: {missing}"

@must
def hook_formulas_complete_in_both_languages():
    hooks = json.load(open(os.path.join(SK, "yt-script", "hooks.json"), encoding="utf-8"))["hooks"]
    keys = {"id", "name", "shape", "example", "fails_when", "match", "example_es", "match_es"}
    bad = [h.get("id") for h in hooks if not keys <= set(h)]
    for h in hooks:
        for p in h["match"] + h["match_es"]: re.compile(p)
    return len(hooks) == 21 and not bad, f"{len(hooks)} formulas, incomplete: {bad}"

@must
def plugin_files_are_valid_json():
    for f in glob.glob(os.path.join(ROOT, ".claude-plugin", "*.json")): json.load(open(f))
    return True, "plugin.json and marketplace.json parse"

# ---------------------------------------------------------------- MUST: hard inputs that work

@must
def hookscore_emoji_and_accents():
    p = write("emoji.txt", "🔥 Tu canal está muerto 💀 y nadie te lo dice 😱\n")
    code, out = run("yt-script", "--json", p)
    r = json.loads(out)[0]
    return code == 0 and r.get("lang") == "es", f"scored {r['verdict']} as Spanish"

@must
def hookscore_very_long_hook():
    p = write("long.txt", " ".join(["you lose your audience"] * 150) + "\n")
    code, out = run("yt-script", "--json", p)
    return code == 0 and json.loads(out)[0]["properties"]["BREVITY"] == 10, "600 words: brevity at its floor"

@must
def title_empty_and_emoji_do_not_crash():
    outs = [run("yt-package", "--title", t) for t in ("", "🔥🔥🔥", "Ñandú ÁÉÍÓÚ " * 12)]
    return all(c == 0 and not crashed(o) for c, o in outs), "empty, emoji-only and 156-char accented titles"

@must
def deadair_windows_line_endings_and_bom():
    p = write("crlf.srt", "﻿" + srt([(0, 2, "hello there friend"), (3, 5, "um")]).replace("\n", "\r\n"))
    code, out = run("yt-edit", "--json", p)
    kinds = sorted(c["kind"] for c in json.loads(out)["cuts"])
    return code == 0 and kinds == ["DEAD", "FILLER"], f"cuts {kinds}"

@must
def deadair_whisper_json():
    p = write("w.json", json.dumps({"segments": [{"start": 0, "end": 2, "text": " eh"},
                                                 {"start": 3, "end": 5, "text": " hola a todos"}]}))
    code, out = run("yt-edit", "--json", "--lang", "es", p)
    return code == 0 and any(c["kind"] == "FILLER" for c in json.loads(out)["cuts"]), "Spanish filler found in whisper json"

@must
def broken_transcripts_fail_politely():
    outs = [run("yt-edit", write("empty.srt", "")),
            run("yt-edit", write("bad.srt", "1\n00:00:01,000 --> garbage\nhola\n")),
            run("yt-chapters", write("short.srt", srt([(0, 2, "a b c")])))]
    return all(c == 1 and not crashed(o) for c, o in outs), "empty, malformed and too-short files: clear message, no crash"

@must
def four_hour_transcript_is_fast():
    words = "la isla prohibida tiene una tribu que nadie visita y los barcos no se acercan".split()
    cues, t = [], 0.0
    for i in range(4000):
        cues.append((t, t + 3, "eh" if i % 37 == 0 else " ".join(words[(i + k) % len(words)] for k in range(8))))
        t += 3 + (2.5 if i % 9 == 0 else 0.2)
    p = write("big.srt", srt(cues))
    start = time.time()
    ok = all(run(s, p)[0] == 0 for s in ("yt-edit", "yt-chapters"))
    took = time.time() - start
    return ok and took < 10, f"{t / 3600:.1f} hours of transcript in {took:.2f}s"

@must
def retention_seconds_axis():
    p = write("secs.csv", "t,ret\n" + "".join(f"{x},{100 - x * 0.08:.1f}\n" for x in range(0, 601, 20)))
    code, out = run("yt-retention", "--json", p)
    return code == 0 and json.loads(out)["points"] == 31, "a 600-second export read point by point"

@must
def swipe_odd_rows():
    zeros = write("zeros.json", json.dumps([{"channel": "A", "title": "t", "views": 0}] * 5))
    empty = write("empty.json", "[]")
    return all(run("yt-viral", p)[0] == 0 for p in (zeros, empty)), "all-zero views and an empty list"

@must
def three_skills_work_alone():
    alone = os.path.join(TMP, "alone")
    ok = []
    for s, arg in (("yt-script", "--hook"), ("yt-package", "--title"), ("yt-edit", None)):
        shutil.copytree(os.path.join(SK, s), os.path.join(alone, s, s))
        args = [arg, "Esto es una prueba de 30 segundos"] if arg else [write("solo.srt", srt([(0, 2, "eh"), (3, 5, "hola")]))]
        ok.append(run(s, *args, skills=os.path.join(alone, s))[0] == 0)
    return all(ok), "hook scorer, title linter and edit list each run from their own folder"

# ---------------------------------------------------------------- KNOWN: found, not fixed yet

def alone(skill, *args):
    d = os.path.join(TMP, "alone2", skill)
    if not os.path.exists(d): shutil.copytree(os.path.join(SK, skill), os.path.join(d, skill))
    return run(skill, *args, skills=d)

@known
def chapters_viral_retention_work_alone():
    """Uploaded alone (as claude.ai Skills does), they look for files in another skill's folder."""
    p = write("ch.srt", srt([(i * 12, i * 12 + 10, f"part {i} talks about thing{i} and topic{i}") for i in range(8)]))
    r = [alone("yt-chapters", p), alone("yt-viral", write("v.json", "[]")),
         alone("yt-retention", write("r.csv", "".join(f"{x},{100 - x}\n" for x in range(10))), "--transcript", p)]
    return all(c == 0 for c, _ in r), "; ".join(o.strip().splitlines()[-1][:60] for c, o in r if c)

@known
def swipe_reads_ytdlp_output():
    """The skill says to collect with yt-dlp, whose file holds 'entries' and 'view_count'."""
    p = write("ytdlp.json", json.dumps({"channel": "X", "entries": [
        {"title": f"v{i}", "view_count": 1000 * (i + 1) ** 2, "url": "u"} for i in range(6)]}))
    code, out = run("yt-viral", "--json", "--min", "1.0", p)
    n = len(json.loads(out)["outliers"]) if code == 0 else 0
    return n > 0, f"{n} videos read from a yt-dlp file"

@known
def swipe_views_written_as_text():
    p = write("text.json", json.dumps([{"channel": "A", "title": "t", "views": v} for v in ("1.2M", "900K", "45,000", "3000")]))
    code, out = run("yt-viral", p)
    return code == 0, "crash: " + out.strip().splitlines()[-1][:70] if code else "read"

@known
def deadair_whisper_list_json():
    p = write("wl.json", json.dumps([{"start": 0, "end": 2, "text": "um"}, {"start": 3, "end": 5, "text": "hello there"}]))
    code, out = run("yt-edit", p)
    return code == 0, out.strip().splitlines()[-1][:70]

@known
def deadair_youtube_auto_captions():
    """YouTube's own auto-caption file wraps words in timing tags, which hides fillers."""
    vtt = ("WEBVTT\nKind: captions\nLanguage: es\n\n"
           "00:00:00.000 --> 00:00:02.000\nhola<00:00:00.500><c> a</c><00:00:00.900><c> todos</c>\n\n"
           "00:00:03.000 --> 00:00:04.000\neh<00:00:03.500><c> bueno</c>\n")
    code, out = run("yt-edit", "--json", write("auto.vtt", vtt))
    return any(c["kind"] == "FILLER" for c in json.loads(out)["cuts"]), "filler hidden inside timing tags"

@known
def retention_semicolon_decimal_comma_csv():
    """Not confirmed that a Spanish-language Studio exports this way; spreadsheets do."""
    rows = "".join(f"{x};{100 - x * 0.6:.1f}\n".replace(".", ",") for x in range(0, 101, 5))
    code, out = run("yt-retention", write("es.csv", "Posición (%);Retención (%)\n" + rows))
    return code == 0, out.strip().splitlines()[-1][:70]

@known
def options_in_any_order():
    secs = write("o.csv", "".join(f"{x},{100 - x * 0.08:.1f}\n" for x in range(0, 601, 20)))
    titles = write("t.txt", "Mi título\n")
    r = [run("yt-retention", "--duration", "600", secs), run("yt-package", "--thumb", "HOLA", titles)]
    return all(c == 0 for c, _ in r), "option before the file prints the help instead of running"

@known
def missing_option_value_is_explained():
    r = [run("yt-script", "--hook"), run("yt-package", "--title", "x", "--thumb"),
         run("yt-edit", "--floor", "abc", write("f.srt", srt([(0, 2, "hola")])))]
    return not any(crashed(o) for _, o in r), f"{sum(crashed(o) for _, o in r)} of 3 end in a Python error"

@known
def missing_file_is_an_error():
    code, _ = run("yt-script", "no-such-file.txt")
    return code != 0, f"exit {code} for a file that does not exist"

@known
def chapter_titles_same_every_run():
    p = write("same.srt", srt([(i * 12, i * 12 + 10, f"part {i} talks about thing{i} and topic{i}") for i in range(8)]))
    outs = set()
    for seed in ("1", "2", "3"):
        q = subprocess.run([sys.executable, os.path.join(SK, "yt-chapters", "chapters.py"), p], cwd=TMP,
                           capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED=seed))
        outs.add(q.stdout)
    return len(outs) == 1, f"{len(outs)} different title sets in 3 runs"

def main():
    fails = 0
    print()
    for fn in MUST:
        try: ok, why = fn()
        except Exception as e: ok, why = False, f"crashed: {type(e).__name__}: {e}"
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  must   {fn.__name__}   ({why})")
    fixed = 0
    for fn in KNOWN:
        try: ok, why = fn()
        except Exception as e: ok, why = False, f"crashed: {type(e).__name__}: {e}"
        fixed += ok
        print(f"  {'FIXED' if ok else 'known'} known  {fn.__name__}   ({why})")
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n  {len(MUST) - fails}/{len(MUST)} must-pass checks passed, {len(KNOWN) - fixed} known problems open"
          + (f", {fixed} now fixed: move them to MUST" if fixed else "") + "\n")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()

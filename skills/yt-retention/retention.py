#!/usr/bin/env python3
"""retention.py - read a YouTube Studio audience-retention export and find the leaks.

    python3 retention.py retention.csv
    python3 retention.py retention.csv --transcript transcript.srt   # names what was said at each drop
    python3 retention.py retention.csv --json

Get the file from Studio: Analytics -> a video -> Engagement -> the audience-retention chart ->
the download icon -> "Audience retention". Two columns, a position (percent or seconds) and a
percentage still watching.

It reports three things, because they are three different problems with three different fixes:
  HOOK LEAK    what you lost in the first 30 seconds
  CLIFFS       single steep drops - a specific moment people left at
  SLIDE        the steady bleed rate across the flat middle

With --transcript it prints what you were saying at each cliff, which is the only version of this
report you can act on without scrubbing the video yourself.
"""
import csv, json, os, re, sys

def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        head = fh.read(4096); fh.seek(0)
        # Spreadsheets set to Spanish (and most of Europe) save with ";" between columns and a
        # decimal comma: "12;87,5". Otherwise a comma separates columns or thousands, as before.
        semi = head.count(";") > head.count(",") / 2 and ";" in head
        for r in csv.reader(fh, delimiter=";" if semi else ","):
            nums = []
            for c in r:
                c = c.strip().replace("%", "")
                c = c.replace(".", "").replace(",", ".") if semi else c.replace(",", "")
                try: nums.append(float(c))
                except ValueError: nums.append(None)
            vals = [n for n in nums if n is not None]
            if len(vals) >= 2: rows.append((vals[0], vals[1]))
    return rows

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
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    tr, dur = take(a, "--transcript"), take(a, "--duration", float)
    if tr and not os.path.exists(tr): sys.exit(f"file not found: {tr}")
    files = [first_file(a)]
    rows = load_csv(files[0])
    if len(rows) < 8: print("could not read at least 8 data points from that csv"); sys.exit(1)
    xs = [r[0] for r in rows]; ys = [r[1] for r in rows]
    pct_axis = max(xs) <= 100.5
    def at(x): return (x / 100.0 * dur) if (pct_axis and dur) else x
    start = ys[0] or 100.0
    # HOOK: the first 30 seconds, or the first 10% when the axis is a percentage and we have no duration
    cutoff = 30.0 if not pct_axis else (30.0 / dur * 100 if dur else 10.0)
    hook_end = min((y for x, y in rows if x <= cutoff), default=start)
    hook_leak = start - hook_end
    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    drops.sort(reverse=True)
    cliffs = [{"from": round(a1, 2), "to": round(b1, 2), "lost": round(d, 2),
               "at_seconds": round(at(a1), 1) if (not pct_axis or dur) else None}
              for _, a1, b1, d in drops[:5] if d > 0.8]
    mid = [d for d, x0, _, _ in [(r[0], r[1], r[2], r[3]) for r in drops] if x0 > cutoff]
    slide = sum(mid) / len(mid) if mid else 0
    said = {}
    if tr and os.path.exists(tr):
        from deadair import load as load_cues  # a copy of yt-edit's, kept identical by tests/edge.py
        cues = load_cues(tr)
        for c in cliffs:
            if c["at_seconds"] is None: continue
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]
    out = {"points": len(rows), "start": start, "hook_leak": round(hook_leak, 2),
           "end": ys[-1], "cliffs": cliffs, "slide_per_unit": round(slide, 3), "said": said}
    if as_json: print(json.dumps(out, indent=1)); return
    print(f"\n  {files[0]}   {len(rows)} points   {ys[0]:.1f}% -> {ys[-1]:.1f}%\n")
    verdict = "healthy" if hook_leak < 25 else "leaking" if hook_leak < 40 else "severe"
    print(f"  HOOK LEAK   {hook_leak:.1f}% lost in the opening   [{verdict}]")
    print(f"              under 25 is healthy for this length. Fix the first line before anything else.\n")
    print("  CLIFFS      the moments people actually left")
    for c in cliffs:
        where = f"{c['at_seconds']:.0f}s" if c["at_seconds"] is not None else f"{c['from']}"
        print(f"    -{c['lost']:5.1f}%  at {where:>8}" + (f"   \"{said.get(str(c['from']),'')}\"" if said else ""))
    if not cliffs: print("    none steeper than 0.8% - the loss is all slide, not moments")
    print(f"\n  SLIDE       {slide:.3f}% per unit across the middle")
    print( "              a flat slide is pacing, not content. Cut the middle, do not rewrite it.\n")

if __name__ == "__main__":
    main()

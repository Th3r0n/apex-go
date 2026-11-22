"""Lockstep A/B: feed each golden session's inputs to two bot commands (one line, wait for the answer)
and report where their actions differ (first differing line per session, and a count).
usage: python -I abdiff.py GOLDEN.jsonl.gz CMD_A_JSON CMD_B_JSON [session-substring]"""
import gzip, json, queue, subprocess, sys, threading

def start(cmd):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    q = queue.Queue()
    def rd():
        for raw in p.stdout:
            q.put(raw.decode().rstrip("\n"))
        q.put(None)
    threading.Thread(target=rd, daemon=True).start()
    return p, q

def ask(p, q, line, expect):
    try:
        p.stdin.write((line + "\n").encode()); p.stdin.flush()
    except OSError:
        return None
    try:
        return q.get(timeout=20 if expect else 0.25)
    except queue.Empty:
        return None

def strip(o):
    if not o or not o.startswith("{"):
        return o
    d = json.loads(o)
    d.pop("debug", None)
    return json.dumps(d, sort_keys=True)

golden, ca, cb = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
filt = sys.argv[4] if len(sys.argv) > 4 else ""
sessions = {}
with gzip.open(golden, "rt", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("type") == "meta":
            continue
        sessions.setdefault(r["s"], []).append(r)
for name, recs in sessions.items():
    if recs[0].get("nomount") or filt not in name:
        continue
    recs.sort(key=lambda r: r["i"])
    pa, qa = start(ca)
    pb, qb = start(cb)
    n = same = 0
    first = None
    for r in recs:
        a = ask(pa, qa, r["in"], r["expect"])
        b = ask(pb, qb, r["in"], r["expect"])
        if not r["expect"]:
            continue
        n += 1
        if strip(a) == strip(b):
            same += 1
        elif first is None:
            first = (r["i"], a, b)
    for p in (pa, pb):
        try:
            p.stdin.close(); p.wait(timeout=10)
        except Exception:
            p.kill()
    print(f"{name}: {same}/{n} identical actions")
    if first:
        print(f"   first diff i={first[0]}\n   A: {first[1]}\n   B: {first[2]}")

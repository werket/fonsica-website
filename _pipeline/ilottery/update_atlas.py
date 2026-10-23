#!/usr/bin/env python3
"""Keep the iLottery Atlas current: rebuild, check and publish when the research data changes.

The research bot works in its own container and pushes deliveries to the private repo
werket/fonsica-insights. launchd (com.fonsica.ilottery-atlas) runs this every hour, at login
and when the local copy changes: it fast-forwards ~/Projects/fonsica-insights from GitHub
(this Mac only reads that repo), then rebuilds. Adam chose (2026-10-23) to publish
automatically when every check passes. Anything else stops the run, leaves a report in
_pipeline/logs/ and sends a notification; nothing is pushed.

  python3 _pipeline/ilottery/update_atlas.py             rebuild and write locally, no git
  python3 _pipeline/ilottery/update_atlas.py --publish   ... then commit and push the atlas files
  python3 _pipeline/ilottery/update_atlas.py --dry-run   report what would change, write nothing

Checks before anything goes out: the build guard rails (build_atlas.py), every sentence on
the page (claims.py), and git: only the atlas files are committed, and only on top of
origin/main, so the job never publishes anyone else's unfinished work.
"""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_atlas as ba  # noqa: E402
import claims  # noqa: E402

REPO = ba.REPO
STATE_DIR = os.path.join(HERE, "data")              # gitignored (_pipeline/*/data/)
STATE = os.path.join(STATE_DIR, "update-state.json")
LOCK = os.path.join(STATE_DIR, "update.lock")
LOG_DIR = os.path.join(REPO, "_pipeline", "logs")   # gitignored
PUBLISH_PATHS = ["insights/ilottery/atlas.json", "insights/ilottery/index.html", "images/insights/ilottery"]
COMMIT_PREFIX = "Update iLottery Atlas data"
QUIET_SECONDS = 180      # a delivery is finished when no input has changed for this long
MAX_WAIT_SECONDS = 1200


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def notify(message):
    script = f'display notification {json.dumps(message)} with title "iLottery Atlas"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def fingerprint(data):
    h = hashlib.sha256()
    for rel in ba.INPUTS:
        path = os.path.join(data, rel)
        st = os.stat(path) if os.path.exists(path) else None
        h.update(f"{rel}|{st.st_size if st else '-'}|{st.st_mtime_ns if st else '-'}\n".encode())
    return h.hexdigest()


NETWORK_ERRORS = ("could not resolve", "connection", "timed out", "network is unreachable", "ssh: connect")
PULL_WARNING = os.path.join(STATE_DIR, "pull-warning.json")


def sync_from_github(data):
    """Fast-forward the research repo to what the bot pushed from its container.

    The bot is the only writer; this Mac only reads. Returns True when new commits arrived.
    Without a network the local copy is used as it is. A copy that can no longer
    fast-forward (local edits, rewritten history) is reported at most once a day.
    """
    repo = os.path.dirname(os.path.abspath(data))
    if not os.path.isdir(os.path.join(repo, ".git")):
        return False
    head = lambda: subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    before = head()
    r = subprocess.run(["git", "-C", repo, "pull", "--ff-only", "--quiet"], capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        after = head()
        if after != before:
            log(f"pulled {before}..{after} from GitHub")
        return after != before
    reason = ((r.stderr or r.stdout).strip().splitlines() or ["git pull failed"])[-1]
    if any(n in reason.lower() for n in NETWORK_ERRORS):
        log(f"GitHub not reachable, using the local copy ({reason})")
        return False
    log(f"could not fast-forward the research repo: {reason}")
    try:
        last = json.load(open(PULL_WARNING, encoding="utf-8")).get("at", 0)
    except (OSError, ValueError):
        last = 0
    if time.time() - last > 86400:
        notify("Forskningsrepot kan inte hämta botens senaste leverans (lokala ändringar?). Se _pipeline/logs.")
        json.dump({"at": time.time(), "reason": reason}, open(PULL_WARNING, "w", encoding="utf-8"))
    return False


def wait_for_quiet(data):
    """A delivery writes many files; wait until the folder has been still for a while."""
    waited = 0
    while waited < MAX_WAIT_SECONDS:
        times = [os.path.getmtime(os.path.join(data, rel)) for rel in ba.INPUTS if os.path.exists(os.path.join(data, rel))]
        idle = time.time() - max(times) if times else QUIET_SECONDS
        if idle >= QUIET_SECONDS:
            return
        log(f"data changed {idle:.0f}s ago, waiting for the delivery to finish")
        time.sleep(30)
        waited += 30


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(fp, status):
    json.dump({"fingerprint": fp, "status": status, "at": datetime.now().isoformat(timespec="seconds")},
              open(STATE, "w", encoding="utf-8"), indent=1)


def comparable(atlas):
    a = json.loads(json.dumps(atlas))
    a.get("meta", {}).pop("built", None)
    return a


def summarize(old, new):
    lines = []

    def num(label, path):
        a, b = ba.lookup(old, path), ba.lookup(new, path)
        if a != b:
            lines.append(f"{label}: {a} → {b}")

    num("Data hämtad", "meta.data_retrieved")
    num("Spel i katalogen", "catalog.games")
    num("Lobbyer", "catalog.lotteries")
    num("Spel med RTP", "catalog.rtp_games")
    num("Studior", "studios.count")
    num("Lotterier i registret", "register.lotteries")
    for t in ("einstants", "online", "planned", "offline"):
        num(f"Status {t}", f"register.totals.{t}")
    num("USA-jurisdiktioner med eInstants", "register.us.einstant_jurisdictions")
    num("Rader i prisplaner", "pack.prize_rows")
    num("Kontrakt", "pack.contracts")
    old_tiles = {t["code"]: t["tier"] for t in old["register"]["tiles"]}
    for t in new["register"]["tiles"]:
        if old_tiles.get(t["code"]) != t["tier"]:
            lines.append(f"Kartan: {t['code']} {old_tiles.get(t['code'])} → {t['tier']}")
    old_growth = {s["id"]: s["points"][-1] for s in old["growth"]}
    for s in new["growth"]:
        last, before = s["points"][-1], old_growth.get(s["id"])
        if before != last:
            lines.append(f"Tillväxt {s['label']}: senaste punkt FY{last['fy']} = {last['v']} (grad {last['grade']})")
    old_moves = {(m["lottery"], m["vendor"]) for m in old["moves"]}
    for m in new["moves"]:
        if (m["lottery"], m["vendor"]) not in old_moves:
            lines.append(f"Ny händelse 2026: {m['lottery']} · {m['vendor']}")
    if not lines:
        lines.append("Bara mindre ändringar i underliggande värden")
    return lines


def tiers_changed(old, new):
    return {t["code"]: t["tier"] for t in old["register"]["tiles"]} != {t["code"]: t["tier"] for t in new["register"]["tiles"]}


def write_report(status, lines, candidates=()):
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"ilottery-{datetime.now():%Y%m%d-%H%M%S}.md")
    body = [f"# iLottery Atlas: uppdatering {datetime.now():%Y-%m-%d %H:%M}", "", f"**Status:** {status}", ""]
    body += [f"- {line}" for line in lines]
    if candidates:
        body += ["", "## Nya verifierade avtal 2026 som saknar publik text",
                 "Publiceras inte automatiskt. Lägg till dem i MOVES i build_atlas.py med en engelsk mening.", ""]
        body += [f"- {c['lottery']} · {c['vendor']} · {c['when']} · {c['status']} · {c['url']}" for c in candidates]
    open(path, "w", encoding="utf-8").write("\n".join(body) + "\n")
    return path


def stop(fp, title, lines, retry=False):
    """End the run without publishing. Unless retry, remember the data so it is not reported twice."""
    report = write_report(f"Stoppad: {title}", lines)
    log(f"STOPPED: {title}: {'; '.join(lines)} (report: {report})")
    notify(f"Publiceringen stoppades: {title}. Se rapporten i _pipeline/logs.")
    if not retry:
        save_state(fp, f"blocked: {title}")
    return 1


def git_preflight():
    """None when it is safe to commit on top of origin/main, else the reason not to."""
    if git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "main":
        return "repot står inte på main"
    if git("fetch", "-q", "origin", "main").returncode:
        return "kunde inte hämta origin/main (nätverk?)"
    if git("diff", "--cached", "--quiet").returncode:
        return "det finns redan stagade ändringar i repot"
    if git("status", "--porcelain", "--", *PUBLISH_PATHS).stdout.strip():
        return "atlasfilerna har lokala ändringar som inte är publicerade"
    ahead = git("log", "--format=%s", "origin/main..main").stdout.split("\n")
    ahead = [s for s in ahead if s]
    if any(not s.startswith(COMMIT_PREFIX) for s in ahead):
        return "main har opushade commits från annat arbete"
    behind = int(git("rev-list", "--count", "main..origin/main").stdout.strip() or 0)
    if behind and git("merge", "--ff-only", "-q", "origin/main").returncode:
        return "kunde inte snabbspola main till origin/main"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="path to the fonsica-data folder (default: $FONSICA_DATA)")
    ap.add_argument("--publish", action="store_true", help="commit and push the atlas files")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--force", action="store_true", help="run even if the data looks unchanged")
    args = ap.parse_args()
    os.makedirs(STATE_DIR, exist_ok=True)

    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another update is running")
            return 0

        data = ba.find_data_dir(args.data)
        pulled = False if args.dry_run else sync_from_github(data)
        fp = fingerprint(data)
        if fp == load_state().get("fingerprint") and not args.force:
            log("no new data")
            return 0
        if not pulled:   # a pull lands a whole commit at once; local writes may still be going on
            wait_for_quiet(data)
            fp = fingerprint(data)

        try:
            new = ba.build(data)
        except ba.BuildRefused as e:
            return stop(fp, "bygget vägrade", [str(e)])
        except Exception as e:  # a broken delivery must never take the job down silently
            return stop(fp, "bygget kraschade", [repr(e)])

        failures = claims.check(new)
        if failures:
            return stop(fp, "texten på sidan stämmer inte längre med datan", failures)

        old = json.load(open(ba.OUT, encoding="utf-8"))
        candidates = ba.candidate_moves(data)
        if comparable(old) == comparable(new):
            log("built and checked, nothing public changed")
            if not args.dry_run:
                save_state(fp, "unchanged")
            return 0

        changes = summarize(old, new)
        if args.dry_run:
            log("dry run, would publish:\n  " + "\n  ".join(changes))
            for c in candidates:
                log(f"candidate move: {c['lottery']} / {c['vendor']} / {c['when']}")
            return 0

        if args.publish and (reason := git_preflight()):
            return stop(fp, "git", [reason], retry=True)

        ba.write(new)
        if tiers_changed(old, new):
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_panel_image.py")], capture_output=True, text=True)
            if r.returncode:
                changes.append("Bräd-bilden kunde inte ritas om: " + (r.stderr.strip().splitlines() or ["okänt fel"])[-1])
            else:
                changes.append("Bräd-bilden ritades om")

        status = "Skriven lokalt (inte publicerad)"
        if args.publish:
            git("add", "--", *PUBLISH_PATHS)
            staged = [p for p in git("diff", "--cached", "--name-only").stdout.split("\n") if p]
            stray = [p for p in staged if not any(p == a or p.startswith(a + "/") for a in PUBLISH_PATHS)]
            if stray:
                git("reset", "-q", "--", *stray)
                return stop(fp, "oväntade filer i committen", stray, retry=True)
            if not staged:
                log("nothing to commit after writing")
                save_state(fp, "unchanged")
                return 0
            day = new["meta"]["data_retrieved"] or datetime.now().strftime("%Y-%m-%d")
            if git("commit", "-q", "-m", f"{COMMIT_PREFIX} - {day}").returncode:
                return stop(fp, "commit misslyckades", ["git commit gav fel"], retry=True)
            sha = git("rev-parse", "--short", "HEAD").stdout.strip()
            push = git("push", "-q", "origin", "main")
            if push.returncode:
                return stop(fp, "push misslyckades", [f"commit {sha} ligger lokalt", push.stderr.strip()[-300:]], retry=True)
            status = f"Publicerad (commit {sha})"

        save_state(fp, status)
        report = write_report(status, changes, candidates)
        log(f"{status}: {'; '.join(changes)} (report: {report})")
        extra = f" {len(candidates)} nya avtal behöver text." if candidates else ""
        notify(f"{status}. {len(changes)} ändringar.{extra}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

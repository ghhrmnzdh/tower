"""A fictional Tower state for the site: a working day on a product team.
Every surface on the page (the web replicas and the real TUI frames) reads
this one fixture, so the numbers agree everywhere. Times are relative to NOW."""
import json, os, sys, time

HOME = os.path.expanduser("~")


def build(now=None):
    now = now or time.time()
    T = lambda s: now - s
    code = HOME + "/code/"

    def sub(aid, typ, status, act, desc, tools, ago_s, result=None):
        return {"agent_id": aid, "type": typ, "status": status, "activity": act,
                "result": result, "since": T(ago_s), "started": T(ago_s),
                "desc": desc, "tools": tools}

    def sess(sid, name, model, fam, effort, status, since, activity, *,
             branch="main", title=None, prompt=None, result=None, pending=None,
             ticks=(0, 0, 0, 0), subs=(), turn=None, started=3600, health=None,
             tty="ttys001", kind="interactive"):
        return {"session_id": sid, "pid": 40000 + len(sid) * 37 + ord(sid[0]),
                "kind": kind, "model": model, "model_family": fam, "effort": effort,
                "context": None, "project_name": name, "cwd": code + name,
                "git_root": code + name, "git_branch": branch, "title": title,
                "last_prompt": prompt, "status": status, "status_since": T(since),
                "turn_at": T(turn) if turn else None, "activity": activity,
                "result": result, "pending_tool": pending, "tty": tty,
                "focusable": True, "guarded": True, "last_activity": T(min(since, 4)),
                "started": T(started),
                "ticks": {"tools_done": ticks[0], "files": ticks[1],
                          "errors": ticks[2], "subagents": ticks[3]},
                "subagents": list(subs),
                "health": health or {"level": "ok", "reasons": []},
                "dismissed": False}

    sessions = [
        sess("a1checkout", "checkout-web", "claude-opus-5-5", "opus", "high",
             "working", 1260, "Editing src/payments/refund.ts",
             branch="feat/partial-refunds", turn=1260, started=9200,
             title="Partial refunds in checkout",
             prompt="add partial refunds to checkout: a line-item picker, the Stripe call, and tests",
             ticks=(148, 9, 1, 3), tty="ttys002",
             subs=[sub("s1", "Explore", "done", "found 11 callers", "map every caller of chargeCustomer", 23, 1100,
                       result="11 call sites, 2 in webhooks"),
                   sub("s2", "code-reviewer", "working", "Reading src/payments/refund.ts", "review the refund diff", 14, 420),
                   sub("s3", "test-runner", "working", "Running pnpm test payments", "run the payments suite", 6, 150)]),
        sess("b2ledger", "ledger-api", "claude-fable-5-1", "fable", "max",
             "pending_tool", 95, "Bash: psql -f migrations/0042_split_ledger.sql",
             branch="split-ledger", started=14400, title="Split the ledger table by currency",
             prompt="split the ledger table by currency without downtime; write the migration and the backfill",
             pending={"name": "Bash", "detail": "psql -f migrations/0042_split_ledger.sql"},
             ticks=(212, 6, 0, 2), tty="ttys003",
             subs=[sub("s4", "general-purpose", "done", "backfill plan ready", "plan the backfill in batches", 31, 2400,
                       result="batches of 50k, 14 min")]),
        sess("c3ios", "ios-app", "claude-sonnet-5-5", "sonnet", "medium",
             "asking", 240, "Should offline drafts sync over cellular too?",
             branch="offline-drafts", started=5400, title="Offline drafts",
             prompt="make drafts work offline and sync when the network comes back",
             ticks=(64, 7, 0, 0), tty="ttys004"),
        sess("d4pipe", "data-pipeline", "claude-opus-5-5", "opus", "high",
             "working", 2280, "Running dbt run --select orders_daily",
             branch="late-events", turn=2280, started=21600,
             title="Late-arriving events in orders_daily",
             prompt="orders_daily undercounts on Mondays. find out why and fix the model",
             ticks=(301, 4, 2, 4), tty="ttys005",
             subs=[sub("s5", "Explore", "done", "found the cause", "trace the late-arriving events", 40, 2000,
                       result="events land up to 26 h late"),
                   sub("s6", "general-purpose", "working", "Backfilling 2026-09-01..30", "backfill September's partitions", 58, 900),
                   sub("s7", "general-purpose", "working", "Writing tests/orders_daily_late.sql", "add a test for late events", 12, 300),
                   sub("s8", "code-reviewer", "done", "approved", "review the window change", 9, 600, result="approved")]),
        sess("e5docs", "docs-site", "claude-haiku-5-5", "haiku", "low",
             "done", 70, "done", branch="api-v3", started=3000,
             title="Docs for the v3 API",
             prompt="update every page that still shows the v2 API",
             result="rewrote 14 pages for the v3 API, links check clean",
             ticks=(96, 14, 0, 0), tty="ttys006"),
        sess("f6infra", "infra", "claude-sonnet-5-5", "sonnet", "high",
             "working", 520, "thinking…", branch="edge-cache", turn=520, started=7200,
             title="Cache static assets at the edge",
             prompt="put the static assets behind the CDN with a one-year cache and immutable names",
             ticks=(41, 3, 0, 1), tty="ttys007",
             subs=[sub("s9", "Explore", "working", "Reading modules/edge/main.tf", "find every bucket behind the CDN", 8, 200)]),
        sess("g7mkt", "marketing-site", "claude-sonnet-5-5", "sonnet", "medium",
             "idle", 6200, "", started=30000, ticks=(0, 0, 0, 0), tty="ttys008"),
        sess("h8tokens", "design-tokens", "claude-haiku-5-5", "haiku", "low",
             "idle", 11000, "", started=40000, ticks=(0, 0, 0, 0), tty="ttys009"),
    ]
    needs = [{"session_id": "b2ledger", "reason": "pending_tool", "since": T(95)},
             {"session_id": "c3ios", "reason": "asking", "since": T(240)},
             {"session_id": "e5docs", "reason": "done", "since": T(70)}]
    events = []
    for sid, a, b, ago_s in [("d4pipe", "idle", "working", 2280), ("a1checkout", "idle", "working", 1260),
                             ("f6infra", "idle", "working", 520), ("c3ios", "working", "asking", 240),
                             ("b2ledger", "working", "pending_tool", 95), ("e5docs", "working", "done", 70)]:
        events.append({"t": T(ago_s), "session_id": sid, "from": a, "to": b})

    hist = []
    import math, random
    rnd = random.Random(7)
    for i in range(60):
        t = T((60 - i) * 10)
        hist.append({"t": t, "internet_ms": 9 + 4 * math.sin(i / 5) + rnd.random() * 5,
                     "api_ms": 186 + 22 * math.sin(i / 7) + rnd.random() * 30})
    recent = []
    for i in range(50):
        sec = int(now) - (50 - i) * 5
        lt = time.localtime(sec)
        host = ["api.anthropic.com", "api.anthropic.com", "statsig.anthropic.com",
                "registry.npmjs.org", "api.anthropic.com", "github.com"][i % 6]
        recent.append({"t": time.strftime("%H:%M:%S", lt), "host": host,
                       "kind": "claude" if "anthropic" in host else "other", "action": "allowed"})

    days = []
    for k, c in enumerate([38.4, 52.1, 47.9, 12.3, 8.6, 61.7, 44.2]):
        d = time.strftime("%Y-%m-%d", time.localtime(now - (6 - k) * 86400))
        days.append({"day": d, "tokens": int(c * 410000), "cost": c})

    s = {
        "location": {"status": "OK", "ip": "142.114.9.2", "city": "Toronto", "region": "Ontario",
                     "country_name": "Canada", "country_cc": "CA", "in_target": True,
                     "isp": "Bell Canada", "error": None},
        "guard": {"target_cc": "CA", "enforce": True, "block_all": False, "allowed": 4812,
                  "blocked": 7, "proxy_port": 8888, "proxy_up": True, "claude_allowed": True,
                  "net_ok": True, "pending": False, "holding": 0},
        "routing": {"installed": True, "intended": True},
        "keepawake": {"on": True, "mode": "lid", "holding": True, "reason": "agents working", "grace_left": None},
        "settings": {"theme": "Daybreak", "country": "CA", "plan_week_tokens": 400000000, "plan_enabled": True},
        "recent": recent,
        "usage": {
            "session": {"tokens": 6120400, "input": 4100, "output": 88200, "cache": 6028100,
                        "cost": 18.42, "msgs": 140, "since": T(9200)},
            "today": {"tokens": 18100200, "cost": 44.20},
            "week": {"tokens": 106000000, "cost": 265.20, "since": T(86400 * 6 + 3600 * 5), "basis": "plan"},
            "pace": {"tokens_per_active_hr": 2900000, "active_hrs": 6, "projected_week_tokens": 120000000,
                     "projected_week_cost": 301.0, "live_tpm": 61000},
            "headroom": {"used_week_tokens": 106000000, "plan_week_tokens": 400000000, "pct": 26.5},
            "byModel": [{"model": "claude-opus-5-5", "tokens": 62000000, "cost": 171.30, "pct": 58.5},
                        {"model": "claude-fable-5-1", "tokens": 21000000, "cost": 61.20, "pct": 19.8},
                        {"model": "claude-sonnet-5-5", "tokens": 18000000, "cost": 27.10, "pct": 17.0},
                        {"model": "claude-haiku-5-5", "tokens": 5000000, "cost": 5.60, "pct": 4.7}],
            "series": days,
        },
        "plan": {"ok": True, "updated": T(120),
                 "session": {"pct": 34, "resets": "", "resets_at": now + 3600 * 2 + 14 * 60},
                 "week": {"pct": 47, "resets": "", "resets_at": now + 86400 * 2 + 3600 * 4},
                 "fable": {"pct": 22, "resets": "", "resets_at": now + 86400 * 2 + 3600 * 4},
                 "last24h": {"requests": 1840, "sessions": 9}, "billing": "subscription",
                 "windows": {
                     "24h": {"requests": 1840, "sessions": 9,
                             "tips": [{"pct": 62, "text": "Give \"general-purpose\" subagents a cheaper model", "hint": None},
                                      {"pct": 41, "text": "Start fresh when you switch tasks", "hint": "run /clear"}],
                             "top": {"subagents": [{"name": "general-purpose", "pct": 34}, {"name": "Explore", "pct": 12},
                                                   {"name": "code-reviewer", "pct": 7}],
                                     "skills": [{"name": "/review", "pct": 3}],
                                     "mcp_servers": [{"name": "github", "pct": 2}]}},
                     "7d": {"requests": 11900, "sessions": 41,
                            "tips": [{"pct": 71, "text": "Give \"general-purpose\" subagents a cheaper model", "hint": None},
                                     {"pct": 48, "text": "Stop sessions you no longer need", "hint": "some ran 8 hours or more"},
                                     {"pct": 30, "text": "Save max effort for hard tasks", "hint": None}],
                            "top": {"subagents": [{"name": "general-purpose", "pct": 38}, {"name": "Explore", "pct": 14},
                                                  {"name": "code-reviewer", "pct": 9}, {"name": "test-runner", "pct": 4}]}}}},
        "net": {"status": "online", "raw_status": "online", "reason": None,
                "internet_ms": hist[-1]["internet_ms"], "api_ms": hist[-1]["api_ms"], "api_error": None,
                "last_change": T(3 * 3600), "checked": T(2), "history": hist,
                "speedtest": {"running": False, "progress": 0.0, "mbps_down": 412.0, "ms": 9.0,
                              "bytes": 25000000, "at": T(600), "error": None, "cooldown_until": 0.0}},
        "agents": {"sessions": sessions, "needs_you": needs,
                   "collisions": [],
                   "summary": {"working": 4, "needs_you": 2, "done_today": 41, "top_tier": "fable",
                               "unguarded": 0, "pinned": 0},
                   "events": events,
                   "meta": {"source": "hooks", "lsof_ok": True, "parse_errors": 0, "claude_versions": []}},
        "apps": {"desktop": {"installed": True, "running": True, "guarded": True, "pid": 51200},
                 "web": {"available": True, "browser": "Google Chrome", "running": False, "guarded": None}},
        "procs": {"daemon_pid": 42426, "keepawake_pid": 42490},
        "platform": "macos", "version": "4.0", "ts": now,
    }
    return s


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=1)

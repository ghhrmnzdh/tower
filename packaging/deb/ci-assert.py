#!/usr/bin/env python3
"""Assert the shape of a freshly-started daemon's state.json.

Split out of ci-smoke.sh because a heredoc inside a YAML block scalar cannot
be dedented to column 0, and indented Python is a syntax error. Reads
$HOME/.tower/state.json and checks only what the *packaging* is responsible
for — that the daemon runs on this Ubuntu's Python and knows where it is.
"""
import json
import os
import sys

path = os.path.join(os.path.expanduser("~"), ".tower", "state.json")
with open(path) as f:
    s = json.load(f)

fails = []
if s.get("platform") != "linux":
    fails.append(f'platform is {s.get("platform")!r}, expected "linux"')
if not s.get("guard", {}).get("proxy_up"):
    fails.append(f'proxy is not up: {s.get("guard")}')
# Fail-closed: a container has no confirmed country, so nothing may pass.
if s.get("guard", {}).get("claude_allowed"):
    fails.append("claude_allowed is true with no confirmed location — "
                 "the gate is not fail-closed")
if s.get("agents", {}).get("meta") is None:
    fails.append("agent monitor produced no meta")

if fails:
    for f_ in fails:
        print("FAIL:", f_)
    sys.exit(1)

print(f'  platform={s["platform"]} '
      f'port={s["guard"]["proxy_port"]} '
      f'location={s["location"]["status"]} '
      f'claude_allowed={s["guard"]["claude_allowed"]}')

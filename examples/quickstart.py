"""Read the service, then sign an account in and look at its stash.

    python examples/quickstart.py

Needs DARKERAPI_KEY in the environment for the second half. The first half runs
without one.
"""

import os
import time

from darkerapi import DarkerAPI, DarkerAPIError

# ---- public: no key needed -------------------------------------------------

api = DarkerAPI()

status = api.status()
print(f"service: {status['status']}")
print(f"game build: {status['build']['version']}")

if status["status"] == "maintenance":
    window = status["game"]["maintenance"]
    print(f"  IRONMACE has the game down; about {window['remainingSec'] // 60} min left")
    raise SystemExit

patch = api.patch()["patch"]
if patch:
    print(f"live patch: {patch['version']} — {patch['files']} files")

# ---- with a key ------------------------------------------------------------

key = os.environ.get("DARKERAPI_KEY")
if not key:
    print("\nSet DARKERAPI_KEY to run the signed-in half.")
    raise SystemExit

api = DarkerAPI(key)
print(f"\nsigned in as {api.me()['username']}")
print(f"credits used: {api.usage()['creditsUsed']}")

label = os.environ.get("DARKERAPI_ACCOUNT", "main")

try:
    api.sessions.create(label=label, account_key=label)
except DarkerAPIError as e:
    print(f"could not open a session: {e}")
    # `from None`: the message above is the useful part, and a traceback through
    # the library adds nothing for someone reading an example.
    raise SystemExit from None

s = api.session(label)

# Opening a session starts the login; it does not finish it. `state` is the one
# action that works throughout, and it costs the game nothing to poll.
print("waiting for the lobby", end="", flush=True)
for _ in range(60):
    state = s.state()["state"]
    if state == "in_lobby":
        break
    if state == "disconnected":
        print("\nthe login dropped — check the account's credentials")
        raise SystemExit
    print(".", end="", flush=True)
    time.sleep(2)
else:
    print("\ngave up waiting")
    raise SystemExit

print(f"\nin the lobby as {s.state()['nick']}")
print(f"gold: {s.gold()}")

stash = s.inventory.stash()
items = stash.get("items", [])
print(f"stash: {len(items)} items")
for item in items[:10]:
    # `label` is the display name throughout the API; `tag` is the stable id.
    print(f"  {item.get('label') or item.get('tag', '?')}")

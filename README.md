# darkerapi-python

The official Python client for [DarkerAPI](https://darkerapi.com) — read your stash,
watch the marketplace and trade in **Dark and Darker** over HTTP.

```python
from darkerapi import DarkerAPI

api = DarkerAPI("dnd_your_key_here")

api.sessions.create(label="main", account_key="main")
stash = api.session("main").inventory.stash()
```

## Install

```bash
pip install darkerapi
```

Or straight from the repository, for an unreleased change:

```bash
pip install git+https://github.com/DarkerAPI/darkerapi-python
```

One dependency: [httpx](https://www.python-httpx.org/). Python 3.9+.

## No key? Still useful

The service, build and marketplace endpoints are public, so this works with no
arguments at all:

```python
from darkerapi import DarkerAPI

api = DarkerAPI()

api.status()  # is the service up, and is the game up?
api.status_history()  # 90 days of uptime, per component
api.patch()  # the live game build and every patch recorded
api.market()  # current marketplace prices
api.items(q="ruby")  # search the item catalog
```

`status()` returns one of `up`, `degraded`, `down` or `maintenance` — and
`maintenance` means IRONMACE has taken the game down on purpose, which is not an
outage of this service.

Prices as they change, without polling:

```python
for tick in api.market_stream():
    print(tick)
```

## Getting a key

Sign up at [darkerapi.com](https://darkerapi.com), then create a key in the
dashboard, or from here:

```python
api = DarkerAPI()  # a session cookie also works
key = api.keys.create("my-bot")["key"]  # shown once — store it now
```

The free tier is dashboard-only. API keys need a paid plan; see
`api.plans()`.

## Signing a game account in

Save the account once, then open sessions by label:

```python
api.accounts.save(
    "main", username="steamuser", password="…", shared_secret="…"
)  # for Steam Guard codes
```

Opening a session **starts** a login; it does not finish it. Poll until the
account reaches the lobby — `state()` is the one action that works before the
login completes, and it costs the game nothing:

```python
import time

api.sessions.create(label="main", account_key="main")
s = api.session("main")

while s.state()["state"] != "in_lobby":
    time.sleep(2)
```

If the account has more than one character, pick one first:

```python
chars = s.characters()["characters"]
s.enter(chars[0]["characterId"])
```

## The 69 actions

Everything a signed-in account can do is grouped the way the API documents it:

```python
s = api.session("main")

s.state()  # session & character
s.gold()
s.characters()

s.inventory.carried()  # inventory & stash
s.inventory.stash()
s.inventory.sort_stash(dry_run=True)  # see the moves before making them

s.merchants.list()  # merchants
s.merchants.stock(merchant_id="…")

s.market.enter()  # marketplace
s.market.list(item_id="Ruby", rarity="legendary")
s.market.best_price("Ruby")
s.market.claim_all()

s.trade.channels()  # trading
s.trade.whisper("Grimsby", "still selling?")

s.party.find("Grimsby")  # party
s.dungeon.enter()  # dungeons
```

Anything not wrapped — or added to the API after this release — is reachable by
name, with the API's own argument spelling:

```python
s.action("createCharacter", nickName="Grimsby", characterClass="Fighter", gender=0)
```

`api.docs()` lists every action, its parameters and an example.

## Errors

One exception per documented error code, all under `DarkerAPIError`:

```python
from darkerapi import ActionFailed, CreditsExhausted, PlanLimit

try:
    s.market.buy(listing_id, price)
except ActionFailed as e:
    print("the game refused it:", e.message)  # already sold, not enough gold…
except CreditsExhausted:
    print("out of credits for this period")
except PlanLimit as e:
    print("plan does not allow that:", e.message)
```

`ActionFailed` is the interesting one: the request was fine and you were allowed
to make it, but the *game* said no.

## Credits

Requests made with a bearer key are metered; the dashboard is not. Most calls
cost 1 credit. The exceptions are worth knowing:

| Call | Credits |
| --- | --- |
| `sessions.create`, `sessions.reconnect` | 25 |
| `proxies.test`, `proxies.switch` | 10 |
| any game action | 2 |
| everything else | 1 |

`api.usage()` shows what you have spent and when the period resets.

## Self-hosting

```python
api = DarkerAPI("dnd_…", base_url="http://127.0.0.1:8765/api/v1")
```

## A word of warning

DarkerAPI is an independent third-party tool, not affiliated with IRONMACE Co.,
Ltd. or Valve Corporation. Automating a game account is very likely to breach the
game's own terms, and an account using a tool like this one may be suspended or
deleted without warning. That is your decision to make.

## Releasing

Publishing runs from `.github/workflows/publish.yml` on a version tag, using
**PyPI Trusted Publishing** — there is no API token in the repo, in secrets, or
on anyone's laptop.

**One-time setup**, on [pypi.org](https://pypi.org) with an account that has 2FA
enabled. Go to *Your projects → Publishing → Add a new pending publisher* and
enter exactly:

| Field | Value |
| --- | --- |
| PyPI Project Name | `darkerapi` |
| Owner | `DarkerAPI` |
| Repository name | `darkerapi-python` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

"Pending" is the right choice while the project does not exist yet — PyPI
creates it on the first successful upload and claims the name then.

**Each release:**

1. Bump `version` in `pyproject.toml` *and* `__version__` in
   `src/darkerapi/__init__.py`. They must match; the second one is what the
   `User-Agent` reports.
2. Commit, then `./scripts/release.sh`, which tags the commit and pushes the tag
   — the push is what publishes. The workflow runs the tests on 3.9 and 3.13,
   builds, checks the metadata, then uploads.

The script does two things a bare `git push` does not. It refuses a version that
is already on PyPI, and it checks the two version strings against each other
before tagging — a mismatch ships a package whose `User-Agent` lies about
itself, and a version number can only ever be used once. And it pushes as the
`darkerapi-bot` machine account rather than as you: GitHub attributes a workflow
run — and the deployment record the publish job creates — to *whoever pushed the
tag*, never to the identity in `git config`. Push one yourself and the
repository's Deployments panel reads "by a maintainer", on a public page,
permanently.

A tag rather than a GitHub Release for the same reason: a Release is stamped
with the name of whoever clicked the button. A tag carries only its tagger,
which here is `DarkerAPI <noreply@darkerapi.com>`.

### The release account

One-time, and the same account serves every DarkerAPI repository.

1. Create a GitHub account, `darkerapi-bot`. The org itself holds the plain
   `darkerapi` name — users and organisations share one namespace — so a machine
   account cannot have it. A `+` alias on your own address is enough to sign up
   with: `bot@example.com`.
2. Invite it to the `DarkerAPI` org with **Write** on this repository, and
   accept the invitation from the bot account.
3. Signed in as the bot, create a **classic** personal access token under
   *Settings → Developer settings → Personal access tokens → Tokens (classic)*,
   with one scope ticked: **`public_repo`**. That is enough to push a tag to a
   public repository and grants nothing else. A fine-grained token can also work,
   but its *Repository access* radio defaults to "Public repositories
   (read-only)" — leave it there and the push fails with `contents=write` while
   every permission box further down the page still looks correct.
4. Put it where `scripts/release.sh` looks for it:
   ```bash
   security add-generic-password -s darkerapi-bot-github-pat \
     -a darkerapi-bot -w 'github_pat_…' -U
   ```

The token stays in the Keychain — never in the repository, never in
`.git/config`, and never on a command line. Before it tags anything
`release.sh` asks GitHub which account the stored token belongs to, and stops if
the answer is not `darkerapi-bot`; a token that quietly turned out to be yours
is the one failure that would defeat the point of the exercise.

## Licence

MIT. See [LICENSE](LICENSE).

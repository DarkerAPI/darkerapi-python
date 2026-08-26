#!/usr/bin/env bash
#
# Cut a release: tag the current commit and push the tag, which is what starts
# .github/workflows/publish.yml.
#
# The push is deliberately made with a *machine account's* credential rather
# than yours. GitHub stamps a workflow run — and the deployment record the
# publish job creates — with the account that pushed, not with the identity in
# `git config`. Push it yourself and the Deployments panel reads "by a maintainer"
# on a public page, permanently. Push it as darkerapi-bot and it reads
# "by darkerapi-bot".
#
# The token lives in the macOS Keychain, never in this repository and never in
# .git/config. One-time setup is in the README, under "Releasing".
#
set -euo pipefail

BOT_USER="darkerapi-bot"
KEYCHAIN_SERVICE="darkerapi-bot-github-pat"

cd "$(dirname "$0")/.."

# A tag is permanent once pushed, and PyPI will not let a version number be
# re-uploaded once it is burnt. Both are worth a few seconds of checking.
branch=$(git rev-parse --abbrev-ref HEAD)
[ "$branch" = "main" ] || { echo "release: on '$branch', expected main" >&2; exit 1; }
git diff --quiet && git diff --cached --quiet ||
  { echo "release: working tree is dirty" >&2; exit 1; }

# Two places carry the version and they must agree — the second one is what the
# User-Agent reports, so a mismatch ships a package that lies about itself.
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)
dunder=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/darkerapi/__init__.py | head -1)
[ -n "$version" ] || { echo "release: no version in pyproject.toml" >&2; exit 1; }
[ "$version" = "$dunder" ] ||
  { echo "release: pyproject.toml says $version, __init__.py says $dunder" >&2; exit 1; }

tag="v$version"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null &&
  { echo "release: $tag already exists locally" >&2; exit 1; }

# The registry is the real authority on whether a version is still free, and it
# is a much better error than a failed publish job ten minutes from now.
if curl -sfS -o /dev/null "https://pypi.org/pypi/darkerapi/$version/json" 2>/dev/null; then
  echo "release: darkerapi $version is already on PyPI — bump the version" >&2
  exit 1
fi

token=$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$BOT_USER" -w 2>/dev/null) ||
  { echo "release: no token in the Keychain for $BOT_USER — see README" >&2; exit 1; }

# Guard against the whole point of this script quietly failing: if the stored
# token belongs to the wrong account, the push still succeeds and the release is
# attributed to a human again. Check before creating the tag, not after.
who=$(curl -sS -H "Authorization: Bearer $token" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        https://api.github.com/user |
      python3 -c 'import json,sys; print(json.load(sys.stdin).get("login",""))')
[ "$who" = "$BOT_USER" ] ||
  { echo "release: Keychain token belongs to '${who:-unknown}', not $BOT_USER" >&2; exit 1; }

# The tagger comes from `git config`, which for this repository is
# DarkerAPI <noreply@darkerapi.com>.
git tag -a "$tag" -m "$version"

# `credential.helper=` with an empty value clears the inherited list first, so a
# credential stored for your own account cannot be used instead. The token is
# passed through the environment rather than the command line, which keeps it
# out of `ps` and out of the shell history.
export BOT_USER token
if ! git \
  -c credential.helper= \
  -c credential.helper='!f() { test "$1" = get && printf "username=%s\npassword=%s\n" "$BOT_USER" "$token"; }; f' \
  push origin "$tag"
then
  # Leaving a tag behind that was never pushed makes the next run fail on the
  # "already exists locally" check for no good reason.
  git tag -d "$tag" >/dev/null
  echo "release: push failed, local tag removed" >&2
  exit 1
fi

echo "release: pushed $tag as $BOT_USER"
echo "         https://github.com/DarkerAPI/darkerapi-python/actions"

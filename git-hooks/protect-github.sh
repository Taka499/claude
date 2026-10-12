#!/bin/sh
# Protect main, master and develop of a GitHub repository with a ruleset: no deletion, no force push.
#
#   git-hooks/protect-github.sh OWNER/REPOSITORY
#
# Only those two rules, so ordinary pushes of merges still work, including a workflow that pushes
# develop directly; no pull-request requirement. No bypass actors, so the rules bind admins too.
# Re-running updates the ruleset by name instead of adding a second one.
#
# Needs gh, so run it outside the sandbox (global CLAUDE.md § Git Operations). GitHub's free plans
# enforce rulesets on public repositories only: for a private repository GitHub answers 403
# "Upgrade to GitHub Pro or make this repository public", and the local hook is the only guard.
set -eu

repository=$1
name="protect main, master and develop"
body='{"name": "'"$name"'", "target": "branch", "enforcement": "active", "bypass_actors": [],
 "conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/master", "refs/heads/develop"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}'

existing=$(gh api "repos/$repository/rulesets" --jq ".[] | select(.name == \"$name\") | .id")
if [ -n "$existing" ]; then
    printf '%s' "$body" | gh api --method PUT "repos/$repository/rulesets/$existing" --input - > /dev/null
    echo "protect-github: updated ruleset $existing on $repository"
else
    printf '%s' "$body" | gh api --method POST "repos/$repository/rulesets" --input - > /dev/null
    echo "protect-github: created the ruleset on $repository"
fi

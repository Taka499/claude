"""Tests for the reference-transaction hook and its two installers. Run: python3 -m unittest discover -s git-hooks"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "protect-branches.sh")
PROTECT_GITHUB = os.path.join(HERE, "protect-github.sh")

# Real git, isolated from the machine's own configuration (a global core.hooksPath, signing, …).
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")


class Repo:
    def __init__(self, path: str):
        self.path = path

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", self.path, *args], env=ENV, capture_output=True,
                              text=True, timeout=30, check=check)

    def tip(self, branch: str) -> str:
        return self.git("rev-parse", branch).stdout.strip()

    def commit(self, message: str) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def install(self) -> subprocess.CompletedProcess:
        return subprocess.run(["sh", INSTALL, self.path], env=ENV, capture_output=True,
                              text=True, timeout=30, check=False)


class ProtectedRepoTest(unittest.TestCase):
    """A repository with develop holding one commit and the hook installed."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repo(os.path.join(self.temp.name, "repo"))
        subprocess.run(["git", "init", "-q", "-b", "develop", self.repo.path], env=ENV, check=True)
        self.repo.commit("root")
        installed = self.repo.install()
        self.assertEqual(installed.returncode, 0, installed.stderr)

    def tearDown(self):
        self.temp.cleanup()

    def assertRefused(self, result: subprocess.CompletedProcess, branch: str, before: str):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protect-branches: refusing", result.stderr)
        self.assertEqual(self.repo.tip(branch), before)

    def feature_with_commit(self, name: str = "feat") -> None:
        """A branch with one commit that changes a file, so a revert of it has something to undo."""
        self.repo.git("switch", "-q", "-c", name)
        with open(os.path.join(self.repo.path, f"{name}.txt"), "w") as handle:
            handle.write(name)
        self.repo.git("add", f"{name}.txt")
        self.repo.git("commit", "-q", "-m", f"work on {name}")


class RefusedUpdates(ProtectedRepoTest):

    def test_a_direct_commit_on_develop(self):
        before = self.repo.tip("develop")
        self.assertRefused(self.repo.git("commit", "--allow-empty", "-m", "x", check=False), "develop", before)

    def test_a_fast_forward_over_plain_commits(self):
        before = self.repo.tip("develop")
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        self.assertRefused(self.repo.git("merge", "--ff-only", "feat", check=False), "develop", before)

    def test_a_rewind_by_reset(self):
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        before = self.repo.tip("develop")
        self.assertRefused(self.repo.git("reset", "--hard", "HEAD~1", check=False), "develop", before)

    def test_a_force_move_from_another_branch(self):
        before = self.repo.tip("develop")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("branch", "-f", "develop", "feat", check=False), "develop", before)

    def test_an_amend(self):
        before = self.repo.tip("develop")
        self.assertRefused(self.repo.git("commit", "--amend", "--allow-empty", "-m", "y", check=False),
                           "develop", before)

    def test_a_revert_made_on_the_branch_itself(self):
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        before = self.repo.tip("develop")
        self.assertRefused(self.repo.git("revert", "--no-edit", "-m", "1", "HEAD", check=False), "develop", before)

    def test_deleting_it(self):
        before = self.repo.tip("develop")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("branch", "-D", "develop", check=False), "develop", before)

    def test_main_and_master_alike(self):
        for name in ("main", "master"):
            with self.subTest(branch=name):
                self.repo.git("branch", name, "develop")
                self.repo.git("switch", "-q", name)
                before = self.repo.tip(name)
                self.assertRefused(self.repo.git("commit", "--allow-empty", "-m", "x", check=False), name, before)
                self.repo.git("switch", "-q", "develop")

    @unittest.skipUnless(os.path.exists(os.path.dirname(os.path.abspath(__file__)).upper()),
                         "only a case-insensitive filesystem maps refs/heads/DEVELOP onto develop")
    def test_a_differently_cased_name_on_a_case_insensitive_filesystem(self):
        """Security review of PR B (2026-10-12): `update-ref refs/heads/DEVELOP` moved develop on APFS."""
        before = self.repo.tip("develop")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("update-ref", "refs/heads/DEVELOP", "feat", check=False), "develop", before)

    @unittest.skipUnless(os.path.exists(os.path.dirname(os.path.abspath(__file__)).upper()),
                         "only a case-insensitive filesystem folds refs/heads/maſter onto master")
    def test_a_unicode_folded_name_on_a_case_insensitive_filesystem(self):
        """Security review of the case fix (2026-10-12): `update-ref refs/heads/maſter` (long s) moved master."""
        self.repo.git("branch", "master", "develop")
        before = self.repo.tip("master")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("update-ref", "refs/heads/ma\u017fter", "feat", check=False), "master", before)

    def test_a_plain_commit_dressed_as_a_merge_by_a_replacement(self):
        """Codex review of PR B (2026-10-12): `git replace --graft` made a plain commit pass as a merge."""
        before = self.repo.tip("develop")
        self.repo.git("switch", "-q", "-c", "side")
        self.repo.commit("side work")
        self.feature_with_commit()
        self.repo.git("replace", "--graft", "feat", "develop", "side")
        self.assertRefused(self.repo.git("update-ref", "refs/heads/develop", "feat", check=False), "develop", before)

    def test_a_merge_that_takes_the_old_tip_only_as_second_parent(self):
        """Codex review of PR B (2026-10-12): all-merge first parents, but the old tip off the first-parent line."""
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        before = self.repo.tip("develop")
        self.repo.git("switch", "-q", "-c", "other", "develop~1")
        self.repo.git("switch", "-q", "-c", "z")
        self.repo.commit("z work")
        self.repo.git("switch", "-q", "other")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge z", "z")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge develop", "develop")
        self.assertRefused(self.repo.git("update-ref", "refs/heads/develop", "other", check=False), "develop", before)

    @unittest.skipUnless(os.path.exists(os.path.dirname(os.path.abspath(__file__)).upper()),
                         "only a case-insensitive filesystem folds refs/heads/maſter onto master")
    def test_a_folded_alias_of_a_packed_branch(self):
        """Codex review of PR B, round 2 (2026-10-12): with master packed, the alias looked like a new branch."""
        self.repo.git("branch", "master", "develop")
        self.repo.git("pack-refs", "--all", "--prune")
        before = self.repo.tip("master")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("update-ref", "refs/heads/ma\u017fter", "feat", check=False), "master", before)

    def test_deleting_a_packed_branch(self):
        before = self.repo.tip("develop")
        self.repo.git("pack-refs", "--all", "--prune")
        self.feature_with_commit()
        self.assertRefused(self.repo.git("branch", "-D", "develop", check=False), "develop", before)

    def test_from_a_linked_worktree(self):
        """The hook lives in the shared hooks directory, so a worktree is covered too."""
        before = self.repo.tip("develop")
        self.repo.git("switch", "-q", "-c", "parking")  # git itself refuses to move a checked-out branch
        worktree = os.path.join(self.temp.name, "wt")
        self.repo.git("worktree", "add", "-q", "-b", "feat2", worktree)
        Repo(worktree).commit("work in the worktree")
        self.assertRefused(Repo(worktree).git("branch", "-f", "develop", "feat2", check=False), "develop", before)


class AllowedUpdates(ProtectedRepoTest):

    def test_a_merge_commit(self):
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        result = self.repo.git("merge", "--no-ff", "-m", "merge feat", "feat", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_fast_forward_over_merge_commits(self):
        """What pulling a branch that took pull-request merges on GitHub looks like."""
        self.feature_with_commit()
        self.repo.git("switch", "-q", "-c", "stage", "develop")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        self.repo.git("switch", "-q", "develop")
        result = self.repo.git("merge", "--ff-only", "stage", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_revert_brought_in_by_a_merge(self):
        self.feature_with_commit()
        self.repo.git("switch", "-q", "develop")
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        merge = self.repo.tip("develop")
        self.repo.git("switch", "-q", "-c", "revert-feat")
        self.repo.git("revert", "--no-edit", "-m", "1", merge)
        self.repo.git("switch", "-q", "develop")
        result = self.repo.git("merge", "--no-ff", "-m", "merge revert-feat", "revert-feat", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_creating_a_protected_branch(self):
        result = self.repo.git("branch", "main", "develop", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_repositorys_first_commit(self):
        fresh = Repo(os.path.join(self.temp.name, "fresh"))
        subprocess.run(["git", "init", "-q", "-b", "main", fresh.path], env=ENV, check=True)
        self.assertEqual(fresh.install().returncode, 0)
        result = fresh.git("commit", "--allow-empty", "-m", "first", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_anything_on_other_branches(self):
        self.feature_with_commit()
        self.repo.commit("more")
        result = self.repo.git("reset", "--hard", "HEAD~2", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_packing_refs(self):
        """Codex review of PR B, round 2: pack-refs deletes each loose copy after packing it; gc runs it."""
        self.repo.git("branch", "master", "develop")
        before = (self.repo.tip("develop"), self.repo.tip("master"))
        result = self.repo.git("pack-refs", "--all", "--prune", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo.tip("develop"), self.repo.tip("master")), before)
        self.assertEqual(self.repo.git("gc", "--quiet", check=False).returncode, 0)

    def test_switching_branches(self):
        self.repo.git("switch", "-q", "-c", "feat")
        result = self.repo.git("switch", "develop", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_users_documented_bypass(self):
        result = self.repo.git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "x", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


class Installer(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repo(os.path.join(self.temp.name, "repo"))
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo.path], env=ENV, check=True)
        self.hook = os.path.join(self.repo.path, ".git", "hooks", "reference-transaction")

    def tearDown(self):
        self.temp.cleanup()

    def test_rerunning_updates_its_own_copy(self):
        self.assertEqual(self.repo.install().returncode, 0)
        result = self.repo.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(self.hook, os.X_OK))

    def test_refuses_to_overwrite_a_foreign_hook(self):
        os.makedirs(os.path.dirname(self.hook), exist_ok=True)
        with open(self.hook, "w") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        result = self.repo.install()
        self.assertNotEqual(result.returncode, 0)
        with open(self.hook) as handle:
            self.assertEqual(handle.read(), "#!/bin/sh\nexit 0\n")

    def test_refuses_when_core_hooks_path_redirects_git(self):
        self.repo.git("config", "core.hooksPath", ".husky")
        result = self.repo.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("core.hooksPath", result.stderr)
        self.assertFalse(os.path.exists(self.hook))

    def test_refuses_when_core_hooks_path_is_set_empty(self):
        """Codex review of PR B (2026-10-12): an empty core.hooksPath also makes git ignore the hooks directory."""
        self.repo.git("config", "core.hooksPath", "")
        result = self.repo.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(self.hook))

    def test_refuses_a_foreign_hook_that_merely_mentions_the_marker(self):
        os.makedirs(os.path.dirname(self.hook), exist_ok=True)
        foreign = "#!/bin/sh\n# composed hook; see protect-branches: Taka499/claude\nexit 0\n"
        with open(self.hook, "w") as handle:
            handle.write(foreign)
        self.assertNotEqual(self.repo.install().returncode, 0)
        with open(self.hook) as handle:
            self.assertEqual(handle.read(), foreign)

    def test_refuses_outside_a_repository(self):
        result = subprocess.run(["sh", INSTALL, self.temp.name], env=ENV, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)


class GitHubRuleset(unittest.TestCase):
    """protect-github.sh against a stub `gh` that records its calls."""

    def run_with_existing(self, existing_id: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as temp:
            log = os.path.join(temp, "calls.jsonl")
            stub = os.path.join(temp, "gh")
            with open(stub, "w") as handle:
                handle.write(
                    "#!/bin/sh\n"
                    f'if [ "$3" = "--jq" ]; then printf "%s" "{existing_id}"; exit 0; fi\n'
                    f'python3 -c \'import json,sys; print(json.dumps({{"args": sys.argv[1:], "body": sys.stdin.read()}}))\' "$@" >> "{log}"\n'
                )
            os.chmod(stub, 0o755)
            env = dict(ENV, PATH=f"{temp}:{os.environ['PATH']}")
            result = subprocess.run(["sh", PROTECT_GITHUB, "owner/repo"], env=env, capture_output=True,
                                    text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(log) as handle:
                return [json.loads(line) for line in handle]

    def test_creates_the_ruleset_when_none_exists(self):
        calls = self.run_with_existing("")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["args"][:4], ["api", "--method", "POST", "repos/owner/repo/rulesets"])
        body = json.loads(calls[0]["body"])
        self.assertEqual({rule["type"] for rule in body["rules"]}, {"deletion", "non_fast_forward"})
        self.assertEqual(set(body["conditions"]["ref_name"]["include"]),
                         {"refs/heads/main", "refs/heads/master", "refs/heads/develop"})
        self.assertEqual(body["bypass_actors"], [])
        self.assertEqual(body["enforcement"], "active")

    def test_updates_the_existing_ruleset_by_id(self):
        calls = self.run_with_existing("42")
        self.assertEqual(calls[0]["args"][:4], ["api", "--method", "PUT", "repos/owner/repo/rulesets/42"])


if __name__ == "__main__":
    unittest.main()

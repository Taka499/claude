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
INSTALL_GLOBAL = os.path.join(HERE, "install-global.sh")
HOOK = os.path.join(HERE, "reference-transaction")

# Real git, isolated from the machine's own configuration (a global core.hooksPath, signing, …).
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")


class Repo:
    def __init__(self, path: str):
        self.path = path

    def git(self, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", self.path, *args], env=dict(ENV, **(env or {})), capture_output=True,
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

    def test_a_plain_commit_dressed_as_a_merge_by_grafts(self):
        """Security review after merge (2026-10-12): the legacy graft file rewrites parents as replacements do."""
        before = self.repo.tip("develop")
        self.repo.git("switch", "-q", "-c", "side")
        self.repo.commit("side work")
        self.feature_with_commit()
        graft = f"{self.repo.tip('feat')} {before} {self.repo.tip('side')}\n"
        with open(os.path.join(self.repo.path, ".git", "info", "grafts"), "w") as handle:
            handle.write(graft)
        self.assertRefused(self.repo.git("update-ref", "refs/heads/develop", "feat", check=False), "develop", before)
        os.remove(os.path.join(self.repo.path, ".git", "info", "grafts"))
        elsewhere = os.path.join(self.temp.name, "grafts")
        with open(elsewhere, "w") as handle:
            handle.write(graft)
        self.assertRefused(self.repo.git("update-ref", "refs/heads/develop", "feat", check=False,
                                         env={"GIT_GRAFT_FILE": elsewhere}), "develop", before)

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
        self.assertNotIn("hint:", result.stderr)  # the hook's GIT_GRAFT_FILE must not trigger git's deprecation advice

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


class OwnRepositoriesOnly(ProtectedRepoTest):
    """The hook acts where origin is the user's (Taka499, tia-tools) or absent; others' clones must still pull."""

    def direct_commit_moves_develop(self, origin: str) -> bool:
        self.repo.git("remote", "add", "origin", origin)
        before = self.repo.tip("develop")
        self.repo.git("commit", "--allow-empty", "-m", "direct", check=False)
        return self.repo.tip("develop") != before

    def test_someone_elses_repository_is_left_alone(self):
        self.assertTrue(self.direct_commit_moves_develop("https://github.com/receptron/mulmoterminal.git"))

    def test_the_users_account_is_protected(self):
        self.assertFalse(self.direct_commit_moves_develop("git@github.com:Taka499/nudge.git"))

    def test_the_owner_in_another_case_is_still_the_user(self):
        self.assertFalse(self.direct_commit_moves_develop("https://github.com/taka499/nudge.git"))

    def test_an_insteadof_alias_is_expanded(self):
        self.repo.git("config", "url.https://github.com/Taka499/.insteadOf", "mine:")
        self.assertFalse(self.direct_commit_moves_develop("mine:nudge.git"))

    def test_a_push_url_to_the_user_protects(self):
        """Codex review of the global hook (2026-10-12): only origin's first fetch URL was read."""
        self.repo.git("remote", "add", "origin", "https://github.com/receptron/mulmoterminal.git")
        self.repo.git("remote", "set-url", "--push", "origin", "git@github.com:Taka499/mulmoterminal.git")
        before = self.repo.tip("develop")
        self.repo.git("commit", "--allow-empty", "-m", "direct", check=False)
        self.assertEqual(self.repo.tip("develop"), before)

    def test_the_users_remote_under_another_name_protects(self):
        self.repo.git("remote", "add", "fork", "git@github.com:Taka499/mulmoterminal.git")
        self.assertFalse(self.direct_commit_moves_develop("https://github.com/receptron/mulmoterminal.git"))

    def test_the_users_organization_is_protected(self):
        self.assertFalse(self.direct_commit_moves_develop("https://github.com/tia-tools/gakumas-supportcards.git"))


def config_hooks_supported() -> bool:
    """Whether the git on PATH runs hooks defined in config (git 2.56 does; Apple's 2.50 does not)."""
    with tempfile.TemporaryDirectory() as temp:
        config = os.path.join(temp, "gitconfig")
        marker = os.path.join(temp, "ran")
        with open(config, "w") as handle:
            handle.write(f'[hook "probe"]\n\tevent = reference-transaction\n\tcommand = touch {marker}\n')
        env = dict(ENV, GIT_CONFIG_GLOBAL=config)
        subprocess.run(["git", "init", "-q", os.path.join(temp, "r")], env=env, capture_output=True, check=False)
        subprocess.run(["git", "-C", os.path.join(temp, "r"), "commit", "-q", "--allow-empty", "-m", "x"],
                       env=env, capture_output=True, check=False)
        return os.path.exists(marker)


@unittest.skipUnless(config_hooks_supported(), "this git does not run config-defined hooks")
class GlobalHook(unittest.TestCase):
    """The hook defined once in global config, the way install-global.sh sets it up."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.temp.name, "gitconfig")
        with open(self.config, "w") as handle:
            handle.write(f'[hook "protect-branches"]\n\tevent = reference-transaction\n\tcommand = {HOOK}\n')
        self.env = {"GIT_CONFIG_GLOBAL": self.config}
        self.repo = Repo(os.path.join(self.temp.name, "repo"))

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], env=dict(ENV, **self.env), capture_output=True, text=True, check=False)

    def test_init_and_clone_still_work(self):
        """The first version asked for the git directory before git init had made one, and aborted the init."""
        self.assertEqual(self.run_git("init", "-q", "-b", "develop", self.repo.path).returncode, 0)
        self.repo.git("commit", "-q", "--allow-empty", "-m", "root", env=self.env)
        clone = os.path.join(self.temp.name, "clone")
        result = self.run_git("clone", "-q", self.repo.path, clone)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_direct_commit_on_develop_is_refused(self):
        self.run_git("init", "-q", "-b", "develop", self.repo.path)
        self.repo.git("commit", "-q", "--allow-empty", "-m", "root", env=self.env)
        before = self.repo.tip("develop")
        result = self.repo.git("commit", "--allow-empty", "-m", "direct", check=False, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.repo.tip("develop"), before)

    def test_the_repositorys_own_hooks_still_run(self):
        """Unlike a global core.hooksPath: Git LFS keeps its hooks in .git/hooks."""
        self.run_git("init", "-q", "-b", "develop", self.repo.path)
        marker = os.path.join(self.temp.name, "post-commit-ran")
        hook = os.path.join(self.repo.path, ".git", "hooks", "post-commit")
        with open(hook, "w") as handle:
            handle.write(f"#!/bin/sh\ntouch {marker}\n")
        os.chmod(hook, 0o755)
        self.repo.git("commit", "-q", "--allow-empty", "-m", "root", env=self.env)
        self.assertTrue(os.path.exists(marker))

    def test_install_global_sets_the_hook_up_and_proves_it_runs(self):
        home = os.path.join(self.temp.name, "home")
        os.makedirs(home)
        env = dict(ENV, HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"),
                   GIT_CONFIG_GLOBAL=os.path.join(home, ".gitconfig"))
        result = subprocess.run(["sh", INSTALL_GLOBAL], env=env, capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("active", result.stdout)
        installed = os.path.join(home, ".config", "git", "protect-branches")
        self.assertTrue(os.access(installed, os.X_OK))
        command = subprocess.run(["git", "config", "--global", "--get", "hook.protect-branches.command"], env=env,
                                 capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(command, installed)
        check = subprocess.run(["sh", INSTALL_GLOBAL, "--check"], env=env, capture_output=True, text=True, timeout=60,
                               check=False)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_check_fails_when_another_hook_does_the_refusing(self):
        """Codex review: the probe must see this hook's own refusal, not any refusal."""
        home = os.path.join(self.temp.name, "home2")
        os.makedirs(home)
        config = os.path.join(home, ".gitconfig")
        other = os.path.join(home, "other-hook")
        with open(other, "w") as handle:  # refuses only updates of an existing develop, as a real one might
            handle.write('#!/bin/sh\n[ "$1" = prepared ] || exit 0\n'
                         'while read -r old new ref; do\n'
                         '  case "$old" in *[!0]*) [ "$ref" = refs/heads/develop ] && exit 1 ;; esac\n'
                         'done\nexit 0\n')
        os.chmod(other, 0o755)
        with open(config, "w") as handle:
            handle.write(f'[hook "other"]\n\tevent = reference-transaction\n\tcommand = {other}\n')
        env = dict(ENV, HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"), GIT_CONFIG_GLOBAL=config)
        check = subprocess.run(["sh", INSTALL_GLOBAL, "--check"], env=env, capture_output=True, text=True, timeout=60,
                               check=False)
        self.assertNotEqual(check.returncode, 0)


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

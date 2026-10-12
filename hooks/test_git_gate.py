"""Tests for git_gate.py. Run: python3 -m unittest discover -s hooks"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import git_gate
from git_gate import decide

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git_gate.py")


def on(branch, elsewhere=None):
    """A branch_of that reports `branch` for the session's cwd and `elsewhere[dir]` for a `cd` target."""
    elsewhere = elsewhere or {}
    return lambda directory: branch if directory is None else elsewhere.get(directory)


def asks(verdict):
    return verdict is not None and verdict[0] == "ask"


class FeatureBranchWork(unittest.TestCase):
    """Happy path: the standing permission covers a feature branch."""

    def test_commit_on_feature_branch_is_left_alone(self):
        self.assertIsNone(decide('git commit -m "feat: x"', on("feat/x")))

    def test_staging_then_committing_on_feature_branch(self):
        self.assertIsNone(decide("git add a.py b.py && git commit -m 'fix: y'", on("feat/x")))

    def test_merging_develop_into_feature_branch_updates_it(self):
        self.assertIsNone(decide("git merge develop", on("feat/x")))

    def test_read_only_git_on_develop(self):
        self.assertIsNone(decide("git status && git log --oneline -3 && git diff develop", on("develop")))

    def test_switching_to_a_named_feature_branch_then_committing(self):
        self.assertIsNone(decide("git switch -c feat/new && git commit -m x", on("develop")))
        self.assertIsNone(decide("git switch feat/y && git commit -m x", on("develop")))

    def test_listing_and_plainly_creating_branches(self):
        for command in ("git branch", "git branch -a -v", "git branch --show-current",
                        "git branch feat/new", "git branch feat/new develop"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("develop")))

    def test_read_forms_of_worktree_and_symbolic_ref(self):
        self.assertIsNone(decide("git worktree list", on("develop")))
        self.assertIsNone(decide("git symbolic-ref --short -q HEAD", on("develop")))

    def test_pull_on_a_feature_branch(self):
        self.assertIsNone(decide("git pull origin feat/x", on("feat/x")))

    def test_fetching_develop_only_updates_remote_tracking_refs(self):
        self.assertIsNone(decide("git fetch origin develop", on("feat/x")))

    def test_fetch_refspecs_into_remote_tracking_refs_or_tags(self):
        """The user's report (2026-10-13): the /codex-review snapshot's fetch of its base asked."""
        for command in ('git -C "$S/repo" fetch -q origin "master:refs/remotes/origin/master"',
                        "git fetch origin '+refs/heads/*:refs/remotes/origin/*'", "git fetch origin v1:refs/tags/v1",
                        "git fetch origin develop:", "git fetch git@github.com:Taka499/claude.git",
                        "git fetch https://github.com/x/y.git main:refs/remotes/y/main"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("develop")))
        for command in ("git fetch origin x:refs/heads/develop", "git fetch origin feat:feat2",
                        "git fetch origin 'refs/heads/*:refs/heads/*'", "git fetch origin develop:refs/heads/main",
                        'git fetch "$R" master:refs/remotes/origin/master', "git fetch origin $SPEC"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_heredoc_commit_message_that_mentions_git_commands(self):
        self.assertIsNone(decide("git commit -F - <<'EOF'\nfix: git merge handling\nEOF", on("feat/x")))

    def test_interpreter_heredoc_with_harmless_git_prose(self):
        command = "python3 - <<'EOF'\nprint('update the git repo; git add later')\nEOF"
        self.assertIsNone(decide(command, on("feat/x")))

    def test_python_rewriting_a_plan_full_of_git_prose(self):
        """Regression (a coordination worker, 2026-10-12): a plan edit asked, costing the user an approval."""
        command = ("python3 - <<'EOF'\nfrom pathlib import Path\np = Path('docs/plans/EXECPLAN.md')\n"
                   "t = p.read_text().replace('merge it', 'run git merge --no-ff feature/x, then git push origin develop')\n"
                   "p.write_text(t)\nEOF")
        self.assertIsNone(decide(command, on("feat/x")))
        self.assertIsNone(decide(command, on("develop")))
        self.assertIsNone(decide('python3 -c "print(\'git commit -m x\')"', on("develop")))
        # Codex: the old command-wide rule asked for these two
        self.assertIsNone(decide("env " + command, on("feat/x")))
        self.assertIsNone(decide(command + "\ntime true", on("feat/x")))

    def test_message_from_a_command_substitution(self):
        self.assertIsNone(decide('git commit -m "$(cat msg.txt)"', on("feat/x")))


class ProtectedBranches(unittest.TestCase):
    """The rule: history written to main, master or develop asks."""

    def test_commit_on_each_protected_branch_asks(self):
        for branch in ("main", "master", "develop"):
            with self.subTest(branch=branch):
                verdict = decide('git commit -m "x"', on(branch))
                self.assertTrue(asks(verdict))
                self.assertIn(branch, verdict[1])

    def test_merge_into_develop_asks(self):
        self.assertTrue(asks(decide("git merge --no-ff feature/b11", on("develop"))))

    def test_other_history_writers_ask(self):
        for command in ("git revert -m 1 abc123", "git cherry-pick abc123", "git am < p.patch"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("develop"))))

    def test_merge_continue_still_writes_the_merge_commit(self):
        self.assertTrue(asks(decide("git merge --continue", on("main"))))

    def test_gh_pr_merge_always_asks(self):
        self.assertTrue(asks(decide("gh pr merge 23 --merge", on("feat/x"))))


class EdgesAndCorners(unittest.TestCase):

    def test_abort_leaves_the_branch_alone(self):
        self.assertIsNone(decide("git merge --abort", on("develop")))
        self.assertIsNone(decide("git cherry-pick --abort", on("develop")))

    def test_env_assignment_before_git(self):
        self.assertTrue(asks(decide("GIT_EDITOR=true git merge --continue", on("develop"))))

    def test_global_options_before_subcommand(self):
        self.assertTrue(asks(decide("git -c user.name=x --no-pager commit -m y", on("develop"))))
        self.assertIsNone(decide("git --no-pager log -1", on("develop")))

    def test_cd_into_a_worktree_uses_that_branch(self):
        branch_of = on("develop", {"../wt": "feat/wt"})
        self.assertIsNone(decide("cd ../wt && git commit -m x", branch_of))

    def test_cd_into_the_main_checkout_from_a_worktree_asks(self):
        branch_of = on("feat/wt", {"../main": "develop"})
        self.assertTrue(asks(decide("cd ../main && git merge --no-ff feat/wt", branch_of)))

    def test_cd_inside_a_subshell_does_not_leak_out(self):
        branch_of = on("develop", {"../wt": "feat/wt"})
        self.assertTrue(asks(decide("(cd ../wt && make) && git commit -m x", branch_of)))

    def test_git_dash_C_is_resolved(self):
        branch_of = on("feat/x", {"../main": "develop"})
        self.assertTrue(asks(decide("git -C ../main commit -m x", branch_of)))

    def test_newline_separated_commands(self):
        self.assertTrue(asks(decide("git add a\ngit commit -m x", on("master"))))

    def test_heredoc_message_with_apostrophe(self):
        command = "git commit -F - <<'EOF'\nfix: it's done\nEOF"
        self.assertTrue(asks(decide(command, on("develop"))))
        self.assertIsNone(decide(command, on("feat/x")))


class UnknownTargetsAsk(unittest.TestCase):
    """When the branch cannot be named, a history write asks instead of passing silently."""

    def test_detached_head_or_not_a_repo(self):
        self.assertTrue(asks(decide("git commit -m x", on(None))))

    def test_git_dir_override(self):
        self.assertTrue(asks(decide("git --git-dir=/elsewhere/.git commit -m x", on("feat/x"))))

    def test_cd_minus(self):
        self.assertTrue(asks(decide("cd - && git commit -m x", on("feat/x"))))

    def test_unbalanced_quotes_fall_back_to_a_scan(self):
        self.assertTrue(asks(decide("git commit -m \"unterminated", on("develop"))))
        self.assertIsNone(decide("git commit -m \"unterminated", on("feat/x")))

    def test_unbalanced_quotes_with_cd_ask_even_on_a_feature_branch(self):
        self.assertTrue(asks(decide("cd ../wt && git commit -m \"unterminated", on("feat/x"))))


class BypassRegressions(unittest.TestCase):
    """Shapes that wrote history to a protected branch with no ask in the first version
    (Codex review and the background security review, 2026-10-12). All run from a feature branch."""

    SHAPES = (
        "git switch develop && git commit -m x",          # branch switch earlier in the command
        "git checkout develop && git merge feat/x",
        "git switch -C develop",                            # force-create resets a protected branch
        "bash -c \"git commit -m x\"",                      # git inside another program
        "sh -c \"cd ../main && git merge feat\"",
        "eval \"git commit -m x\"",
        "echo \"$(git commit -m x)\"",
        "echo `git commit -m x`",
        "bash <<'EOF'\ngit commit -m x\nEOF",               # interpreter heredoc
        "git -c alias.ci=commit ci -m x",                   # inline alias
        "git branch -f develop HEAD",                       # direct ref moves
        "git update-ref refs/heads/develop HEAD",
        "git fetch origin feat:develop",
        "git push origin HEAD:develop",                     # any push
        "GIT_DIR=../main/.git git commit -m x",             # environment redirects
        "export GIT_DIR=../main/.git; git commit -m x",
        "GIT_WORK_TREE=../main; git commit -m x",
        "env GIT_DIR=../main/.git git commit -m x",
        "gh pr merge 1 --merge && true",
    )

    def test_every_shape_asks(self):
        for command in self.SHAPES:
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_switch_to_a_branch_the_text_does_not_name(self):
        for command in ("git switch - && git commit -m x",
                        'git switch "$TARGET" && git commit -m x',
                        "git checkout @{-1} && git merge feat/x"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_round_two_shapes_ask(self):
        """Codex review round 2 and the security review of the first fix (2026-10-12)."""
        for command in (
            'git branch -f "$TARGET" HEAD',                 # branch target given as a variable
            'git update-ref "$REF" HEAD',
            'git fetch origin feat:"$TARGET"',
            "git update-ref --stdin <<'EOF'\nupdate refs/heads/main HEAD\nEOF",
            "git switch -Cdevelop",                          # short option attached to its value
            "git checkout -Bmaster",
            "git branch -fmain HEAD",
            "git ship",                                      # an alias, whatever it expands to
            "git -calias.x=commit x",
            "git --config-env=alias.x=VAR x",
            "git filter-branch -- --all",                    # rewrites several refs at once
            "G=git; $G commit -m x",                         # git reached through a variable
            '"$GIT" commit -m x',
        ):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_allowlisted_subcommands_with_branch_moving_forms_ask(self):
        """Security review of the allowlist commit (2026-10-12): options that turn a silent form into a branch move."""
        for command in ("git stash branch develop && git commit -m x",
                        "git symbolic-ref -d HEAD",
                        "git symbolic-ref HEAD refs/heads/main",
                        "git pull origin develop:develop",
                        'git pull origin "$SPEC"'):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))
        self.assertIsNone(decide("git stash && git stash pop", on("feat/x")))

    def test_directory_changes_other_than_cd(self):
        """Security review of the escape fixes (2026-10-12): the shell can move without `cd`."""
        branch_of = on("feat/x", {"../main": "develop"})
        for command in ("pushd ../main && git commit -m x", "builtin cd ../main && git commit -m x",
                        "command cd ../main && git merge feat/x", "popd && git commit -m x"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, branch_of)))
        self.assertIsNone(decide("pushd ../wt && git commit -m x", on("develop", {"../wt": "feat/wt"})))

    def test_printed_git_that_something_else_executes(self):
        for command in ('echo "git commit -m x" | bash', "bash <(echo git commit -m x)",
                        "cat <<'EOF' | bash\ngit commit -m x\nEOF"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))
        self.assertIsNone(decide("git log --oneline | grep commit", on("develop")))

    def test_round_three_shapes_ask(self):
        """Codex review round 3 (2026-10-12)."""
        for command in ("G=git; $G -c alias.x=push x origin HEAD:main",   # alias through a variable
                        "G=git; $G --stdin x",
                        "GIT_CONFIG_COUNT=1 $G x",
                        "printf 'HEAD:refs/heads/main\\n' | git fetch --stdin origin",  # refspecs from stdin
                        "git fetch --refmap=x origin",
                        "git clone --upload-pack='sh -c x' repo dir",       # runs a program
                        "git clone -u 'sh -c x' repo dir",
                        "git clone -c core.hooksPath=h repo dir",            # configuration into the new repo
                        "git clone --template=t repo dir",
                        "git clone -ccore.hooksPath=h repo dir",            # attached short option
                        "git init --template=t dir",
                        "git ls-remote --upload-pack=x origin"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))
        for command in ("git clone https://github.com/isamu/claude.git repo", "git fetch origin --prune",
                        '"$PY" -m unittest', "git commit --template=msg.txt"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("feat/x")))

    def test_switching_off_gits_own_protection_asks(self):
        for command in ("git -c core.hooksPath=/dev/null commit -m x", "git -ccore.hookspath=/dev/null merge x",
                        "git config core.hooksPath /tmp/none", "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='x'\" git status",
                        "git config include.path /tmp/evil.cfg", "git config --file .git/config core.editor x",
                        "git -c hook.protect-branches.enabled=false commit -m x",
                        "git config hook.protect-branches.enabled false",
                        "/usr/bin/git commit -m x"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_git_behind_a_wrapper_is_judged_as_git(self):
        """Per-program review (2026-10-13): a wrapper is looked through, not treated as a shell."""
        for command in ("env git commit -m x", "command git commit -m x", "time git commit -m x",
                        "exec git commit -m x", "xargs git commit -m x < /dev/null", "nohup git merge feat/x",
                        "xargs -I {} git commit -m {}", "find . -maxdepth 0 -exec git commit -m x \\;"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("develop"))))
                self.assertIsNone(decide(command, on("feat/x")))

    def test_codex_round_two_shapes(self):
        """Codex review round 2 of the per-program rule (2026-10-13)."""
        for command in ("echo 'git commit -m x' | cat | bash", "printf 'git commit -m x' | sed 's/x/x/' | sh"):
            with self.subTest(command=command):  # multi-stage pipelines into a shell
                self.assertTrue(asks(decide(command, on("feat/x"))))
        for command in ("arch git commit -m x", "setsid git commit -m x"):
            with self.subTest(command=command):  # launchers on no list
                self.assertTrue(asks(decide(command, on("develop"))))
                self.assertIsNone(decide(command, on("feat/x")))
        for command in ("env git sync", "time git co develop", "env gh pr merge 5", "time gh pr merge 5 --merge"):
            with self.subTest(command=command):  # an alias or gh behind a launcher is still seen
                self.assertTrue(asks(decide(command, on("feat/x"))))
        for command in ("find . -name git -exec echo {} \\;", "sudo -u git true", "env -u git true"):
            with self.subTest(command=command):  # an argument named git is not a git run
                self.assertIsNone(decide(command, on("develop")))

    def test_launchers_codex_found_unscanned(self):
        """Codex review of the narrowing (2026-10-13): runners missing from a fixed list."""
        for command in ("busybox sh -c 'git commit -m x'",
                        "git -c core.pager='sh -c \"git commit -m x\"' log",
                        "GIT_PAGER='git commit -m x' git log",
                        "/bin/bash -c 'git merge feat'"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_rest_of_a_heredoc_line_is_still_seen(self):
        """The heredoc pattern used to swallow what followed `<<EOF` on its line."""
        command = "python3 - <<'EOF' && git commit -m x\nprint('plan edit')\nEOF"
        self.assertTrue(asks(decide(command, on("develop"))))
        self.assertIsNone(decide(command, on("feat/x")))

    def test_process_substitution_runs_its_contents(self):
        """Security review of the narrowing (2026-10-13): `cat <(git commit)` runs the commit."""
        self.assertTrue(asks(decide("cat <(git commit -m x)", on("develop"))))
        self.assertIsNone(decide("cat <(git commit -m x)", on("feat/x")))  # it commits on feat/x
        self.assertTrue(asks(decide("cat -n <(git push origin develop)", on("feat/x"))))
        self.assertIsNone(decide("diff <(git log -1) <(git log -2)", on("develop")))

    def test_printed_git_is_text_until_a_shell_reads_it(self):
        """Codex review round 3 (2026-10-13): `echo git commit` on develop asked."""
        self.assertIsNone(decide("echo git commit -m x", on("develop")))
        self.assertIsNone(decide("printf '%s\\n' git merge feat/x", on("develop")))
        for command in ("env echo git commit -m x", "find echo -exec git commit -m x \\;"):
            with self.subTest(command=command):  # behind a launcher `echo` may be an argument: asking is safe
                self.assertTrue(asks(decide(command, on("develop"))))
        self.assertTrue(asks(decide("env echo <(git commit -m x)", on("develop"))))
        self.assertTrue(asks(decide("echo git commit -m x | sh", on("feat/x"))))
        for command in ("echo <(git commit -m x)", "echo x > >(git commit -F -)", "printf %s <(git merge feat/x)"):
            with self.subTest(command=command):  # security review of round 3: a process substitution runs
                self.assertTrue(asks(decide(command, on("develop"))))

    def test_git_spelled_out_only_at_run_time_is_not_seen(self):
        """Accepted gap (Codex round 3): text built while it runs. The global git hook refuses the write."""
        for command in ("printf 'git com%s' mit | sh", "bash -c \"$(printf %s git) commit -m x\""):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("develop")))

    def test_heredoc_markers_bash_does_not_read(self):
        """Security review (2026-10-13): `<<EOF` in quotes or a comment hid the next lines as a body."""
        for command in ("echo '<<EOF'\ngit commit -m x\nEOF", "echo hi # <<EOF\ngit commit -m x\nEOF",
                        'echo "a <<EOF b"\ngit push origin develop\nEOF', "echo \\<<EOF\ngit commit -m x\nEOF",
                        "echo $'\\'' '<<EOF'\ngit commit -m x\nEOF", 'echo "$(echo "<<EOF")"\ngit commit -m x\nEOF',
                        "echo `echo '<<EOF'`\ngit commit -m x\nEOF", "cat <<< x\ngit commit -m x\nx"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("develop"))))
        real = "python3 - <<'EOF'\nprint(\"it's a 'git commit' # here\")\nEOF\ngit status"
        self.assertIsNone(decide(real, on("develop")))  # a real body's quotes and # do not leak out
        nested = "x=$(python3 - <<'EOF'\nprint('git push origin develop')\nEOF\n)\ngit status"
        self.assertIsNone(decide(nested, on("develop")))  # a heredoc inside $( ) is still a heredoc

    def test_heredocs_end_where_the_shell_ends_them(self):
        """Codex review round 6 (2026-10-13) and the shell checks behind the rewrite: each of these hid a
        command from the hook while the shell runs it."""
        for command in (
            "echo $((1 <<EOF\n))\ngit push origin develop\nEOF",            # arithmetic shift, not a heredoc
            "(( x = 1 <<EOF ))\ngit push origin develop\nEOF",
            "cat <<A <<B\nx\nA\n'\nB\ngit push origin 'develop'",            # two heredocs on one line
            "cat <<EOF\nx\\\nEOF\n'\nEOF\ngit push origin 'develop'",         # x\ + EOF is no delimiter line
            "cat <<EOF\n  EOF\n'\nEOF\ngit push origin 'develop'",            # nor is an indented EOF
            "cat <<EOF\nEOF \n'\nEOF\ngit push origin 'develop'",             # nor one with a trailing space
            'echo "$(case x in a) echo "<<EOF";; esac)"\ngit push origin develop\nEOF',  # a case pattern's )
            'echo "$( (true) ; echo "<<EOF" )"\ngit push origin develop\nEOF',  # a subshell's ) inside $( )
            # The same misreads with quotes left balanced, closed in a line the shell takes for a comment,
            # so the lexer's fallback cannot catch them:
            "cat <<EOF\nx\\\nEOF\ny='\nEOF\ngit push origin develop\n# '",
            "cat <<EOF\n  EOF\ny='\nEOF\ngit push origin develop\n# '",
            "cat <<A <<B\nx\nA\ny='\nB\ngit push origin develop\n# '",
            "cat <<'EOF'\nx\\\nEOF\ngit push origin develop",  # a quoted delimiter joins no lines
            "cat <<$'EOF'\ntext\nEOF\ngit push origin develop",  # Codex round 7: ANSI-C quoted delimiter
            "echo $'\\'' '<<EOF' $'\\''\n\\'\ngit push origin develop\nEOF",  # $'\'' shifting quote parity
        ):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_an_unquoted_heredoc_runs_its_substitutions(self):
        """Codex review round 8 (2026-10-13): with an unquoted delimiter, the shell runs `$(…)` and backticks
        in the body as it reads it, whatever program the body then goes to."""
        for command in ("python3 - <<EOF\n$(git push origin develop)\nEOF",
                        "sed -n p <<EOF\n`git push origin develop`\nEOF",
                        "python3 - <<-EOF\n\t$(cd ../develop && git merge feat/x)\n\tEOF",
                        "git commit -F - <<EOF\nmsg $(git push origin develop)\nEOF"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))
        for command in ("python3 - <<'EOF'\n$(git push origin develop)\nEOF",  # quoted: nothing expands
                        "python3 - <<EOF\nprint('git push origin develop')\nEOF",  # nothing to run
                        "cat <<EOF\nbuilt on $(date)\nEOF"):  # a substitution with no git in it
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("feat/x")))

    def test_ordinary_heredocs_stay_silent(self):
        for command in (
            "git commit -m \"$(cat <<'EOF'\nfix: explain git push origin develop\nEOF\n)\"",
            "python3 - <<-EOF\n\tprint('git push origin develop')\n\tEOF",
            "python3 - <<'A' && cat <<B\nprint('git push origin develop')\nA\ngit merge x\nB",
            "cat <<\"EOF\"\ngit push origin develop\nEOF\ngit status",
        ):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("feat/x")))

    def test_the_coarse_scan_is_no_weaker(self):
        """Security review of round 7's fix (2026-10-13): `$'…'` sends a command to the coarse scan, which
        judged `git -C ../main merge` against the session's branch and did not see `$G push`."""
        for command in ("printf $'x\\n' && git -C ../main merge feat/x", "printf $'x' && G=git && $G push origin develop",
                        "printf $'x' && $G merge feat/x", "printf $'x' && GIT_DIR=../m/.git git commit -m x",
                        "printf $'x' && pushd ../m && git commit -m x", "printf $'x'\ncd ../m && git commit -m x",
                        "printf $'x' && /usr/bin/git commit -m x", "printf $'x' && git -c core.hooksPath=/dev/null commit -m x",
                        "printf $'x'; git config core.hooksPath /dev/null; git commit -m x",
                        "printf $'x'; GIT_CONFIG_PARAMETERS=\"'hook.p.enabled=false'\" git commit -m x"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))
        self.assertIsNone(decide("printf $'a\\tb\\n' > x.txt && git commit -m x", on("feat/x")))
        self.assertTrue(asks(decide("printf $'a\\tb\\n' > x.txt && git commit -m x", on("develop"))))

    def test_every_directory_change_is_followed(self):
        """Codex review round 9 (2026-10-13), also on master: zsh's `chdir` and a `builtin`/`command` in front
        of `pushd` or `popd` were not taken for directory changes, so a merge could land on develop silently."""
        elsewhere = on("feat/x", {"../protected": "develop", "~": "feat/z", "feat": "feat/y", "+1": "feat/z"})
        for command in ("chdir ../protected && git merge topic", "builtin pushd ../protected && git merge topic",
                        "command pushd ../protected && git merge topic", "builtin popd && git merge topic",
                        "cd feat main && git merge topic",          # zsh: replace feat with main in the path
                        "cd -2 && git merge topic", "pushd && git merge topic", "pushd +1 && git merge topic"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, elsewhere)))
        self.assertIsNone(decide("cd feat && git merge topic", elsewhere))  # a named feature checkout
        for command in ('eval "cd ../protected" && git merge topic', "alias c='cd ../protected'\nc && git merge topic",
                        "source <(echo cd ../protected) && git merge topic", "builtin eval 'pushd ../protected' && git merge topic",
                        "alias g='git push origin develop'"):
            with self.subTest(command=command):  # text the current shell runs moves it, or runs git
                self.assertTrue(asks(decide(command, elsewhere)))
        for command in ("{ cd ../protected; git merge topic; }", "if cd ../protected; then git merge topic; fi",
                        "while true; do cd ../protected; git merge topic; break; done", "! cd ../protected || git merge topic"):
            with self.subTest(command=command):  # Codex review round 10: a reserved word hid the move
                self.assertTrue(asks(decide(command, elsewhere)))
        named = on("feat/x", {"~n": "feat/z", "~": "feat/z", "~/x": "feat/z"})
        self.assertTrue(asks(decide("hash -d n=../protected; cd ~n && git merge topic", named)))  # only zsh resolves ~n
        for command in ("cd ~ && git merge topic", "cd ~/x && git merge topic"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, named))
        self.assertIsNone(decide("deploy() { echo git push origin develop; }", on("feat/x")))  # round 10, Low
        for command in ('eval "$(ssh-agent -s)" && git commit -m x', "source .venv/bin/activate && git commit -m x"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command, on("feat/x")))
        self.assertIsNone(decide("printf $'x' && git --no-pager commit -m x", on("feat/x")))  # Codex round 9, Low

    def test_a_hash_hides_nothing_after_it(self):
        """Found reviewing the heredoc fix (2026-10-13), also on master: shlex read `#` as a comment
        to the end of the whole command, after newlines were joined, and mid-word as well."""
        for command in ("echo a#b; git commit -m x", "echo hi # note\ngit commit -m x",
                        "curl -s https://x/y#frag && git push origin develop"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("develop"))))
        self.assertIsNone(decide("git status # git push origin develop", on("develop")))  # a real comment

    def test_a_script_file_is_the_program_file_case(self):
        """Not seen here, by design: a shell running a script file. The global git hook covers it."""
        self.assertIsNone(decide("printf 'git commit -m x' > s.sh; sh s.sh", on("develop")))

    def test_creating_a_protected_branch_asks(self):
        """In a repository without one yet, this would seed main or develop with unreviewed work."""
        for command in ("git branch develop feat/x", "git switch -c main", "git switch --create develop feat/x"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("feat/x"))))

    def test_pull_on_a_protected_branch_asks(self):
        self.assertTrue(asks(decide("git pull --ff-only origin master", on("master"))))

    def test_config_alias_on_a_protected_branch_asks(self):
        self.assertTrue(asks(decide("git ci -m x", on("develop"))))


class Negative(unittest.TestCase):
    """Things that must NOT trigger a prompt."""

    def test_empty_command(self):
        self.assertIsNone(decide("", on("develop")))

    def test_git_commit_inside_quoted_text(self):
        self.assertIsNone(decide('echo "next: git commit on develop"', on("develop")))

    def test_merge_base_is_not_merge(self):
        self.assertIsNone(decide("git merge-base --is-ancestor a b", on("develop")))

    def test_non_git_command(self):
        self.assertIsNone(decide("python3 -m unittest", on("main")))

    def test_read_only_apple_git_and_ordinary_options(self):
        self.assertIsNone(decide("/usr/bin/git status", on("develop")))
        self.assertIsNone(decide('git commit -m "fix: the hook. done"', on("feat/x")))

    def test_branch_merely_containing_a_protected_name(self):
        self.assertIsNone(decide("git commit -m x", on("feature/main-menu")))


class HookEndToEnd(unittest.TestCase):
    """The script as Claude Code runs it: JSON on stdin, a decision (or nothing) on stdout."""

    def run_hook(self, payload):
        result = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, timeout=30, check=True)
        return result.stdout

    def test_real_repository(self):
        with tempfile.TemporaryDirectory() as repo:
            git = ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run(git + ["init", "-q", "-b", "develop"], check=True)
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "root"], check=True)
            payload = {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": "git commit -m x"}}
            output = json.loads(self.run_hook(payload))["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse")
            self.assertEqual(output["permissionDecision"], "ask")
            subprocess.run(git + ["switch", "-q", "-c", "feat/x"], check=True)
            self.assertEqual(self.run_hook(payload), "")

    def test_unreadable_input_asks(self):
        for raw in ("not json", json.dumps({"tool_name": "Bash", "cwd": "/", "tool_input": {"command": None}}),
                    json.dumps({"tool_name": "Bash", "cwd": "/", "tool_input": {"command": 7}})):
            with self.subTest(raw=raw):
                result = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True,
                                        text=True, timeout=30, check=True)
                self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_other_tools_are_ignored(self):
        payload = {"tool_name": "Read", "cwd": "/", "tool_input": {"file_path": "/x"}}
        self.assertEqual(self.run_hook(payload), "")

    def test_a_failing_gate_asks_about_history_writes_only(self):
        def boom(command, branch_of):
            raise RuntimeError("boom")

        for command, expect_ask in (("git commit -m x", True), ("ls -la", False)):
            with self.subTest(command=command):
                payload = {"tool_name": "Bash", "cwd": "/", "tool_input": {"command": command}}
                out = io.StringIO()
                with mock.patch.object(git_gate, "decide", boom), \
                        mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                        contextlib.redirect_stdout(out):
                    git_gate.main()
                if expect_ask:
                    self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "ask")
                else:
                    self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

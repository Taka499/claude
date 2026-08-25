# Deploy this repo as the user-level Claude Code config by linking the tracked
# pieces into ~/.claude. Idempotent; backs up pre-existing real files.
# Directories use junctions (no elevation needed); the CLAUDE.md file uses a
# symbolic link, which requires Developer Mode or an elevated shell on Windows.
#
# CLAUDE.md, docs/ and commands/ are linked whole — nothing but this repo
# writes there. skills/ is different: ~/.claude/skills is a shared namespace
# that other tools install into, so it stays a real directory and each skill
# this repo owns is junctioned into it individually.
# See docs/adr/0003-skills-are-linked-per-skill.md.
$ErrorActionPreference = "Stop"

$RepoDir = $PSScriptRoot
$ClaudeDir = Join-Path $env:USERPROFILE ".claude"
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null

function Set-Link {
    param([string]$Src, [string]$Dst, [string]$Kind) # Kind: SymbolicLink | Junction

    $existing = Get-Item -Path $Dst -ErrorAction SilentlyContinue
    if ($existing) {
        if ($existing.LinkType -and $existing.Target -eq $Src) {
            Write-Host "ok: $Dst already linked"
            return
        }
        if ($existing.LinkType) {
            $existing.Delete()
        } else {
            $backup = "$Dst.pre-central.$(Get-Date -Format yyyyMMddHHmmss)"
            Write-Host "backup: $Dst -> $backup"
            if ($existing.PSIsContainer) {
                Write-Host "  NOTE: $Dst is a directory. Everything inside it leaves the live config;"
                Write-Host "        port anything you still want into $RepoDir and re-run."
            }
            Move-Item -Path $Dst -Destination $backup
        }
    }
    New-Item -ItemType $Kind -Path $Dst -Target $Src | Out-Null
    Write-Host "linked: $Dst -> $Src"
}

# Refuse to run against the pre-0003 layout rather than guess which skills in
# the repo are ours and which an installer dropped there. Migration moves files
# the user owns, so it is a deliberate manual step, done once.
function Assert-NotOldSkillsLayout {
    $srcDir = Join-Path $RepoDir "skills"
    $dstDir = Join-Path $ClaudeDir "skills"
    $existing = Get-Item -Path $dstDir -ErrorAction SilentlyContinue
    if (-not $existing -or -not $existing.LinkType) { return }
    if ($existing.Target -ne $srcDir) { return }
    Write-Error @"
$dstDir is a link to $srcDir (the layout before ADR 0003).

  While it is linked, every skill another tool installs lands in this repo's
  working tree. Migrate once, by hand, so you decide what moves:

    1. Check what is in the repo but not tracked by it:
         git -C "$RepoDir" status --porcelain --untracked-files=all skills/
    2. Replace the link with a real directory:
         (Get-Item "$dstDir").Delete(); New-Item -ItemType Directory -Path "$dstDir"
    3. Move every untracked (i.e. externally installed) skill back out of the
       repo, e.g.:
         Move-Item "$srcDir\<their-skill>" "$dstDir\<their-skill>"
    4. Re-run this script. It will link this repo's own skills individually.

  Commit any skill of your own that is still untracked before step 3, or it
  will look external to you when you read that list.
"@
    exit 1
}

function Set-SkillLinks {
    $srcDir = Join-Path $RepoDir "skills"
    $dstDir = Join-Path $ClaudeDir "skills"
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

    foreach ($skill in Get-ChildItem -Path $srcDir -Directory) {
        Set-Link -Src $skill.FullName -Dst (Join-Path $dstDir $skill.Name) -Kind Junction
    }

    # Drop links left behind by a skill this repo no longer has — deleted, or
    # absent on the branch now checked out. Only ever removes a link that
    # points into this repo; real directories and other tools' skills are
    # untouchable here.
    foreach ($entry in Get-ChildItem -Path $dstDir -Force) {
        if (-not $entry.LinkType) { continue }
        if ($entry.Target -notlike "$srcDir*") { continue }
        if (-not (Test-Path -Path $entry.Target)) {
            Write-Host "prune: $($entry.FullName) (gone from $srcDir)"
            $entry.Delete()
        }
    }
}

Assert-NotOldSkillsLayout

Set-Link -Src (Join-Path $RepoDir "CLAUDE.md") -Dst (Join-Path $ClaudeDir "CLAUDE.md") -Kind SymbolicLink
Set-Link -Src (Join-Path $RepoDir "docs")      -Dst (Join-Path $ClaudeDir "docs")      -Kind Junction
Set-Link -Src (Join-Path $RepoDir "commands")  -Dst (Join-Path $ClaudeDir "commands")  -Kind Junction
Set-SkillLinks

# settings.json is deliberately NOT linked — Claude Code owns and rewrites that
# file (effortLevel, tui, enabledPlugins, ...). See docs/adr/0002-settings-json-stays-untracked.md.

Write-Host "Done. ~/.claude now tracks this clone of the claude repo."

# Deploy this repo as the user-level Claude Code config by linking the tracked
# pieces into ~/.claude. Idempotent; backs up pre-existing real files.
# Directories use junctions (no elevation needed); the CLAUDE.md file uses a
# symbolic link, which requires Developer Mode or an elevated shell on Windows.
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

Set-Link -Src (Join-Path $RepoDir "CLAUDE.md") -Dst (Join-Path $ClaudeDir "CLAUDE.md") -Kind SymbolicLink
Set-Link -Src (Join-Path $RepoDir "skills")    -Dst (Join-Path $ClaudeDir "skills")    -Kind Junction
Set-Link -Src (Join-Path $RepoDir "docs")      -Dst (Join-Path $ClaudeDir "docs")      -Kind Junction
Set-Link -Src (Join-Path $RepoDir "commands")  -Dst (Join-Path $ClaudeDir "commands")  -Kind Junction

# settings.json is deliberately NOT linked — Claude Code owns and rewrites that
# file (effortLevel, tui, enabledPlugins, ...). See docs/adr/0002-settings-json-stays-untracked.md.

Write-Host "Done. ~/.claude now tracks this clone of the claude repo."

# Shared by session-start, scratch-rm and scratch-sweep; install.sh copies it beside them. Plan 0041.
# A session's scratch root is $BASE/<session id>/. $BASE is fixed here, never taken from the environment.
BASE=/tmp/cs

# is_session_id ID: true when ID looks like a Claude Code session id (a lowercase UUID).
is_session_id() {
    case $1 in
        ????????-????-????-????-????????????) ;;
        *) return 1 ;;
    esac
    case $1 in *[!0-9a-f-]*) return 1 ;; esac
    return 0
}

# own_dir PATH: true when PATH is a real folder (not a symlink) owned by this user, with mode 700 and no ACL,
# so that no other user can add, rename or replace anything in it.
own_dir() {
    [ -d "$1" ] && [ ! -L "$1" ] && [ -O "$1" ] || return 1
    case $(ls -ld "$1") in "drwx------ "* | "drwx------@ "* | "drwx------. "*) return 0 ;; esac
    return 1
}

# make_private PATH: give this user's folder PATH mode 700 and, on macOS, drop any ACL.
make_private() {
    [ -d "$1" ] && [ ! -L "$1" ] && [ -O "$1" ] || return 1
    chmod 700 "$1" 2>/dev/null
    [ "$(uname -s)" = Darwin ] && chmod -N "$1" 2>/dev/null
    return 0
}

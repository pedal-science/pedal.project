# Shared by devices/tib/{apply,check,backup}. Source it, don't run it.
set -euo pipefail

TIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIB_HOST="${TIB_HOST:-tib}"
# Never prompt, fail fast. WiFi is tib's only way in, so a hung session is the common failure.
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m[✓]\033[0m %s\n' "$*" >&2; }

tib() { ssh "${SSH_OPTS[@]}" "$TIB_HOST" "$@"; }

require_tib() {
  tib true 2>/dev/null || die "cannot ssh to $TIB_HOST. If the 1Password agent is locked, unlock it (ssh-add -l)."
}

# The commit the tree came from, marked dirty if devices/tib has uncommitted changes (rule 5).
tree_commit() {
  local c; c=$(git -C "$TIB_DIR" rev-parse --short HEAD)
  [[ -z $(git -C "$TIB_DIR" status --porcelain -- .) ]] || c="$c-dirty"
  echo "$c"
}

timestamp() { date -u +%Y%m%dT%H%M%SZ; }

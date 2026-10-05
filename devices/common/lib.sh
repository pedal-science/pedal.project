# Shared by devices/<host>/{apply,check,backup}, which are links to devices/common/. Source it,
# don't run it. The host is the name of the directory the link was run from, so
# devices/piv/apply works on piv and devices/tib/apply on tib.
set -euo pipefail

# BASH_SOURCE keeps the path the script was invoked by, not the link's target.
DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_NAME="$(basename "$DEV_DIR")"
COMMON_DIR="$(cd "$DEV_DIR/../common" && pwd)"
[[ $DEV_NAME != common ]] || { echo "run this from devices/<host>/, not devices/common/" >&2; exit 2; }
DEV_HOST="${DEV_HOST:-$DEV_NAME}"
# Never prompt, fail fast. WiFi is the usual way in, so a hung session is the common failure.
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m[✓]\033[0m %s\n' "$*" >&2; }

dev() { ssh "${SSH_OPTS[@]}" "$DEV_HOST" "$@"; }

require_dev() {
  dev true 2>/dev/null || die "cannot ssh to $DEV_HOST. Check ~/.ssh/config (the Core hosts' key, docs/vip-image.md) and that $DEV_HOST is up."
}

# The commit the tree came from, marked dirty if this device's tree or the common one has
# uncommitted changes (rule 5). Backups are output, not input, so they do not count.
tree_commit() {
  local c; c=$(git -C "$DEV_DIR" rev-parse --short HEAD)
  [[ -z $(git -C "$DEV_DIR" status --porcelain -- . ":!backups" "$COMMON_DIR") ]] || c="$c-dirty"
  echo "$c"
}

# Every file that goes on the host, as "<source path>\t</installed path>". The device's own
# rootfs wins over the common one where both have a file.
rootfs_files() {
  local root rel
  declare -A seen=()
  for root in "$DEV_DIR/rootfs" "$COMMON_DIR/rootfs"; do
    [[ -d $root ]] || continue
    while IFS= read -r rel; do
      [[ -n ${seen[$rel]:-} ]] && continue
      seen[$rel]=1
      printf '%s\t/%s\n' "$root/$rel" "$rel"
    done < <(cd "$root" && find . -type f ! -name .DS_Store ! -path '*/__pycache__/*' | sed 's|^\./||' | sort)
  done | sort -t$'\t' -k2
}

timestamp() { date -u +%Y%m%dT%H%M%SZ; }

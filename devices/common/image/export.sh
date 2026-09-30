# Sourced by devices/common/make-card and scripts/deploy-engine: export a repo's tree as a commit
# holds it, submodules included, for a build that mustn't see a working tree. Needs die().
# export <repo> <commit or "worktree"> <dest>: the tree at that commit, submodules included
# (at the commits their parent records), and nothing ignored or untracked.
export_tree() {
  local repo=$1 rev=$2 dest=$3
  mkdir -p "$dest"
  if [[ $rev == worktree ]]; then
    # Tracked and untracked-but-not-ignored files that exist (a deleted tracked file is gone).
    git -C "$repo" ls-files -z -c -o --exclude-standard \
      | while IFS= read -r -d '' f; do [[ -e $repo/$f || -L $repo/$f ]] && printf '%s\0' "$f"; done \
      | tar -C "$repo" --null -T - --no-recursion -cf - | tar -xf - -C "$dest"
    rev=HEAD
  else
    git -C "$repo" archive "$rev" | tar -xf - -C "$dest"
  fi
  git -C "$repo" ls-tree -r "$rev" | awk '$2 == "commit" {print $3, $4}' | while read -r sha path; do
    [[ -e $repo/$path/.git ]] || die "$repo: submodule $path isn't checked out"
    export_tree "$repo/$path" "$sha" "$dest/$path"
  done
}

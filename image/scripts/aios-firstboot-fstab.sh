#!/usr/bin/env bash
# First-boot fstab reconciliation for a bootc/ostree system.
#
# The installer (Anaconda) lays out the disk with its own autopart and writes a
# conventional /etc/fstab, including a line for / (e.g.
#   UUID=... / btrfs subvol=root,ro 0 0
# ). But this image's root is a composefs overlay that ostree mounts, so / is no
# longer the btrfs subvolume Anaconda described. When systemd-remount-fs applies
# that fstab line to the overlay it is refused with
#   overlay: No changes allowed in reconfigure
# and the service fails on the first boot.
#
# On a bootc/ostree system the root is mounted by the kernel command line
# (root= / rootflags=) and must not also be listed in /etc/fstab: the / entry is
# duplicative and is the thing that breaks the remount. So drop every line whose
# mountpoint is the root, and leave the rest (/boot, /boot/efi, /var, /var/home,
# ...) exactly as the installer wrote them. This is idempotent: a system whose
# fstab already has no / line is left untouched.
set -euo pipefail

FSTAB=/etc/fstab

# Nothing to reconcile if the file is absent or carries no line for the root.
[ -f "$FSTAB" ] || exit 0
if ! awk '$2 == "/" {found=1} END {exit found ? 0 : 1}' "$FSTAB"; then
  exit 0
fi

# Rewrite without the root line(s). awk's default field splitting skips leading
# whitespace, so $2 is the mountpoint even on indented lines; comments and blank
# lines are preserved verbatim.
tmp="$(mktemp "${FSTAB}.XXXXXX")"
awk '
  /^[[:space:]]*#/ { print; next }
  /^[[:space:]]*$/ { print; next }
  { if ($2 == "/") next; print }
' "$FSTAB" > "$tmp"
# Preserve the original inode and permissions rather than replacing the file.
cat "$tmp" > "$FSTAB"
rm -f "$tmp"

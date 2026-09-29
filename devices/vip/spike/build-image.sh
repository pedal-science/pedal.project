#!/usr/bin/env bash
# Runs INSIDE the build container. Makes the step 1 spike card image for vip: a GPT card with
# bootsel (autoboot.txt), two boot partitions and one root, every kernel command line carrying
# markers that say which partition and slot it came from. Throwaway: stock kernel, no pedal.
#
# In:  /in/authorized_keys           public keys for rik
#      stdin                         two lines, the WiFi SSID then its PSK (never written
#                                    anywhere but the root being built)
#      SNAPSHOT, SPIKE_HOSTNAME      from the environment
# Out: /out/spike.img, /out/spike.manifest

set -euo pipefail

log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

: "${SNAPSHOT:?}" "${SPIKE_HOSTNAME:?}"
KVER=7.0.0-1017-raspi
MIRROR="https://snapshot.ubuntu.com/ubuntu/${SNAPSHOT}"
# Pinned for the spike; the real build takes these from devices/vip/image.lock.
export SOURCE_DATE_EPOCH=$(date -u -d "${SNAPSHOT:0:8} ${SNAPSHOT:9:2}:${SNAPSHOT:11:2}:${SNAPSHOT:13:2}" +%s)

IFS= read -r WIFI_SSID || die "no WiFi SSID on stdin"
IFS= read -r WIFI_PSK  || die "no WiFi PSK on stdin"
[[ -n $WIFI_SSID && ${#WIFI_PSK} -ge 8 ]] || die "WiFi SSID empty or PSK too short"
[[ -s /in/authorized_keys ]] || die "no authorized_keys"

W=/work; ROOT=$W/root
rm -rf "$W"; mkdir -p "$W"

log "root: resolute minbase from the $SNAPSHOT snapshot"
PKGS=(
  systemd systemd-sysv systemd-resolved udev dbus kmod iproute2 iputils-ping less
  openssh-server sudo wpasupplicant wireless-regdb systemd-timesyncd
  dracut-core dosfstools e2fsprogs
  "linux-image-$KVER" "linux-modules-$KVER" linux-firmware-raspi
)
mmdebstrap --variant=minbase --mode=root \
  --aptopt='APT::Install-Recommends "false"' \
  --aptopt='Acquire::Check-Valid-Until "false"' \
  --components=main,restricted,universe \
  --include="$(IFS=,; echo "${PKGS[*]}")" \
  --customize-hook='chroot "$1" dpkg-query -W -f="\${Package} \${Version}\n" > '"$W"'/packages.txt' \
  --customize-hook='chroot "$1" dracut --force --no-hostonly --kver '"$KVER"' --add-drivers "sdhci-brcmstb sdhci-iproc mmc_block ext4 vfat" /boot/initrd.img-'"$KVER" \
  resolute "$ROOT" \
  "deb $MIRROR resolute main restricted universe" \
  "deb $MIRROR resolute-updates main restricted universe"

log "customise the root"
echo "$SPIKE_HOSTNAME" > "$ROOT/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 %s\n' "$SPIKE_HOSTNAME" > "$ROOT/etc/hosts"
cat > "$ROOT/etc/fstab" <<'EOF'
LABEL=spike-root  /             ext4  defaults,noatime        0 1
LABEL=BOOTSEL     /boot/bootsel vfat  defaults,noauto,nofail  0 0
EOF
mkdir -p "$ROOT/boot/bootsel"

chroot "$ROOT" useradd -m -s /bin/bash -G sudo rik
install -d -m 700 -o 1000 -g 1000 "$ROOT/home/rik/.ssh"
install -m 600 -o 1000 -g 1000 /in/authorized_keys "$ROOT/home/rik/.ssh/authorized_keys"
echo 'rik ALL=(ALL) NOPASSWD:ALL' > "$ROOT/etc/sudoers.d/10-rik"
chmod 440 "$ROOT/etc/sudoers.d/10-rik"
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' \
  > "$ROOT/etc/ssh/sshd_config.d/10-keys-only.conf"
# A throwaway card: fresh host keys, generated here rather than on first boot.
rm -f "$ROOT"/etc/ssh/ssh_host_*
ssh-keygen -q -t ed25519 -N '' -C "root@$SPIKE_HOSTNAME" -f "$ROOT/etc/ssh/ssh_host_ed25519_key"

log "network: networkd on eth0 and wlan0, wpa_supplicant for wlan0"
mkdir -p "$ROOT/etc/systemd/network" "$ROOT/etc/wpa_supplicant"
for i in eth0 wlan0; do
  printf '[Match]\nName=%s\n\n[Network]\nDHCP=yes\n' "$i" > "$ROOT/etc/systemd/network/20-$i.network"
done
{
  echo 'ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev'
  echo 'country=GB'
  echo 'network={'
  printf '  ssid="%s"\n' "$WIFI_SSID"
  # netplan keeps the key hashed, as 64 hex digits, and wpa_supplicant takes that form only
  # unquoted: quoted, it is a passphrase, too long, and the error message prints it.
  if [[ $WIFI_PSK =~ ^[0-9a-fA-F]{64}$ ]]; then printf '  psk=%s\n' "$WIFI_PSK"
  else printf '  psk="%s"\n' "$WIFI_PSK"; fi
  echo '}'
} > "$ROOT/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
chmod 600 "$ROOT/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
unset WIFI_SSID WIFI_PSK
ln -sf /run/systemd/resolve/stub-resolv.conf "$ROOT/etc/resolv.conf"
chroot "$ROOT" systemctl enable systemd-networkd systemd-resolved wpa_supplicant@wlan0 ssh

log "serial console: root autologin on ttyAMA10 (spike only: needs the Debug Probe in hand)"
mkdir -p "$ROOT/etc/systemd/system/serial-getty@ttyAMA10.service.d"
printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --keep-baud 115200 %%I $TERM\n' \
  > "$ROOT/etc/systemd/system/serial-getty@ttyAMA10.service.d/10-autologin.conf"

log "watchdog at 14 s, as on piv"
mkdir -p "$ROOT/etc/systemd/system.conf.d"
printf '[Manager]\nRuntimeWatchdogSec=14\nRebootWatchdogSec=2min\n' \
  > "$ROOT/etc/systemd/system.conf.d/10-watchdog.conf"

install -m 755 /spike/spike-report /spike/spike-try "$ROOT/usr/local/sbin/"
install -m 644 /spike/spike-report.service "$ROOT/etc/systemd/system/"
chroot "$ROOT" systemctl enable spike-report

log "boot partitions"
# The one command line, with the markers appended per slot.
# net.ifnames=0 keeps wlan0 and eth0: without it udev renames them wld0 and end0, and every
# unit and script written for wlan0 waits for a device that never appears.
BASE_CMDLINE="net.ifnames=0 console=ttyAMA10,115200 console=tty1 root=LABEL=spike-root rootfstype=ext4 rootwait fixrtc cfg80211.ieee80211_regdom=GB rd.shell=0 rd.emergency=reboot rd.retry=60 rd.timeout=90 panic=10"
FW=$ROOT/usr/lib/firmware/$KVER/device-tree
[[ -d $FW ]] || die "no device tree at $FW"
slot() {  # slot <dir> <part> <slot>
  mkdir -p "$1"
  cp "$ROOT/boot/vmlinuz-$KVER" "$1/vmlinuz"
  cp "$ROOT/boot/initrd.img-$KVER" "$1/initrd.img"
  cp "$FW"/broadcom/bcm2712*.dtb "$1/"
  cp -r "$FW/overlays" "$1/overlays"
  echo "$BASE_CMDLINE spike.part=$2 spike.slot=$3" > "$1/cmdline.txt"
}
config_txt() {  # config_txt <all-prefix> <tryboot-prefix>
  cat <<EOF
[all]
os_prefix=$1/

[tryboot]
os_prefix=$2/

[all]
arm_64bit=1
kernel=vmlinuz
cmdline=cmdline.txt
initramfs initrd.img followkernel
dtparam=watchdog=on
enable_uart=1
dtoverlay=vc4-kms-v3d
disable_fw_kms_setup=1
EOF
}
mkdir -p "$W/p1" "$W/p2" "$W/p3"
# p1 bootsel: normal boot is partition 2; the tryboot flag goes where spike-try points it.
cat > "$W/p1/autoboot.txt" <<'EOF'
[all]
tryboot_a_b=1
boot_partition=2

[tryboot]
boot_partition=3
EOF
config_txt current new > "$W/p2/config.txt"
slot "$W/p2/current" 2 current
slot "$W/p2/new" 2 new
config_txt a b > "$W/p3/config.txt"
slot "$W/p3/a" 3 a
slot "$W/p3/b" 3 b

log "filesystems"
mkfat() {  # mkfat <dir> <label> <MiB> <out> <volume id>
  rm -f "$4"; mkfs.vfat -F 32 -n "$2" -i "$5" -C "$4" $(( $3 * 1024 )) >/dev/null
  MTOOLS_SKIP_CHECK=1 mcopy -s -m -i "$4" "$1"/* ::/
}
mkfat "$W/p1" BOOTSEL 64 "$W/p1.img" 7669700a
mkfat "$W/p2" PEDAL-BOOT 512 "$W/p2.img" 7669700b
mkfat "$W/p3" RESCUE-BOOT 256 "$W/p3.img" 7669700c
ROOT_MB=$(( $(du -sm "$ROOT" | cut -f1) * 13 / 10 + 256 ))
mkfs.ext4 -q -L spike-root -E root_owner=0:0 -d "$ROOT" "$W/p4.img" "${ROOT_MB}M"

log "card image"
IMG=/out/spike.img
MB=$(( 1 + 64 + 512 + 256 + ROOT_MB + 1 ))
rm -f "$IMG"; truncate -s "${MB}M" "$IMG"
BASIC=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7
LINUX=0FC63DAF-8483-4772-8E79-3D69D8477DE4
sfdisk -q "$IMG" <<EOF
label: gpt
first-lba: 2048
start=1MiB,   size=64MiB,  type=$BASIC, name=bootsel
              size=512MiB, type=$BASIC, name=pedal-boot
              size=256MiB, type=$BASIC, name=rescue-boot
              size=${ROOT_MB}MiB, type=$LINUX, name=spike-root
EOF
n=0
while read -r start; do
  n=$(( n + 1 ))
  dd if="$W/p$n.img" of="$IMG" bs=1M seek=$(( start * 512 / 1048576 )) conv=notrunc status=none
done < <(sfdisk -J "$IMG" | python3 -c 'import json,sys; [print(p["start"]) for p in json.load(sys.stdin)["partitiontable"]["partitions"]]')

{
  echo "snapshot $SNAPSHOT"
  echo "kernel $KVER"
  echo "hostname $SPIKE_HOSTNAME"
  echo "image-bytes $(stat -c %s "$IMG")"
  echo "image-sha256 $(sha256sum "$IMG" | cut -d' ' -f1)"
  echo "--- sfdisk"
  sfdisk -d "$IMG" | sed 's|/out/||'
  echo "--- packages"
  cat "$W/packages.txt"
} > /out/spike.manifest
log "done: $(du -h --apparent-size "$IMG" | cut -f1) $IMG"

# The build container for a Pi host's card (devices/common/make-card): aarch64 Ubuntu 26.04,
# native on the M2 under colima. Its own packages come from the same pinned snapshot the image
# uses, so namchain and rigpa are built and tested on the userland the host runs. rigpa's Qt is
# Ubuntu's 6.10.2, the version its Mac build pins (rigpa mise.toml).
FROM ubuntu:26.04

ARG SNAPSHOT
# The base image has no CA bundle, and the snapshot is https only, so ca-certificates comes
# from the base image's own mirror first. Everything after that is from the snapshot.
RUN test -n "$SNAPSHOT" \
 && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates \
 && printf '%s\n' \
      "Types: deb" \
      "URIs: https://snapshot.ubuntu.com/ubuntu/${SNAPSHOT}" \
      "Suites: resolute resolute-updates" \
      "Components: main restricted universe" \
      "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg" \
      > /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      mmdebstrap ca-certificates dosfstools mtools e2fsprogs fdisk zstd xz-utils \
      device-tree-compiler \
      python3 openssh-client \
      cmake ninja-build make gcc g++ git \
      qt6-base-dev qt6-declarative-dev qt6-svg-dev qt6-virtualkeyboard-dev \
      qml6-module-qtquick qml6-module-qtquick-window qml6-module-qtquick-shapes \
      qml6-module-qtquick-controls qml6-module-qtquick-templates qml6-module-qtqml-workerscript \
      qml6-module-qtquick-virtualkeyboard qt6-virtualkeyboard-plugin qt6-qpa-plugins qt6-svg-plugins \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

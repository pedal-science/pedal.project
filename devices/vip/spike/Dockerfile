# The build container for vip's card: aarch64 Ubuntu 26.04, native on the M2 under colima.
# Its own packages come from the same pinned snapshot the image uses.
FROM ubuntu:26.04

ARG SNAPSHOT=20260929T000000Z
# The base image has no CA bundle, and the snapshot is https only, so ca-certificates comes
# from the base image's own mirror first. Everything after that is from the snapshot.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates \
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
      python3 openssh-client \
 && rm -rf /var/lib/apt/lists/*

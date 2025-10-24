#!/bin/sh

set -e

ROOT_PARTITION="/dev/nvme0n1p2"
BOOT_PARTITION="/dev/nvme0n1p1"

mkfs.btrfs -f $ROOT_PARTITION
# mkfs.vfat -n BOOT $BOOT_PARTITION

mount -t btrfs $ROOT_PARTITION /mnt
btrfs subvolume create /mnt/root
btrfs subvolume create /mnt/home
btrfs subvolume create /mnt/nix
btrfs subvolume create /mnt/log
btrfs subvolume create /mnt/swap

umount /mnt

mount -o subvol=root,compress=zstd,noatime $ROOT_PARTITION /mnt
mkdir /mnt/home
mount -o subvol=home,compress=zstd,noatime $ROOT_PARTITION /mnt/home
mkdir /mnt/nix
mount -o subvol=nix,compress=zstd,noatime $ROOT_PARTITION /mnt/nix
mkdir -p /mnt/var/log
mount -o subvol=log,compress=zstd,noatime $ROOT_PARTITION /mnt/var/log
mount -o subvol=swap,noatime $ROOT_PARTITION /mnt/swap

btrfs filesystem mkswapfile --size 4g --uuid clear /mnt/swap/swapfile

mkdir /mnt/boot
mount $BOOT_PARTITION /mnt/boot

nixos-generate-config --root /mnt

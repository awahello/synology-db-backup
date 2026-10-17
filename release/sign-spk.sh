#!/bin/sh
# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <offline-private-key.pem> <package.spk>" >&2
    exit 2
fi

KEY=$1
SPK=$2
[ -r "$KEY" ] || { echo "Private key is not readable" >&2; exit 1; }
[ -r "$SPK" ] || { echo "SPK is not readable" >&2; exit 1; }

openssl pkeyutl -sign -rawin -inkey "$KEY" -in "$SPK" -out "${SPK}.sig"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$SPK" > "${SPK}.sha256"
else
    shasum -a 256 "$SPK" > "${SPK}.sha256"
fi
echo "Created ${SPK}.sig and ${SPK}.sha256"


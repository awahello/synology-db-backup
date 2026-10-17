#!/bin/sh
# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
set -eu

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <public-key.pem> <package.spk> <package.spk.sig>" >&2
    exit 2
fi

PUB=$1
SPK=$2
SIG=$3
openssl pkeyutl -verify -rawin -pubin -inkey "$PUB" -in "$SPK" -sigfile "$SIG"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$SPK"
else
    shasum -a 256 "$SPK"
fi


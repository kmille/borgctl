#!/bin/bash
set -eu

sudo rm -rf template && mkdir template


VERSION="$(poetry version -s )-1"

# TODOS
# lintian output
# size?

function step1() {
    echo "2.0" > template/debian-binary
}

function step2() {
    echo "Package: borgctl
Version: $VERSION
Architecture: amd64
Maintainer: Debian Borg Collective <team+borg@tracker.debian.org>
Installed-Size: 2762
Depends: borgbackup, python3-ruamel.yaml
Suggests: borgbackup-doc
Section: admin
Priority: optional
Homepage: https://github.com/kmille/borgctl
Description: wrapper around borg backup
" > template/control

    tar -C template -cJf control.tar.xz control
    rm -rf template/control
}

function step3() {
    mkdir -p template/root/usr/lib/python3/dist-packages/
    poetry build --format wheel
    unzip -qo dist/borgctl-*.whl -d template/root/usr/lib/python3/dist-packages/
    rm -rf dist

    mkdir -p template/root/usr/bin
    echo '#!/usr/bin/python3
    # -*- coding: utf-8 -*-
import re
import sys
from borgctl.__init__ import main
if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    sys.exit(main())
    ' > template/root/usr/bin/borgctl
    chmod +x template/root/usr/bin/borgctl
    sudo chown -R 0:0 template/root
    tar -C template/root -cJf data.tar.xz .
}

function create_deb() {
    step1
    step2
    step3
    ar r "borgctl_"$VERSION"_amd64.deb" template/debian-binary control.tar.xz data.tar.xz
}

create_deb

rm -rf control.tar.xz data.tar.xz
sudo rm -rf template

wormhole send borgctl_0.4.0a0-1_amd64.deb

echo "done"

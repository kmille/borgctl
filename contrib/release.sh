#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

PACKAGE=$(poetry version | awk '{ print $1 }')

# install dev environment
poetry install

function check_prerequisites() {
    if [ -n "$(git status --untracked-files=no --porcelain)" ]; then
      echo "Working directory is not clean. Please commit all changes first"
      exit 1
    fi

    # run tests
    poetry run flake8 --ignore=E501,E265 --show-source --statistics ../$PACKAGE
    poetry run mypy ../$PACKAGE
    poetry run pytest -v -s ../tests
}


function bump_version() {
    
    #poetry version patch
    poetry version prerelease

    VERSION=$(poetry version -s)
    git add ../pyproject.toml && git commit -m "Bump to v$VERSION" --no-verify && git push
    gh release create $VERSION --generate-notes --prerelease
}


function build_and_upload_python_package() {
    poetry build
    poetry publish
}

function create_debian_package () {
    VERSION=$(poetry version -s)
    ./create-deb-package.sh
    gh release upload $VERSION ../dist/* borgctl_$VERSION-1_amd64.deb
}


function cleanup() {
    rm -rf ../dist/
    rm borgctl_$VERSION-1_amd64.deb
}


function arch_package() {
    # Update arch package
    pushd ArchLinux >/dev/null

    SHA265SUMS=$(makepkg --geninteg 2>/dev/null)
    sed -i "s/sha256sums.*/$SHA265SUMS/" PKGBUILD

    makepkg -sf
    gh release upload $VERSION *.tar.zst
    ./clean.sh
    popd > /dev/null
}

check_prerequisites
bump_version
build_and_upload_python_package
create_debian_package
arch_package
cleanup

echo "done"

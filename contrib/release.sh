#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

PACKAGE=$(poetry version | awk '{ print $1 }')
DEPLOY_PRE_RELEASE="1"
SKIP_PREREQUISITES="0"

while [[ $# -gt 0 ]]; do
  case $1 in
    -p|--prod)
      DEPLOY_PRE_RELEASE="0"
      shift # past argument
      ;;
    -s|--skip-prerequisites)
      SKIP_PREREQUISITES="1"
      shift # past argument
      ;;
  esac
done


# install dev environment
poetry install

function check_prerequisites() {

    if [[ $SKIP_PREREQUISITES == "1" ]]
    then
        return
    fi

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
    if [[ $DEPLOY_PRE_RELEASE == "0" ]]
    then
        bump_version_prod
    else
        bump_version_prerelease
    fi

}

function bump_version_prerelease() {
    poetry version prerelease
    VERSION=$(poetry version -s)
    git add ../pyproject.toml && git commit -m "Bump to v$VERSION" --no-verify && git push
    git tag -m "Bump to v$VERSION" "$VERSION"
    git push --tags
    gh release create $VERSION --generate-notes --prerelease
}


function bump_version_prod() {
    poetry version patch
    VERSION=$(poetry version -s)
    git add ../pyproject.toml && git commit -m "Bump to v$VERSION" --no-verify && git push
    git tag -m "Bump to v$VERSION" "$VERSION"
    git push --tags
    gh release create $VERSION --generate-notes
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


function create_arch_package() {
    pushd ArchLinux >/dev/null

    SHA265SUMS=$(makepkg --geninteg 2>/dev/null)
    sed -i "s/sha256sums.*/$SHA265SUMS/" PKGBUILD

    makepkg -sf
    gh release upload $VERSION *.tar.zst
    make clean
    git add PKGBUILD && git commit -m 'Update sha256sums in PKGBUILD' && git push
    popd > /dev/null
}


function cleanup() {
    rm -rf ../dist/
    rm borgctl_$VERSION-1_amd64.deb
}

check_prerequisites
bump_version
build_and_upload_python_package
create_debian_package
create_arch_package
cleanup

echo "done"

#!/bin/bash
set -euo pipefail

#if [ -n "$(git status --untracked-files=no --porcelain)" ]; then
#  echo "Working directory is not clean. Please commit all changes first"
#  exit 1
#fi

PACKAGE=$(poetry version | awk '{ print $1 }')

# install dev environment
poetry install

# run tests
# run by git hooks
poetry run flake8 --ignore=E501,E265 --show-source --statistics $PACKAGE
#poetry run mypy $PACKAGE
#sudo poetry run pytest -v -s tests

# update version
#poetry version patch
poetry version preminor

## update git version
#git add pyproject.toml
#git commit -m "Bump to v$(poetry version --short)" --no-verify
#git push
#git tag -m "Bump to v$(poetry version --short)" "v$(poetry version --short)"
#git push --tags

# build package
poetry build
poetry publish

rm -rf dist/

echo "done"

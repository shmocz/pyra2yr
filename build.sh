#!/bin/bash

set -o nounset

if [ ! -d .venv ]; then
	set -e
	python3 -m venv .venv
	.venv/bin/pip install -U pip setuptools
	.venv/bin/pip install poetry poetry-dynamic-versioning
	.venv/bin/poetry install
	# TODO(shmocz): Workaround for poetry adding empty lines to this
	git checkout pyproject.toml
	set +e
fi

function lint() {
	.venv/bin/poetry run pylint pyra2yr
}

function format() {
	.venv/bin/poetry run black pyra2yr
}

function check-format() {
	format
	d="$(git diff)"
	[ ! -z "$d" ] && { echo "$d"; exit 1; }
}

function build() {
	check-format
	set -e
	lint
	.venv/bin/poetry build
	set +e
}

$1

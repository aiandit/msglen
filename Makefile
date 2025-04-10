.PHONY: clean-pyc clean-build docs clean dist all

all: dist

help:
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "sdist - package"

clean: clean-build clean-pyc
	rm -fr htmlcov/

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info
	rm -fr tmp*

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

lint:
	flake8 --color=never --max-line-length=120 --ignore=F821 msglen
	flake8 --color=never --max-line-length=120 --ignore=E201,E202,E211,E226,E227,E231,E265,E302,E303,E305,E306,E402,F821,F841 tests

test:
	./tests/test_cmdline.sh
	tox

coverage:
	tox -e coverage

docs:
	tox -e docs

dist:
	python -m build .

PIP ?= pip
install:
	$(PIP) install .

install-dist:
	$(PIP) install -I $(shell ls -1rt dist/*.whl | tail -n 1)

venv = /var/lib/venvs/test
CMD=flake8
venv-run:
	.  $(venv)/bin/activate && $(CMD)

venv = /var/lib/venvs/test
GOAL=dist
venv-make:
	.  $(venv)/bin/activate && $(MAKE) $(MAKEFLAGS) $(GOAL)

typecheck:
	ruff check baidupcs_py

format-check:
	ruff format --check .

format:
	ruff format .

build-pyx:
	python3 build.py build_ext --inplace

test: build-pyx
	pytest -s tests/test_common.py

build: all
	rm -fr dist
	poetry build -f sdist

publish: all
	poetry publish

build-publish: build publish

all: format-check typecheck

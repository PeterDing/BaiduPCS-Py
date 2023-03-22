typecheck:
	ruff check baidupcs_py
	mypy -p baidupcs_py \
		--ignore-missing-imports \
		--warn-unreachable \
		--implicit-optional \
		--allow-redefinition \
		--disable-error-code abstract

format-check:
	black --check .

format:
	black .

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

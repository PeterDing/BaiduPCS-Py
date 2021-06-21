typecheck:
	mypy -p baidupcs_py --ignore-missing-imports --warn-unreachable

format-check:
	black --check .

format:
	black .

build-pyx:
	python build.py build_ext --inplace


build: all
	rm -fr dist
	poetry build -f sdist

publish: all
	poetry publish

build-publish: build publish

all: format-check typecheck

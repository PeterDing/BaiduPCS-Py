typecheck:
	mypy -p baidupcs_py --ignore-missing-imports --warn-unreachable

format-check:
	black --check .

format:
	black .

build-pyx:
	python build.py build_ext --inplace

build-publish: all
	rm -fr dist
	poetry build -f sdist
	poetry publish

all: format-check typecheck

typecheck:
	mypy -p baidupcs_py --ignore-missing-imports --warn-unreachable

format-check:
	black --check .

format:
	black .

build-pyx:
	python build.py build_ext --inplace

all: format-check typecheck

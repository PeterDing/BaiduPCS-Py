typecheck:
	mypy -p baidupcs_py --ignore-missing-imports --warn-unreachable

format-check:
	black --check .

format:
	black .

all: format-check typecheck

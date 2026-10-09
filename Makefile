.PHONY: test proto-update

test:
	python3 -m pip install -q -r requirements_test.txt
	python3 -m pytest -q tests/

proto-update:
	./scripts/update_proto.sh main

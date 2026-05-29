.PHONY: test sanity help

help:
	@./bin/ccopy --help

test:
	PYTHONPATH=scripts python3 -m unittest discover -s tests -v

sanity:
	./sanity.sh

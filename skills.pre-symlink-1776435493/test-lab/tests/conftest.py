"""Pytest conftest that skips test-lab blind test scripts from collection."""
# test-lab blind tests are standalone scripts invoked by test-lab/run.sh,
# NOT pytest-collectable test modules. They require skill-specific sys.path
# and command-line arguments. Skip them when pytest discovers this directory.
collect_ignore_glob = ["**/test_*.py"]

#!/bin/bash
set -e
TMPDIR=$(mktemp -d)
cat > "$TMPDIR/trivial.py" << 'PYEOF'
def add(x: int, y: int) -> int:
    return x + y
PYEOF
cd "$TMPDIR"
mypyc trivial.py 2>&1
python3 -c "from trivial import add; assert add(2,3)==5; print('PASS: mypyc compile + import works')"
rm -rf "$TMPDIR"

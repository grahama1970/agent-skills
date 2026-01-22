#!/bin/bash
LOCAL_DEV="/home/graham/workspace/experiments/anvil"
if [ -d "$LOCAL_DEV" ]; then
    cd "$LOCAL_DEV" || exit
    exec uv run anvil "$@"
else
    exec uvx --from "git+https://github.com/grahama1970/anvil.git" anvil "$@"
fi

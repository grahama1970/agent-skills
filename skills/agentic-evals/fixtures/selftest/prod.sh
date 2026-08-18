#!/usr/bin/env bash
# A substantive producer entrypoint: writes a receipt an oracle reads back.
# This stands in for a real skill entrypoint reaching a load-bearing boundary.
printf '{"phase":"settled","session":"S-1"}' > receipt.json

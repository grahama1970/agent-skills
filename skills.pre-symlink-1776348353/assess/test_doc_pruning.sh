#!/bin/bash

# Test script for documentation pruning capabilities in assess skill
# This script validates that the assess skill recognizes documentation pruning triggers

echo "Testing assess skill documentation pruning triggers..."

# Test triggers that should activate documentation pruning mode
test_triggers=(
    "prune documentation"
    "doc pruning" 
    "documentation cleanup"
    "fix documentation alignment"
    "update docs to match code"
    "deprecate outdated documentation"
    "documentation audit"
    "doc-code alignment check"
    "documentation review"
    "clean up docs"
)

echo "Documentation pruning triggers to test:"
for trigger in "${test_triggers[@]}"; do
    echo "  - $trigger"
done

echo ""
echo "These triggers should activate the enhanced assess skill's documentation pruning mode."
echo "The skill should:"
echo "1. Ask clarifying questions about documentation focus areas"
echo "2. Perform documentation inventory and cross-reference validation"
echo "3. Identify alignment issues between docs and code"
echo "4. Recommend specific pruning actions (update/deprecate/consolidate)"
echo "5. Present findings in the enhanced output format with documentation quality metrics"

echo ""
echo "To test manually, run: pi --skill assess --message 'prune documentation'"
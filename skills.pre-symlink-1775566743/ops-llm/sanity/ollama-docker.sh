#!/bin/bash
set -e

# Verify Ollama CLI version
version=$(docker exec scillm-ollama ollama --version | sed 's/ollama version is //')
expected_version="0.14.3-rc2"
if [ "$version" != "$expected_version" ]; then
  echo "ERROR: Ollama CLI version is incorrect. Expected: $expected_version, Actual: $version"
  exit 1
fi
echo "Ollama CLI version check passed: $version"

# Verify Ollama API endpoint
api_version=$(curl -s http://localhost:11434/api/version | jq -r '.version')
if [ "$api_version" != "$expected_version" ]; then
  echo "ERROR: Ollama API version is incorrect. Expected: $expected_version, Actual: $api_version"
  exit 1
fi
echo "Ollama API version check passed: $api_version"

echo "Ollama Docker sanity check passed!"
exit 0

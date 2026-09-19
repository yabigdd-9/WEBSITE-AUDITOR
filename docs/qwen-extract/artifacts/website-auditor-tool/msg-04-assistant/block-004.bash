docker run -d \
  --name ds-harness-sandbox \
  -v $(pwd)/integrations:/app/integrations \
  -v $(pwd)/outputs:/app/outputs \
  -v $(pwd)/db:/app/db:ro \ # Read-only mount for safety
  deepseek/harness:dev-preview

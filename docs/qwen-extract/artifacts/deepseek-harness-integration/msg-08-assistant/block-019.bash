# 1. Ensure you are on main and up to date
git checkout main
git pull origin main

# 2. Create the new feature branch
git checkout -b integration/deepseek-harness-phase-a

# 3. Create the directory structure for the integration
mkdir -p integrations/deepseek-harness/{tools,policies,workflows,tests}

# 4. Initialize empty placeholder files (we will fill them in next)
touch integrations/deepseek-harness/config.yaml
touch integrations/deepseek-harness/policies/permissions.yml
touch integrations/deepseek-harness/workflows/agents.yml
touch integrations/deepseek-harness/tools/mm_bridge.py
touch integrations/deepseek-harness/tests/test_integration.py
touch integrations/deepseek-harness/README.md
touch integrations/deepseek-harness/SECURITY.md

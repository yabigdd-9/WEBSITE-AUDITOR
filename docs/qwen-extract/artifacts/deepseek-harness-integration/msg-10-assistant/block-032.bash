# In /Users/dd/agent-trials/hermes/repo

# 1. Initialize DB
python3 -c "from integrations.deepseek_harness.state_machine.engine import StateMachineEngine; e = StateMachineEngine(); print('DB Initialized')"

# 2. Register Prospect
python3 << 'EOF'
from integrations.deepseek_harness.state_machine.engine import StateMachineEngine
e = StateMachineEngine()
pid = e.register_prospect('example.co.nz', 'Example Business')
print(f"Registered Prospect ID: {pid}")
if pid > 0:
    # Transition to Identity Resolved (simulated human/researcher step)
    e.transition(pid, 'IDENTITY_RESOLVED', 'hermes_sim', '', 'Domain verified')
    e.transition(pid, 'AUDIT_PENDING', 'hermes_sim', '', 'Ready for audit')
    print(f"Current State: {e.get_state(pid)}")
e.close()
EOF

# 3. Invoke Audit Tool via Bridge (Simulating Harness Call)
python3 << 'EOF'
from integrations.deepseek_harness.tools.mm_bridge import tool_audit_site
result = tool_audit_site('https://example.co.nz')
print("Audit Result Success:", result['success'])
if result['success']:
    print("Output Snippet:", result['stdout'][:200])
else:
    print("Error:", result.get('error'))
EOF

# 4. Update State to AUDITED
python3 << 'EOF'
from integrations.deepseek_harness.state_machine.engine import StateMachineEngine
e = StateMachineEngine()
# Assuming PID 1 from previous step, in real scenario we'd look it up
pid = 1 
e.transition(pid, 'AUDITED', 'deepseek_harness_sim', 'audits/example.co.nz.json', 'Audit complete')
print(f"Final State: {e.get_state(pid)}")
e.close()
EOF

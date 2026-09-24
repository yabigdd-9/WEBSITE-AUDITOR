# WEBSITE-AUDITOR Recovery

Recovery order:
1. stop duplicate workers/supervisors;
2. identify Git branch/commit;
3. check SQLite integrity;
4. inspect leases/heartbeats;
5. recover stale leases;
6. confirm outreach policy;
7. restart deterministic/lightweight workers first;
8. validate provider/browser health;
9. restore expensive demo/LLM work last;
10. record the incident and recovery evidence.

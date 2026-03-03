# SECURITY_AGENT.md (SRS aligned)

Threat model (minimum):
- Prompt injection via YouTube chat
- Token leakage via logs/traces
- Unsafe output generation
- Denial-of-service via chat bursts / reconnect storms

Required safeguards:
1) Safety Filter first (block NG categories before Bandit/LLM)
2) No secrets or OAuth artifacts in logs
3) Resource bounds (TTL, max queue size, log rotation)
4) Network hygiene (timeouts, bounded retries, circuit breaker + fallback)

SRS references:
- Appendix E (Safety categories + order)
- NFR-SEC-01, NFR-DATA-01

---
description: 'Review a PR/diff against SRS: Security, Reliability, Performance, Protocol compatibility.'
---
Review the diff with SRS in mind.

Provide:
- Top 5 risks (ranked)
- SRS references impacted (FR/NFR/TC)
- Concrete fixes with file/line guidance
- Verification plan (commands)

Checklist:
- Secrets/PII leakage
- Safety order (filter before Bandit/LLM)
- Bounded retries + timeouts
- Resource caps + TTL
- Protocol backward compatibility

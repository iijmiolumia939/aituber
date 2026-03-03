# Code Review Checklist (SRS aligned)

## SRS conformance
- [ ] Change cites FR/NFR/TC references
- [ ] Behavior matches A-3 (chat), A-7 (avatar), Appendix D (Bandit), Appendix E (Safety)
- [ ] Protocol changes are backward compatible

## Security / privacy
- [ ] No secrets committed (keys/tokens/cookies/OAuth artifacts)
- [ ] Logs redact tokens and minimize PII (hash author IDs)
- [ ] Safety Filter runs before Bandit/LLM
- [ ] Prompt injection cases covered in tests

## Reliability
- [ ] External calls have timeouts + bounded retries + backoff
- [ ] Reconnect loops are capped
- [ ] Resource bounds: TTL/limits for seen_set, queues, logs

## Performance
- [ ] Meets latency target (NFR-LAT-01) conceptually (no new blocking/slow paths)
- [ ] 30Hz loops do minimal work (mouth_open)

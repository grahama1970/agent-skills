# Intervention Controls

Session: session-1774356636

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Dogpile: automated UX testing + synthetic training in graph tools and robotics sim (subagent-service/0)
- `2`: Build CDP interaction harness for UX Lab projects (subagent-service/0)
- `3`: Build adversarial command generator using /prompt-lab (subagent-service/1)
- `4`: Build blind evaluator — grades QuerySpec without seeing expected result (subagent-service/1)
- `5`: Integrate voice command generation via /converse + PersonaPlex (subagent-service/2)
- `6`: Run interaction batch: 200 text + 50 voice commands against Binary Explorer (subagent-service/2)
- `7`: Build grader: compare actual vs expected QuerySpec (blind evaluation) (subagent-service/3)
- `8`: Auto-retrain intent classifier from graded labels via /create-gpt (subagent-service/3)
- `9`: Wire /episodic-archiver for chat transcript archival (subagent-service/3)
- `10`: Convergence loop: run batches until intent accuracy exceeds 85% (subagent-service/4)
- `11`: Verification: end-to-end test with 50 novel commands + 10 voice (local/4)

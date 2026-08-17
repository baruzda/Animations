# AGENTS.md

## Minimal and verifiable changes

- Before implementation, check the current requirements, code, and project source of truth.
- Distinguish verified facts from hypotheses, assumptions, and decisions. Do not silently turn unknowns into facts.
- If uncertainty is low-risk and reversible, choose the most conservative reasonable assumption, record it briefly, and continue.
- Ask for confirmation before decisions that may cause data loss, change public contracts, weaken security/privacy, create cost, affect external systems, or are difficult to reverse.
- Implement the smallest solution that satisfies the current requirement. Do not add speculative abstractions, flexibility, configurability, or features “for the future”.
- Change only code directly required by the task plus necessary tests, types, migrations, documentation, and contract-compatible support changes. No drive-by refactoring.
- Before coding a non-trivial change, define observable acceptance criteria and the verification signal.
- Do not report a task as complete until the relevant verification has actually been run. If a check cannot run, state that explicitly and use the best available substitute signal.
- Before finishing, reread the final diff and ensure every changed hunk can be traced to the user request or an explicitly required supporting change.

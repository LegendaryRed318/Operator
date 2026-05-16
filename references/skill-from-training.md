# Skill-from-Training Reference

When the user asks JARVIS to save trained knowledge as a persistent skill, follow this process.

---

## When to generate a skill

Generate a skill when the user says any of:
- "add it to the skills folder"
- "save this as a skill"
- "remember this permanently"
- "install it"
- "make it a skill so you can use it later"

Also proactively *offer* to generate a skill at the end of every training session.

---

## What goes into a training-derived skill

A skill generated from a training session has two jobs:
1. Give JARVIS fast recall of the subject matter in future sessions
2. Tell JARVIS how to answer questions about this topic confidently

### YAML Frontmatter

```yaml
---
name: <topic-slug>
description: >
  JARVIS knowledge base for <Topic>. Use this skill whenever the user asks about
  <topic>, mentions <topic>, or asks JARVIS to recall what it learned about <topic>.
  Compiled: <DATE>. Covers: <2-3 sentence scope summary>.
trained_on: <DATE>
source: <"web" | repo_url>
---
```

### Skill Body Sections

```markdown
# <Topic> — JARVIS Knowledge Base

> Compiled: <DATE> | Source: <web/repo>

## Quick Reference
[The most important 5–10 facts about this topic that JARVIS should recall instantly]

## Core Concepts
[Fundamental understanding — same as the Core Fundamentals section from the report,
 but condensed. This is what JARVIS knows cold.]

## Current State (as of <DATE>)
[Time-sensitive info. Note the date prominently so future sessions know how fresh it is.]

## Key Resources
[Links, repos, docs, dashboards worth fetching for current data]

## Answer Patterns
[How JARVIS should handle common questions about this topic. E.g.:]

**If asked "what is <topic>?"** → Lead with the one-liner, then the core mechanism.
**If asked "what's happening with <topic> right now?"** → Note that this knowledge base
  was compiled on <DATE> and trigger a fresh web search for current data.
**If asked about <specific subtopic>?** → [guidance]

## Known Gaps
[What JARVIS didn't fully cover in training, or where knowledge may go stale quickly]
```

---

## File Structure

```
/tmp/jarvis_training/skills/<topic-slug>/
├── SKILL.md          ← the skill file (above format)
└── (no scripts needed for knowledge-only skills)
```

---

## Naming Convention

| Trained on | Skill name |
|---|---|
| Bitcoin (web) | `bitcoin-knowledge` |
| github.com/tiangolo/fastapi | `fastapi-repo` |
| Ethereum + DeFi | `ethereum-defi-knowledge` |
| Operator repo | `operator-codebase` |

Always lowercase, hyphenated, end in `-knowledge` for web training or `-repo` for repo training.

---

## After Generating

1. Save the skill to `/tmp/jarvis_training/skills/<topic-slug>/SKILL.md`
2. Use `present_files` to give the user the file
3. Tell the user: *"Install this by placing the `<topic-slug>/` folder into your Operator skills directory. JARVIS will have instant recall of this knowledge in all future sessions."*
4. Offer to run a quick test: *"Want me to test the skill by asking myself a question about <topic>?"*

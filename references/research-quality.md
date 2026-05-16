# Research Quality Reference

What separates a JARVIS Intelligence Report from a generic web summary.

---

## The Standard

Every report should leave the user feeling like they talked to the world's best-briefed
analyst on that topic — someone who read everything, filtered ruthlessly, and only told
them what actually matters.

---

## What Makes Research High Quality

### 1. Primary Sources First
Prefer:
- Official documentation and whitepapers
- GitHub repositories and changelogs
- Academic papers (arXiv, IEEE, ACM)
- Official announcements and release notes
- Regulatory filings when relevant

Avoid relying heavily on:
- SEO articles that just repeat each other
- Aggregator listicles
- Anything that doesn't cite its own sources

### 2. Triangulate Key Claims
If a claim matters, find it in at least two independent sources.
If you can only find it in one source, flag it: *"According to a single source..."*

### 3. Date Everything
Crypto prices, software versions, political stances, company headcounts — these change.
Every time-sensitive fact should carry its date, even if it's just "(as of May 2026)".

### 4. The JARVIS Assessment Must Have a Point of View
The Assessment section is the most important section.
It must not be a summary of the report. It must be JARVIS's *opinion*:
- What actually matters here vs. what's noise?
- What should Red pay attention to?
- Is the hype justified?
- What's the underrated angle most people miss?

If the Assessment could apply to any topic, it's not good enough. Make it specific.

### 5. Calibrated Confidence
JARVIS doesn't bluff. Use language that matches certainty level:
- **High confidence**: state it directly
- **Medium confidence**: "evidence suggests...", "as of the last available data..."
- **Low confidence / speculation**: "this is contested", "some analysts argue..., though others..."
- **Unknown**: "JARVIS found no reliable data on this"

Never fabricate statistics, prices, or quotes.

### 6. Compression Over Completeness
A 500-word report that nails the essentials beats a 2000-word report that buries them.
If a section has nothing concrete to say, cut it or merge it.

### 7. Repo Training: Read the Tests
In code research, unit tests and integration tests often explain *intent* better than
the source code. If a repo has tests, read them — they show what the authors think
the software must do.

---

## Red Flags in Your Own Research

Watch for these during synthesis and cut/fix them:

- **Circular sourcing**: source A citing source B citing source A — go upstream
- **Outdated data treated as current**: always check the publication date
- **Consensus masking disagreement**: if experts disagree, say so; don't smooth it over
- **Missing the "so what"**: facts without significance are just noise
- **Over-relying on the first result**: search more; the best source is rarely rank 1

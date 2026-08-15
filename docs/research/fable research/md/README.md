# Deep-research reports — converted for agent reading (2026-08-07)

Saurabh ran the six prompts from `docs/reviews/2026-08-07-deep-research-prompts.md`
through TWO deep-research models independently. Originals are `.docx` in
`../chatgpt/` and `../gemini/`; these `.md` conversions preserve text, tables,
and hyperlinks (stdlib converter, no pandoc on machine).

| Prompt | Topic | ChatGPT report | Gemini report |
|---|---|---|---|
| P1 | Competitive landscape: voice-operated Windows control | P1-chatgpt.md | P1-gemini.md |
| P2 | Accessibility reality check (blind-user demand) | P2-chatgpt.md | P2-gemini.md |
| P3 | Technical SOTA: UI automation on CPU-only Windows | P3-chatgpt.md | P3-gemini.md |
| P4 | The rented cortex: agent brain for zero budget | P4-chatgpt.md | P4-gemini.md |
| P5 | India legal/ToS for assisted automation | P5-chatgpt.md | P5-gemini.md |
| P6 | Far-field voice endpoint hardware (room project) | P6-chatgpt.md | P6-gemini.md |

Citation formats differ by model:
- **Gemini**: live markdown hyperlinks (44-65 per report) — directly checkable.
- **ChatGPT**: `【N†L..】` markers referencing its browsing session — they show a
  claim WAS sourced, but the links are not resolvable; spot-verify anything
  load-bearing before acting on it.

Reading rule for synthesis: where both models agree WITH sources → strong
evidence. Where they disagree → flag it and weigh source quality, don't average.
Where both are silent → the point stays UNDECIDED.

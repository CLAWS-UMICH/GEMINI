# CORVUS Intent Design Decisions — TSS 2026

## Classification Approach

- **Single-label classification** to start — one intent per command
- Architecture allows switching to multi-label later (swap softmax → sigmoid, CrossEntropyLoss → BCEWithLogitsLoss)
- **87 total intents** at time of writing — hidden layer bumped to 256 to handle increased capacity

---

## Response Behavior Rules

### Voice (Piper TTS)
- **Always plays** for every intent — no silent responses

### UI Actions
- UI panels only open on **explicit trigger words**: "open", "show me", "pull up", "display"
- Ambiguous general queries (no explicit UI trigger) default to opening the relevant menu

---

## Intent Routing Patterns

### Pattern 1 — Specific field query (voice only)
Astronaut asks for a specific telemetry value.

- Examples: "what's my heart rate", "check my oxygen level", "how much battery do I have"
- Maps to: `vitals_heart_rate`, `vitals_oxy_pri_storage`, `vitals_batt_time_left` etc.
- Behavior: **voice response only**, no UI change
- Route: **local** (placeholder data for now, live LMCC data later)

### Pattern 2 — Explicit UI action (UI + voice)
Astronaut explicitly asks for a panel to open.

- Examples: "open vitals panel", "pull up navigation", "show me the task list"
- Maps to: `open_menu_vitals`, `open_menu_navigation`, `open_menu_tasks` etc.
- Behavior: **open UI panel + voice confirms** ("Vitals panel open")
- Route: **local**

### Pattern 3 — Ambiguous general query (UI + cloud voice)
Astronaut asks a general question without specifying a field or explicitly requesting UI.

- Examples: "check my vitals", "how are my vitals", "vitals status"
- Maps to: `open_menu_vitals`
- Behavior: **split response**
  - Local: open UI panel immediately (~400ms)
  - Cloud: send all telemetry to Claude API → natural language summary with anomaly detection (~1500ms, read by Piper)
- Example spoken response: *"Heart rate normal at 72 bpm. Oxygen at 94% — slightly low, monitor closely. Battery has 2 hours 15 minutes remaining."*
- Rationale: UI is already visible while waiting for cloud, so latency is acceptable. Claude can flag anomalies and prioritize — far more useful than hardcoded placeholder.

---

## Split Response Pattern

`open_menu_vitals` is the first intent using both local and cloud paths simultaneously:

```
local_handler.py  → UI action (immediate)
cloud_handler.py  → voice response (parallel, ~1500ms)
```

This is the template for future ambiguous intents that benefit from intelligent cloud summarization alongside an immediate UI action.

---

## Near-Identical Intent Pairs (Red Flags)

These intent pairs have nearly identical natural language phrasing and will be hard to distinguish. Training examples must be written carefully with disambiguating context words.

| Group | Intents | Mitigation |
|-------|---------|------------|
| Suit O2 | `vitals_oxy_pri_storage` vs `vitals_oxy_sec_storage` | Include "primary"/"secondary" in examples |
| Suit O2 pressure | `vitals_oxy_pri_pressure` vs `vitals_oxy_sec_pressure` | Same |
| Suit fans | `vitals_fan_pri_rpm` vs `vitals_fan_sec_rpm` | Same |
| Scrubbers | `vitals_scrubber_a_co2_storage` vs `vitals_scrubber_b_co2_storage` | Include "A"/"B" in examples |
| Suit pressure | `vitals_suit_pressure_total` vs `_oxy` vs `_co2` vs `_other` | Use specific gas names in examples |
| Coolant | `vitals_coolant_gas_pressure` vs `vitals_coolant_liquid_pressure` | Same |
| Cross-context (suit vs rover) | `vitals_fan_pri_rpm` vs `get_fan_pri_rpm` | Include "suit"/"rover" context words |
| Cross-context (suit vs rover) | `vitals_coolant_storage` vs `get_coolant_storage` | Same |
| Cross-context (suit vs rover) | `vitals_temperature` vs `get_cabin_temperature` | Same |
| Cross-context (suit vs rover) | `vitals_oxy_pri_storage` vs `get_oxygen_tank` | Same |

---

## Entity Extraction — Future Work

Primary/secondary and A/B modifiers are currently handled by having separate intents. A proper NER component will be added later to:
- Merge near-identical pairs into single intents
- Extract modifiers ("primary", "secondary", "A", "B") as entities
- Reduce total intent count and improve accuracy on ambiguous commands

---

## get/set Pairs

PR cabin control intents come in get/set pairs. Training examples must clearly distinguish:
- **get** → query words: "is the heating on", "what's the cooling status", "are the lights on"
- **set** → action words: "turn on the heating", "activate cooling", "switch on the lights"

Pairs: `get/set_cabin_heating`, `get/set_cabin_cooling`, `get/set_co2_scrubber`, `get/set_lights_on`

---

## Training Data Notes

- **16 examples per intent** target — 8 minimum for SetFit
- Quality over quantity — 12 diverse realistic phrasings beat 30 similar ones
- Include natural speech patterns — astronauts speak under stress, keep it realistic
- For near-identical pairs, always include disambiguating context words
- Can retrain after practical testing — add failure cases as new examples, retrain in ~30 seconds

---

*Last updated: TSS 2026 pre-season planning session.*

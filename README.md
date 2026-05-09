# GEMINI | The Guided EVA Mission Infrastructure for Navigation Insight

**Collaborative Lab for Advancing Work in Space (CLAWS), University of Michigan**

## Installation

1. Install [Unity Hub](https://unity.com/download) and add editor version **6000.2.7f2** (or install the version pinned in this repo’s `ProjectSettings/ProjectVersion.txt`).
2. **Windows** is  required for full HoloLens / UWP workflows and for Microsoft’s Mixed Reality tooling when configuring or updating MRTK/OpenXR packages.
3. Clone and open the project in Unity:
  ```bash
   git clone https://github.com/CLAWS-UMICH/GEMINI.git
  ```
   Then open the cloned folder as a Unity project.

## Key features

High-level capabilities reflected in the Unity client and backend folders:

- **Vitals** — suit and mission vitals UI and controllers
- **Minimap** — overview map with layered views and waypoint placement
- **Navigation** — interest, station, hazard, and companion waypoints, along with world and minimap path visualization
- **Task list** — procedural task tracking UI
- **AI assistant** — in-headset assistant for task and navigational aid
- **LMCC & telemetry** — WebSocket client toward LMCC-style services; TSS-oriented connection hooks for simulation / telemetry
- **Multimodal input** — supports voice interaction, eye-gaze targeting, button-based UI interaction, and multidirectional/spatial mouse input 
- **Related systems:** Python-based rover / PRCC-side logic, see [AI/README.md](AI/README.md)


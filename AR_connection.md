# AR Integration Reference — CORVUS ↔ Navigation.unity

This document maps every AR component from the merged Navigation scene that CORVUS can hook into, what each exposes, and how to wire it up via voice intents.

---

## 1. AIA Circle Animation

**Location:** `Assets/CLAWS/Phase-1/Features/AIA/`

### What exists
| Asset | Status |
|---|---|
| `AIA_Stages.controller` | Animator controller with states wired up |
| `Awake_Animation.anim` | Wake word detected |
| `Start_animation.anim` | Startup / idle |
| `answer_Animation.anim` | Responding / speaking |
| `listening.png`, `awake.png`, ring sprites | Visual assets in-place |
| `AIA_guide.cs` | Shell script — **empty, ready to fill** |

### How to hook in
`AIA_guide.cs` already holds a `[SerializeField] Animator AIA_Animator` reference. You need to add public methods that `CorvusController` calls:

| CORVUS Event | Method to add to AIA_guide | Animator trigger |
|---|---|---|
| Wake word detected | `OnWake()` | `"Awake"` |
| Recording started | `OnListening()` | `"Listening"` (maps to `Start_animation`) |
| Response received | `OnResponding()` | `"Answer"` (maps to `answer_Animation`) |
| Idle / done | `OnIdle()` | `"Idle"` |

`CorvusController` fires:
- `OnWakeWordDetected()` → call `AIA_guide.OnWake()`
- `StartRecording()` → call `AIA_guide.OnListening()`
- `OnIntentReceived` event → call `AIA_guide.OnResponding()`

---

## 2. Dialogue / Text Display System

**Location:** `Assets/CLAWS/Phase-1/Features/AIA/Scripts/`

### Scripts
| Script | What it does |
|---|---|
| `DialogueManager.cs` | Typewriter text display. Call `StartDialogue(dialogue)` to queue sentences, `DisplayNextSentence()` to step through them |
| `Dialogue.cs` | Data container: `string name` + `string[] sentences` |
| `DialogueTrigger.cs` | Calls `manager.StartDialogue(dialogue)` — inspector-wired trigger |

### How to hook in
When `CorvusController` receives a response from Python, it currently calls `GetResponseForIntent()` and speaks via TTS. You can also pipe the same text into `DialogueManager` to display it on-screen:

```
OnIntentReceived → build a Dialogue object with the response text → dialogueManager.StartDialogue(dialogue)
```

This gives you simultaneous TTS speech + typewriter text display in the AR UI.

---

## 3. Side Menu

**Location:** `Assets/CLAWS/Phase-1/Features/`

### Script: `SideMenuTrigger.cs`
| Method | What it does |
|---|---|
| `ShiftMenu()` | Slides menu open, starts gaze-watching coroutine |
| `ShiftMenuBack()` | No-op — retraction is automatic on gaze exit |

**Auto-retract:** Menu closes itself after `retractDelay` seconds (default 0.5s) when gaze leaves it.

**Prefab:** `Sidemenu.prefab` in `Assets/CLAWS/Phase-1/Features/`

### Voice hookup
Intent `"open_menu"` → call `sideMenuTrigger.ShiftMenu()`
Intent `"close_menu"` → not needed (gaze handles it), but you could call `ShiftMenuBack()` to force-close

---

## 4. Navigation Screens

**Location:** `Assets/CLAWS/Phase-1/Waypoints/NavigationFrontend.cs`

### Available screen methods (all public, callable directly)
| Method | What it opens |
|---|---|
| `openCompanionScreen()` | Full map + companion camera (default) |
| `openPOIScreen()` | Points of interest map |
| `openGeoScreen()` | Geology waypoints map |
| `openDangerScreen()` | Danger zone map |
| `openStationScreen()` | Station map |
| `openWaypointScreen()` | Create waypoint UI |
| `openFeatureScreen()` | Re-opens last active screen |
| `closeScreens()` | Closes all navigation screens |

### Navigation methods
| Method | What it does |
|---|---|
| `NavigateToPosition(Vector3)` | Sets pathfinding target to world position |
| `navigateToEV(int)` | Pathfinds to EV2 teammate's position |
| `openDangerNavigation(int)` | Opens nav screen + paths to danger waypoint by index |
| `openGeoNavigation(int)` | Opens nav screen + paths to geo waypoint by index |
| `openPOINavigation(int)` | Opens nav screen + paths to POI waypoint by index |
| `openStationNavigation(int)` | Opens nav screen + paths to station waypoint by index |

### Voice hookup examples
| Voice intent | Call |
|---|---|
| `"open navigation"` | `navigationFrontend.openCompanionScreen()` |
| `"show waypoints"` | `navigationFrontend.openWaypointScreen()` |
| `"show danger zones"` | `navigationFrontend.openDangerScreen()` |
| `"show points of interest"` | `navigationFrontend.openPOIScreen()` |
| `"close map"` | `navigationFrontend.closeScreens()` |
| `"navigate to teammate"` | `navigationFrontend.navigateToEV(0)` |

---

## 5. Vitals Display

**Location:** `Assets/CLAWS/Phase-1/Vitals/Scripts/VitalsController.cs`

### What's tracked (per astronaut)
Heart rate, temperature, O2 consumption, CO2 production, primary/secondary O2 pressure & storage, helmet CO2, suit pressures, scrubber A/B, fans, coolant (liquid & gas), battery time, oxygen time — with battery and oxygen **slider bars**.

### Two screens
- `vitalsFirstAstronautScreen` — EV1
- `vitalsSecondAstronautScreen` — EV2

### Alert system (`AlertController.cs`)
Three alert types defined in `AlertEnum`:
- `Vital_Battery`
- `Vital_Heart`
- `Vital_CO2`

`AlertController` is currently a shell — logic not yet implemented.

### Voice hookup examples
| Voice intent | Action |
|---|---|
| `"check vitals"` / `"show vitals"` | SetActive vitals panel for current astronaut |
| `"check partner vitals"` | SetActive second astronaut screen |
| `"close vitals"` | SetActive(false) on vitals panel |

---

## 6. CorvusController Hook Points

**Location:** `Assets/CLAWS/Backend/Networking/CorvusController.cs`

These are the events/moments you attach AR component calls to:

| Hook point | When it fires | What to call |
|---|---|---|
| `OnWakeWordDetected()` | User says "hey corvus" | `AIA_guide.OnWake()` |
| `StartRecording()` | After wake word, mic opens | `AIA_guide.OnListening()` |
| `OnIntentReceived` event | Python response received | `AIA_guide.OnResponding()`, `DialogueManager.StartDialogue()`, open/close screens |
| `OnRecordStop` → transcription done | STT finished | optionally show transcription text |

The `OnIntentReceived` event signature:
```csharp
event Action<string intent, float confidence, CorvusLatency latency>
```

---

## 7. What Still Needs Work

| Component | Gap |
|---|---|
| `AIA_guide.cs` | Empty — needs state methods + CorvusController subscription |
| `AlertController.cs` | Shell — alert display logic not implemented |
| `WaypointsMenuController.cs` | Entirely commented out — old version, replaced by `NavigationFrontend` |
| Voice → navigation | Need to add navigation intents to Python classifier (`open_poi_screen`, `navigate_to_airlock`, etc.) |
| Dialogue display | Not yet connected to CORVUS response text |
| Side menu voice trigger | `open_menu` intent not yet in classifier |

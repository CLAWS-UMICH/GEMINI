using UnityEngine;
using UnityEngine.Events;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using MixedReality.Toolkit.UX;

/// <summary>
/// Drives the radial menu as a two-level navigation UI: categories (Station, Interest, Add, Companions, Hazards)
/// then waypoints. Selecting a waypoint shows path on minimap and requires a second click on that wedge to confirm navigation.
/// </summary>
public class RadialMenuNavigationController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private RadialMenuBuilder radialBuilder;
    [SerializeField] private NavigationController navigationController;
    [SerializeField] private Pathfinding pathfindingSystem;
    [Header("Add waypoint (minimap placement)")]
    [Tooltip("Leave empty if MinimapWaypointPlacement is on the same NavigationController GameObject. Otherwise drag the MinimapWaypointPlacement component (e.g. on your overlay object) here so Add finds it.")]
    [SerializeField] private MinimapWaypointPlacement waypointPlacementOverride;

    [Header("Category icons (assign in Editor — used for the 5 main wedges)")]
    [Tooltip("Sprite for Station. Leave empty to use the letter icon.")]
    [SerializeField] private Sprite stationSprite;
    [Tooltip("Sprite for Interest (POI).")]
    [SerializeField] private Sprite interestSprite;
    [Tooltip("Sprite for Add waypoint.")]
    [SerializeField] private Sprite addSprite;
    [Tooltip("Sprite for Companions.")]
    [SerializeField] private Sprite companionsSprite;
    [Tooltip("Sprite for Hazards.")]
    [SerializeField] private Sprite hazardsSprite;

    [Header("Companion waypoint icons (assign in Editor — used when Companions is opened)")]
    [Tooltip("Sprite for LTV. Leave empty to use the letter icon.")]
    [SerializeField] private Sprite ltvSprite;
    [Tooltip("Sprite for PR / ROVER. Leave empty to use the letter icon.")]
    [SerializeField] private Sprite prSprite;

    private enum MenuMode { Categories, Waypoints, AddPickType }
    private MenuMode currentMode = MenuMode.Categories;
    private string currentCategory = ""; // "Station", "Interest", "Hazards", "Companions"
    private int selectedWaypointIndex = -1;
    private List<Waypoint> currentWaypointList = new List<Waypoint>();
    private Vector3? pendingTargetPosition; // waypoint selected, path on minimap, waiting for second-click confirmation

    private const string LABEL_BACK = "Back";
    private const string LABEL_CANCEL_NAV = "Cancel Navigation";
    private const string LABEL_CONFIRM_NAV = "Click Again to Confirm";
    private const string LABEL_SELECT = "Select";
    private const int COMPANION_LTV_SELECTION_ID = -2;
    private const int COMPANION_ROVER_SELECTION_ID = -3;

    [Header("Waypoint confirmation")]
    [Tooltip("How long (seconds) a repeated click on the same wedge confirms navigation.")]
    [SerializeField] private float confirmSelectionWindowSeconds = 2.0f;
    [Tooltip("Persistent selected wedge highlight color while waiting for confirm click.")]
    [SerializeField] private Color selectedWedgeHighlightColor = new Color(0.60f, 0.82f, 1f, 1f);

    [Header("Navigation state")]
    [Tooltip("How close (meters) the astronaut must be to the target to consider navigation complete.")]
    [SerializeField] private float navigationArrivalDistance = 1.0f;
    [Tooltip("How often (seconds) we check for arrival while navigating.")]
    [SerializeField] private float navigationCheckIntervalSeconds = 0.2f;

    private bool isNavigating;
    private Vector3 activeTargetPosition;
    private Coroutine navigationMonitorCoroutine;
    private float lastSelectionTime = -999f;
    private int selectedWedgeVisualIndex = -1;
    private string selectedWedgeOriginalLabel = "";
    private RadialWedgeHighlight selectedWedgeHighlight;
    private RadialWedgeLabelExtension selectedWedgeExtension;

    private void Start()
    {
        if (radialBuilder == null) radialBuilder = GetComponent<RadialMenuBuilder>();
        if (radialBuilder == null)
        {
            Debug.LogError("RadialMenuNavigationController: RadialMenuBuilder not assigned.");
            return;
        }

        radialBuilder.onCenterClick = new UnityEvent();
        radialBuilder.onCenterClick.AddListener(OnCenterClicked);
        BuildCategoryMenu();
    }

    /// <summary>Rebuilds the five-wedge category menu and opens the radial (e.g. after minimap waypoint placement).</summary>
    public void ResetRadialToCategoriesAndOpen()
    {
        BuildCategoryMenu();
        if (radialBuilder != null)
            radialBuilder.OpenMenu();
    }

    private void BuildCategoryMenu()
    {
        ClearSelectedWaypointVisual();
        currentMode = MenuMode.Categories;
        currentCategory = "";
        selectedWaypointIndex = -1;
        pendingTargetPosition = null;
        lastSelectionTime = -999f;
        isNavigating = false;
        activeTargetPosition = default;
        StopNavigationMonitor();
        currentWaypointList.Clear();

        radialBuilder.entries.Clear();
        radialBuilder.segmentCount = 5;
        radialBuilder.centerLabel = LABEL_SELECT;
        radialBuilder.SetCenterLabel(LABEL_SELECT);

        AddCategoryEntry("Station", "S", stationSprite, () => OpenWaypointList("Station", GetStationWaypoints()));
        AddCategoryEntry("Interest", "I", interestSprite, () => OpenWaypointList("Interest", GetPOIWaypoints()));
        AddCategoryEntry("Add", "+", addSprite, () => OnAddClicked());
        AddCategoryEntry("Companions", "C", companionsSprite, () => OpenCompanionsList());
        AddCategoryEntry("Hazards", "H", hazardsSprite, () => OpenWaypointList("Hazards", GetDangerWaypoints()));

        radialBuilder.BuildMenu();
    }

    private void AddCategoryEntry(string label, string icon, Sprite sprite, UnityAction onClick)
    {
        var entry = new RadialMenuEntry { label = label, iconUnicode = icon, iconSprite = sprite };
        entry.onClick = new UnityEvent();
        entry.onClick.AddListener(onClick);
        radialBuilder.entries.Add(entry);
    }

    private List<Waypoint> GetStationWaypoints()
    {
        return navigationController != null ? navigationController.StationWaypointList : new List<Waypoint>();
    }

    private List<Waypoint> GetPOIWaypoints()
    {
        return navigationController != null ? navigationController.POIWaypointList : new List<Waypoint>();
    }

    private List<Waypoint> GetDangerWaypoints()
    {
        return navigationController != null ? navigationController.DangerWaypointList : new List<Waypoint>();
    }

    private void OpenWaypointList(string category, List<Waypoint> waypoints)
    {
        if (IsMinimapPlacementBlocking())
            return;

        ClearSelectedWaypointVisual();
        currentMode = MenuMode.Waypoints;
        currentCategory = category;
        // Shallow copy: BuildCategoryMenu / BuildAddWaypointTypeMenu call Clear() on currentWaypointList;
        // must not clear NavigationController's live Station/POI/Danger lists.
        currentWaypointList = waypoints != null ? new List<Waypoint>(waypoints) : new List<Waypoint>();
        selectedWaypointIndex = -1;
        pendingTargetPosition = null;
        lastSelectionTime = -999f;
        isNavigating = false;
        activeTargetPosition = default;
        StopNavigationMonitor();

        radialBuilder.entries.Clear();
        int count = waypoints != null ? waypoints.Count : 0;
        radialBuilder.segmentCount = Mathf.Clamp(count, 2, 12);

        if (count == 0)
        {
            var empty = new RadialMenuEntry { label = "None", iconUnicode = "-" };
            empty.onClick = new UnityEvent();
            radialBuilder.entries.Add(empty);
            radialBuilder.segmentCount = 1;
        }
        else
        {
            int maxShow = Mathf.Min(count, 12);
            for (int i = 0; i < maxShow; i++)
            {
                int index = i;
                Waypoint wp = waypoints[i];
                string name = string.IsNullOrEmpty(wp.Name) ? $"Waypoint {index + 1}" : wp.Name;
                string letter = name.Length > 0 ? name[0].ToString() : "?";
                var entry = new RadialMenuEntry { label = name, iconUnicode = letter };
                entry.onClick = new UnityEvent();
                entry.onClick.AddListener(() => SelectWaypoint(index));
                radialBuilder.entries.Add(entry);
            }
        }

        radialBuilder.centerLabel = LABEL_BACK;
        radialBuilder.SetCenterLabel(LABEL_BACK);
        radialBuilder.BuildMenu();
    }

    private void OpenCompanionsList()
    {
        if (IsMinimapPlacementBlocking())
            return;

        ClearSelectedWaypointVisual();
        currentMode = MenuMode.Waypoints;
        currentCategory = "Companions";
        currentWaypointList = new List<Waypoint>();
        selectedWaypointIndex = -1;
        pendingTargetPosition = null;
        lastSelectionTime = -999f;
        isNavigating = false;
        activeTargetPosition = default;
        StopNavigationMonitor();

        radialBuilder.entries.Clear();
        radialBuilder.segmentCount = 2;

        var ltv = new RadialMenuEntry { label = "LTV", iconUnicode = "LTV", iconSprite = ltvSprite };
        ltv.onClick = new UnityEvent();
        ltv.onClick.AddListener(() => SelectCompanionLTV());
        radialBuilder.entries.Add(ltv);

        var rover = new RadialMenuEntry { label = "ROVER", iconUnicode = "R", iconSprite = prSprite };
        rover.onClick = new UnityEvent();
        rover.onClick.AddListener(() => SelectCompanionRover());
        radialBuilder.entries.Add(rover);

        radialBuilder.centerLabel = LABEL_BACK;
        radialBuilder.SetCenterLabel(LABEL_BACK);
        radialBuilder.BuildMenu();
    }

    MinimapWaypointPlacement ResolveWaypointPlacement()
    {
        if (waypointPlacementOverride != null)
            return waypointPlacementOverride;
        return navigationController != null
            ? navigationController.GetComponent<MinimapWaypointPlacement>()
            : null;
    }

    bool IsMinimapPlacementBlocking()
    {
        var p = ResolveWaypointPlacement();
        return p != null && p.IsPlacementInProgress;
    }

    private void OnAddClicked()
    {
        if (IsMinimapPlacementBlocking())
            return;

        var placement = ResolveWaypointPlacement();
        if (placement == null)
        {
            Debug.LogError("RadialMenuNavigationController: No MinimapWaypointPlacement found. Assign Waypoint Placement Override on the radial, or add MinimapWaypointPlacement to NavigationController.");
            return;
        }

        BuildAddWaypointTypeMenu();
    }

    /// <summary>Three wedges: Station, Hazard, Interest — pick type before minimap placement.</summary>
    private void BuildAddWaypointTypeMenu()
    {
        if (IsMinimapPlacementBlocking())
            return;

        ClearSelectedWaypointVisual();
        currentMode = MenuMode.AddPickType;
        currentCategory = "";
        selectedWaypointIndex = -1;
        pendingTargetPosition = null;
        lastSelectionTime = -999f;
        isNavigating = false;
        activeTargetPosition = default;
        StopNavigationMonitor();
        currentWaypointList.Clear();

        radialBuilder.entries.Clear();
        radialBuilder.segmentCount = 3;
        radialBuilder.centerLabel = LABEL_BACK;
        radialBuilder.SetCenterLabel(LABEL_BACK);

        AddCategoryEntry("Station", "S", stationSprite, () => OnAddTypeWedgeClicked(WaypointType.STATION));
        AddCategoryEntry("Hazard", "H", hazardsSprite, () => OnAddTypeWedgeClicked(WaypointType.DANGER));
        AddCategoryEntry("Interest", "I", interestSprite, () => OnAddTypeWedgeClicked(WaypointType.POI));

        radialBuilder.BuildMenu();
    }

    private void OnAddTypeWedgeClicked(WaypointType type)
    {
        if (IsMinimapPlacementBlocking())
            return;

        if (currentMode != MenuMode.AddPickType)
            return;

        BeginAddPlacement(type);
    }

    private void BeginAddPlacement(WaypointType type)
    {
        var placement = ResolveWaypointPlacement();
        if (placement == null)
        {
            Debug.LogError("RadialMenuNavigationController: No MinimapWaypointPlacement for BeginAddPlacement.");
            return;
        }

        placement.BeginFromRadial(this, pathfindingSystem, type);
        if (radialBuilder != null && placement.IsPlacementInProgress)
        {
            radialBuilder.centerLabel = LABEL_BACK;
            radialBuilder.SetCenterLabel(LABEL_BACK);
        }
    }

    private void SelectWaypoint(int index)
    {
        if (currentWaypointList == null || index < 0 || index >= currentWaypointList.Count)
            return;

        Waypoint wp = currentWaypointList[index];
        Vector3 targetPosition = new Vector3((float)wp.UNITYposX, 0, (float)wp.UNITYposZ);
        HandleWaypointSelection(index, index, targetPosition);
    }

    private void SelectCompanionLTV()
    {
        GameObject ltvObject = GameObject.Find("LTV_ICON");
        if (ltvObject == null)
        {
            Debug.LogWarning("RadialMenuNavigation: LTV_ICON not found.");
            return;
        }
        Vector3 targetPosition = ltvObject.transform.position;
        targetPosition.y = 0;
        HandleWaypointSelection(COMPANION_LTV_SELECTION_ID, 0, targetPosition);
    }

    private void SelectCompanionRover()
    {
        GameObject roverObject = GameObject.Find("PR_ICON");
        if (roverObject == null) roverObject = GameObject.Find("ROVER");
        if (roverObject == null)
        {
            Debug.LogWarning("RadialMenuNavigation: PR_ICON/ROVER not found.");
            return;
        }
        Vector3 targetPosition = roverObject.transform.position;
        targetPosition.y = 0;
        HandleWaypointSelection(COMPANION_ROVER_SELECTION_ID, 1, targetPosition);
    }

    private void HandleWaypointSelection(int selectionId, int wedgeIndex, Vector3 targetPosition)
    {
        bool isConfirmClick = selectedWaypointIndex == selectionId
            && pendingTargetPosition.HasValue;

        if (isConfirmClick)
        {
            BeginNavigationFromPendingTarget();
            return;
        }

        SelectTargetAndShowPathOnMinimap(targetPosition);
        selectedWaypointIndex = selectionId;
        lastSelectionTime = Time.unscaledTime;
        MarkSelectedWaypointVisual(wedgeIndex);
    }

    /// <summary>Run pathfinding and show path only on minimap until user confirms by clicking the selected wedge again.</summary>
    private void SelectTargetAndShowPathOnMinimap(Vector3 targetPosition)
    {
        if (pathfindingSystem == null) return;

        pathfindingSystem.SetTarget(targetPosition);
        pathfindingSystem.ShowMinimapOnly();

        pendingTargetPosition = targetPosition;
        radialBuilder.SetCenterLabel(LABEL_BACK);
        radialBuilder.centerLabel = LABEL_BACK;
    }

    private void BeginNavigationFromPendingTarget()
    {
        if (!pendingTargetPosition.HasValue || pathfindingSystem == null)
            return;

        pathfindingSystem.ShowWorldAndMinimap();
        activeTargetPosition = pendingTargetPosition.Value;
        pendingTargetPosition = null;
        isNavigating = true;
        selectedWaypointIndex = -1;
        lastSelectionTime = -999f;
        if (selectedWedgeExtension != null && !string.IsNullOrEmpty(selectedWedgeOriginalLabel))
        {
            selectedWedgeExtension.SetLabelImmediate(selectedWedgeOriginalLabel);
            selectedWedgeExtension.SetPinned(false);
        }
        radialBuilder.SetCenterLabel(LABEL_CANCEL_NAV);
        radialBuilder.centerLabel = LABEL_CANCEL_NAV;

        StartNavigationMonitor();
    }

    private void OnCenterClicked()
    {
        if (radialBuilder == null) return;

        string currentCenter = radialBuilder.centerLabel ?? "";

        // Cancel navigation (wheel stays open while navigating)
        if (currentCenter == LABEL_CANCEL_NAV && isNavigating)
        {
            CancelNavigation();
            return;
        }

        var placement = ResolveWaypointPlacement();
        if (placement != null && placement.IsPlacementInProgress && currentCenter == LABEL_BACK)
        {
            placement.CancelPlacement();
            return;
        }

        if (currentMode == MenuMode.AddPickType && (currentCenter == LABEL_BACK || string.IsNullOrEmpty(currentCenter)))
        {
            ClearSelectedWaypointVisual();
            BuildCategoryMenu();
            return;
        }

        if (currentMode == MenuMode.Waypoints && (currentCenter == LABEL_BACK || string.IsNullOrEmpty(currentCenter)))
        {
            ClearSelectedWaypointVisual();
            BuildCategoryMenu();
            return;
        }
    }

    private void StartNavigationMonitor()
    {
        StopNavigationMonitor();
        navigationMonitorCoroutine = StartCoroutine(NavigationMonitorCoroutine());
    }

    private void StopNavigationMonitor()
    {
        if (navigationMonitorCoroutine != null)
        {
            StopCoroutine(navigationMonitorCoroutine);
            navigationMonitorCoroutine = null;
        }
    }

    private IEnumerator NavigationMonitorCoroutine()
    {
        while (isNavigating)
        {
            // If astronaut data isn't available yet, wait and try again.
            if (AstronautInstance.User == null || AstronautInstance.User.current == null)
            {
                yield return new WaitForSeconds(navigationCheckIntervalSeconds);
                continue;
            }

            Vector3 astronautPos = new Vector3(
                (float)AstronautInstance.User.current.posX,
                0f,
                (float)AstronautInstance.User.current.posZ
            );

            float dist = Vector3.Distance(astronautPos, activeTargetPosition);
            if (dist <= navigationArrivalDistance)
            {
                OnNavigationArrived();
                yield break;
            }

            yield return new WaitForSeconds(navigationCheckIntervalSeconds);
        }
    }

    private void CancelNavigation()
    {
        isNavigating = false;
        StopNavigationMonitor();
        pendingTargetPosition = null;
        selectedWaypointIndex = -1;
        lastSelectionTime = -999f;
        ClearSelectedWaypointVisual();

        if (pathfindingSystem != null)
            pathfindingSystem.ClearTarget();

        radialBuilder.SetCenterLabel(LABEL_BACK);
        radialBuilder.centerLabel = LABEL_BACK;
    }

    private void OnNavigationArrived()
    {
        isNavigating = false;
        StopNavigationMonitor();
        pendingTargetPosition = null;
        selectedWaypointIndex = -1;
        lastSelectionTime = -999f;
        ClearSelectedWaypointVisual();

        if (pathfindingSystem != null)
            pathfindingSystem.ClearTarget();

        // End navigation with the radial wheel: close it once arrival is reached.
        radialBuilder.SetCenterLabel(LABEL_BACK);
        radialBuilder.centerLabel = LABEL_BACK;
        radialBuilder.CloseMenu();
        BuildCategoryMenu();
    }

    private void MarkSelectedWaypointVisual(int wedgeIndex)
    {
        ClearSelectedWaypointVisual();
        selectedWedgeVisualIndex = wedgeIndex;

        GameObject wedgeGo = FindInteractiveWedgeObject(wedgeIndex);
        if (wedgeGo == null)
            return;

        selectedWedgeHighlight = wedgeGo.GetComponent<RadialWedgeHighlight>();
        if (selectedWedgeHighlight != null)
            selectedWedgeHighlight.SetSelected(true, selectedWedgeHighlightColor);

        selectedWedgeExtension = wedgeGo.GetComponent<RadialWedgeLabelExtension>();
        if (selectedWedgeExtension != null)
        {
            selectedWedgeOriginalLabel = selectedWedgeExtension.GetLabelText();
            selectedWedgeExtension.SetPinnedLabelImmediate(LABEL_CONFIRM_NAV);
        }
        else
        {
            TextMeshPro label = FindWedgeExtensionLabel(wedgeIndex);
            if (label != null)
            {
                selectedWedgeOriginalLabel = label.text;
                label.text = LABEL_CONFIRM_NAV;
            }
        }
    }

    private void ClearSelectedWaypointVisual()
    {
        if (selectedWedgeHighlight != null)
            selectedWedgeHighlight.SetSelected(false);
        if (selectedWedgeExtension != null && !string.IsNullOrEmpty(selectedWedgeOriginalLabel))
        {
            selectedWedgeExtension.SetLabelImmediate(selectedWedgeOriginalLabel);
            selectedWedgeExtension.SetPinned(false);
        }
        else
        {
            if (selectedWedgeExtension != null)
                selectedWedgeExtension.SetPinned(false);

            if (selectedWedgeVisualIndex >= 0 && !string.IsNullOrEmpty(selectedWedgeOriginalLabel))
            {
                TextMeshPro label = FindWedgeExtensionLabel(selectedWedgeVisualIndex);
                if (label != null)
                    label.text = selectedWedgeOriginalLabel;
            }
        }

        selectedWedgeVisualIndex = -1;
        selectedWedgeOriginalLabel = "";
        selectedWedgeHighlight = null;
        selectedWedgeExtension = null;
    }

    private GameObject FindInteractiveWedgeObject(int wedgeIndex)
    {
        if (radialBuilder == null)
            return null;

        string prefix = $"Wedge_{wedgeIndex}_";
        Transform root = radialBuilder.transform;
        for (int i = 0; i < root.childCount; i++)
        {
            Transform child = root.GetChild(i);
            if (child == null || !child.name.StartsWith(prefix))
                continue;

            if (child.GetComponent<PressableButton>() != null)
                return child.gameObject;
        }

        return null;
    }

    private TextMeshPro FindWedgeExtensionLabel(int wedgeIndex)
    {
        if (radialBuilder == null)
            return null;

        string extensionRootName = $"Wedge_{wedgeIndex}_LabelExtension";
        Transform extensionRoot = radialBuilder.transform.Find(extensionRootName);
        if (extensionRoot == null)
            return null;

        Transform labelTf = extensionRoot.Find("Label");
        return labelTf != null ? labelTf.GetComponent<TextMeshPro>() : null;
    }
}

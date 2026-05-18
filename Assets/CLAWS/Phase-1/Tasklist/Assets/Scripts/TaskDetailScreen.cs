using UnityEngine;
using TMPro;
using System.Collections;
using System.Collections.Generic;
using UnityEngine.InputSystem;

public class TaskDetailScreen : MonoBehaviour
{
    [Header("UI References")]
    public GameObject taskMainMenuRoot;
    public GameObject taskDetailMenuRoot;
    public TextMeshPro titleText;
    public List<TextMeshPro> taskTexts;
    public List<GameObject> mainMenuTaskItems;

    [Header("TSS")]
    [SerializeField] private TSSConnection tssConnection;

    [Header("Colors")]
    public Color titleColor = Color.white;
    public Color activeColor = Color.white;
    public Color doneColor = Color.gray;

    [Header("Input")]
    [Tooltip("Enable to advance task steps with gamepad/XR square (West) button.")]
    public bool enableSquareAdvance = true;

    const int FIXED_GROUP_COUNT = LtvErrorTaskSupport.MaxTaskCount;

    readonly List<TaskGroup> groups = new List<TaskGroup>();
    readonly List<Vector3> slotPositions = new List<Vector3>();

    int completedUpTo = -1;
    TaskGroup activeGroup;
    Subscription<LtvErrorsUpdatedEvent> ltvErrorsSubscription;

    void Awake()
    {
        if (tssConnection == null)
            tssConnection = FindObjectOfType<TSSConnection>();
    }

    void Start()
    {
        if (mainMenuTaskItems != null)
        {
            foreach (GameObject btn in mainMenuTaskItems)
            {
                if (btn != null)
                    slotPositions.Add(btn.transform.localPosition);
            }
        }

        ltvErrorsSubscription = EventBus.Subscribe<LtvErrorsUpdatedEvent>(OnLtvErrorsUpdated);

        if (tssConnection != null && tssConnection.TryGetActiveLtvErrorProcedures(out LtvErrorProcedure[] active))
            SyncLtvTaskGroups(active);

        ShowTaskMainMenu();
    }

    void OnDestroy()
    {
        if (ltvErrorsSubscription != null)
        {
            EventBus.Unsubscribe(ltvErrorsSubscription);
            ltvErrorsSubscription = null;
        }
    }

    void Update()
    {
        if (!enableSquareAdvance)
            return;

        bool squarePressed = Gamepad.current != null && Gamepad.current.buttonWest.wasPressedThisFrame;
        if (squarePressed)
            MarkStepDone();
    }

    void OnLtvErrorsUpdated(LtvErrorsUpdatedEvent e)
    {
        SyncLtvTaskGroups(e?.ActiveProcedures);
    }

    /// <param name="activeFromTss">Procedures with needs_resolved true (from LtvErrorsUpdatedEvent or TryGetActiveLtvErrorProcedures).</param>
    public void SyncLtvTaskGroups(LtvErrorProcedure[] activeFromTss)
    {
        List<LtvErrorProcedure> selected = LtvErrorTaskSupport.SelectTopTasks(activeFromTss);

        var dynamicGroups = new List<TaskGroup>();
        foreach (TaskGroup group in groups)
        {
            if (!IsLtvGroup(group))
                dynamicGroups.Add(group);
        }

        TaskGroup previouslyActive = activeGroup;
        string previousLtvCode = previouslyActive?.ltvCode;
        int previousCompletedUpTo = completedUpTo;

        groups.Clear();
        foreach (LtvErrorProcedure procedure in selected)
        {
            string title = LtvErrorTaskSupport.BuildTaskTitle(procedure);
            string[] steps = LtvErrorTaskSupport.ParseProcedureSteps(procedure.procedures);
            groups.Add(new TaskGroup(title, procedure.code, steps));
        }

        groups.AddRange(dynamicGroups);
        RefreshMainMenuButtons();

        TaskGroup replacementActive = FindReplacementActiveGroup(previouslyActive, previousLtvCode);
        if (previouslyActive != null && replacementActive == null)
        {
            activeGroup = null;
            completedUpTo = -1;
            if (taskDetailMenuRoot != null && taskDetailMenuRoot.activeSelf)
                ShowTaskMainMenu();
            else if (groups.Count > 0)
                ShowGroup(0);
            else
                ShowTaskMainMenu();
        }
        else if (replacementActive != null)
        {
            activeGroup = replacementActive;
            int lastStep = activeGroup.tasks != null ? activeGroup.tasks.Length - 1 : -1;
            completedUpTo = Mathf.Clamp(previousCompletedUpTo, -1, lastStep);
            if (titleText != null)
                titleText.text = BuildDetailTitle(activeGroup);
            RefreshSlots();
        }
        else if (groups.Count > 0 && activeGroup == null)
        {
            ShowGroup(0);
        }
    }

    TaskGroup FindReplacementActiveGroup(TaskGroup previous, string previousLtvCode)
    {
        if (previous == null)
            return null;

        if (!string.IsNullOrEmpty(previousLtvCode))
        {
            foreach (TaskGroup group in groups)
            {
                if (string.Equals(group?.ltvCode, previousLtvCode, System.StringComparison.OrdinalIgnoreCase))
                    return group;
            }
            return null;
        }

        return groups.Contains(previous) ? previous : null;
    }

    void RefreshMainMenuButtons()
    {
        if (mainMenuTaskItems == null)
            return;

        for (int i = 0; i < mainMenuTaskItems.Count; i++)
        {
            GameObject button = mainMenuTaskItems[i];
            if (button == null)
                continue;

            bool hasTask = i < groups.Count;
            button.SetActive(hasTask);

            if (hasTask)
                SetMainMenuButtonLabel(button, groups[i].title);
        }

        UpdateMainMenuLayout();
    }

    static void SetMainMenuButtonLabel(GameObject button, string title)
    {
        if (button == null || string.IsNullOrEmpty(title))
            return;

        TextMeshPro tmp = button.GetComponentInChildren<TextMeshPro>(includeInactive: true);
        if (tmp != null)
            tmp.text = title;
    }

    public void ShowGroup(int index)
    {
        if (index < 0 || index >= groups.Count)
            return;

        activeGroup = groups[index];
        completedUpTo = -1;

        if (titleText != null)
        {
            titleText.text = BuildDetailTitle(activeGroup);
            titleText.color = titleColor;
        }

        RefreshSlots();
    }

    string BuildDetailTitle(TaskGroup group)
    {
        if (group == null)
            return string.Empty;

        string cleanTitle = group.title;
        if (!string.IsNullOrEmpty(group.ltvCode) && cleanTitle.StartsWith(group.ltvCode + " - "))
        {
            cleanTitle = cleanTitle.Substring(group.ltvCode.Length + 3);
        }

        int total = group.tasks != null ? group.tasks.Length : 0;
        if (taskTexts == null || total <= taskTexts.Count || total == 0)
            return cleanTitle;

        int currentStep = completedUpTo < 0 ? 1 : Mathf.Min(completedUpTo + 2, total);
        return $"{cleanTitle} ({currentStep}/{total})";
    }

    public void ShowTaskMainMenu()
    {
        if (groups.Count > 0)
            ShowGroup(0);
        else
        {
            if (titleText != null)
                titleText.text = "No active LTV tasks";
            HideTaskSlots();
        }

        if (taskMainMenuRoot != null)
            taskMainMenuRoot.SetActive(true);
        if (taskDetailMenuRoot != null)
            taskDetailMenuRoot.SetActive(false);
    }

    public void ShowTaskDetailMenu(int index)
    {
        ShowGroup(index);
        if (taskMainMenuRoot != null)
            taskMainMenuRoot.SetActive(false);
        if (taskDetailMenuRoot != null)
            taskDetailMenuRoot.SetActive(true);
    }

    public void MarkStepDone()
    {
        if (activeGroup == null || activeGroup.tasks == null || activeGroup.tasks.Length == 0)
            return;

        int nextCompleted = completedUpTo + 1;
        if (nextCompleted >= activeGroup.tasks.Length)
        {
            if (IsLtvGroup(activeGroup))
            {
                /*
                 * ═══════════════════════════════════════════════════════════════════════════
                 * Passive / evaluator-driven mode — Unity did not notify TSS.
                 * ═══════════════════════════════════════════════════════════════════════════
                ShowTaskMainMenu();
                return;
                */

                if (tssConnection != null &&
                    LtvErrorTaskSupport.TryGetProcedureIndex(activeGroup.ltvCode, out int procedureIndex))
                {
                    StartCoroutine(CompleteLtvTaskAndReturnToMenu(procedureIndex));
                    return;
                }

                ShowTaskMainMenu();
                return;
            }

            int currentTaskIndex = groups.IndexOf(activeGroup);
            if (currentTaskIndex >= 0 && mainMenuTaskItems != null &&
                currentTaskIndex < mainMenuTaskItems.Count &&
                mainMenuTaskItems[currentTaskIndex] != null)
            {
                mainMenuTaskItems[currentTaskIndex].SetActive(false);
                UpdateMainMenuLayout();
            }

            ShowTaskMainMenu();
            return;
        }

        completedUpTo = nextCompleted;

        if (titleText != null)
            titleText.text = BuildDetailTitle(activeGroup);

        RefreshSlots();
    }

    public bool AddTaskGroup(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            return false;
        groups.Add(new TaskGroup(name.Trim(), null, name.Trim()));
        RefreshMainMenuButtons();
        return true;
    }

    public bool DeleteTaskGroupByName(string name, out string resolvedName)
    {
        resolvedName = null;
        int i = FindDynamicGroupIndex(name);
        if (i < 0)
            return false;

        resolvedName = groups[i].title;
        bool wasActive = activeGroup == groups[i];
        groups.RemoveAt(i);
        RefreshMainMenuButtons();
        if (wasActive)
            ShowTaskMainMenu();
        return true;
    }

    public bool CompleteByName(string name, out string resolvedName)
    {
        resolvedName = null;
        if (string.IsNullOrWhiteSpace(name))
            return false;

        string needle = name.Trim().ToLowerInvariant();

        if (activeGroup != null)
        {
            int nextIdx = completedUpTo + 1;
            if (nextIdx >= 0 && nextIdx < activeGroup.tasks.Length)
            {
                string nextStep = activeGroup.tasks[nextIdx];
                if (nextStep != null && nextStep.ToLowerInvariant().Contains(needle))
                {
                    resolvedName = nextStep;
                    MarkStepDone();
                    return true;
                }
            }
        }

        for (int g = 0; g < groups.Count; g++)
        {
            TaskGroup grp = groups[g];
            if (grp?.tasks == null)
                continue;

            for (int s = 0; s < grp.tasks.Length; s++)
            {
                string step = grp.tasks[s];
                if (step == null)
                    continue;
                if (step.ToLowerInvariant().Contains(needle))
                {
                    resolvedName = step;
                    ShowTaskDetailMenu(g);
                    completedUpTo = s;
                    RefreshSlots();
                    return true;
                }
            }
        }

        int dyn = FindDynamicGroupIndex(name);
        if (dyn >= 0)
        {
            resolvedName = groups[dyn].title;
            bool wasActive = activeGroup == groups[dyn];
            groups.RemoveAt(dyn);
            RefreshMainMenuButtons();
            if (wasActive)
                ShowTaskMainMenu();
            return true;
        }

        return false;
    }

    /// <summary>
    /// Open a task group by LTV error code or description substring. Returns group index or -1.
    /// </summary>
    public int FindLtvGroupIndex(string codeOrName)
    {
        if (string.IsNullOrWhiteSpace(codeOrName))
            return -1;

        string needle = codeOrName.Trim().ToLowerInvariant();

        for (int i = 0; i < groups.Count && i < FIXED_GROUP_COUNT; i++)
        {
            TaskGroup g = groups[i];
            if (g == null || !IsLtvGroup(g))
                continue;

            if (!string.IsNullOrEmpty(g.ltvCode) &&
                g.ltvCode.Trim().Equals(needle, System.StringComparison.OrdinalIgnoreCase))
                return i;

            if (g.title != null && g.title.ToLowerInvariant().Contains(needle))
                return i;
        }

        return -1;
    }

    public bool TryOpenLtvTask(string codeOrName)
    {
        int index = FindLtvGroupIndex(codeOrName);
        if (index < 0 && groups.Count > 0 && IsLtvGroup(groups[0]))
            index = 0;
        if (index < 0)
            return false;

        ShowTaskDetailMenu(index);
        return true;
    }

    int FindDynamicGroupIndex(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            return -1;

        string needle = name.Trim().ToLowerInvariant();
        for (int i = 0; i < groups.Count; i++)
        {
            if (IsLtvGroup(groups[i]) || groups[i]?.title == null)
                continue;
            string title = groups[i].title.ToLowerInvariant();
            if (title == needle || title.Contains(needle) || needle.Contains(title))
                return i;
        }
        return -1;
    }

    IEnumerator CompleteLtvTaskAndReturnToMenu(int procedureIndex)
    {
        if (tssConnection != null)
            yield return tssConnection.PostLtvProcedureNeedsResolved(procedureIndex, needsResolved: false);

        ShowTaskMainMenu();
    }

    static bool IsLtvGroup(TaskGroup group)
    {
        return group != null && !string.IsNullOrEmpty(group.ltvCode);
    }

    void RefreshSlots()
    {
        if (taskTexts == null || activeGroup == null || activeGroup.tasks == null)
            return;

        int startTask = completedUpTo < 0 ? 0 : completedUpTo;

        for (int slot = 0; slot < taskTexts.Count; slot++)
        {
            if (taskTexts[slot] == null)
                continue;

            int taskIndex = startTask + slot;

            if (taskIndex < activeGroup.tasks.Length)
            {
                taskTexts[slot].transform.parent.gameObject.SetActive(true);
                taskTexts[slot].text = activeGroup.tasks[taskIndex];
                bool isDone = slot == 0 && completedUpTo >= 0;
                taskTexts[slot].color = isDone ? doneColor : activeColor;
            }
            else
            {
                taskTexts[slot].transform.parent.gameObject.SetActive(false);
            }
        }
    }

    void HideTaskSlots()
    {
        if (taskTexts == null)
            return;

        foreach (TextMeshPro taskText in taskTexts)
        {
            if (taskText != null && taskText.transform.parent != null)
                taskText.transform.parent.gameObject.SetActive(false);
        }
    }

    public void UpdateMainMenuLayout()
    {
        if (mainMenuTaskItems == null)
            return;

        int availableSlotIndex = 0;

        for (int i = 0; i < mainMenuTaskItems.Count; i++)
        {
            GameObject button = mainMenuTaskItems[i];
            if (button != null && button.activeSelf)
            {
                if (availableSlotIndex < slotPositions.Count)
                {
                    button.transform.localPosition = slotPositions[availableSlotIndex];
                    availableSlotIndex++;
                }
            }
        }
    }
}


public class TaskGroup
{
    public string title;
    public string ltvCode;
    public string[] tasks;

    public TaskGroup(string title, string ltvCode, params string[] tasks)
    {
        this.title = title;
        this.ltvCode = ltvCode;
        this.tasks = tasks;
    }
}
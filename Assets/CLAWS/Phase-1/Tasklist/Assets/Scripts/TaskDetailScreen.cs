using UnityEngine;
using TMPro;
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
    private List<Vector3> slotPositions = new List<Vector3>();

    [Header("Colors")]
    public Color titleColor    = Color.white;
    public Color activeColor   = Color.white;
    public Color doneColor     = Color.gray;

    [Header("Input")]
    [Tooltip("Enable to advance task steps with gamepad/XR square (West) button.")]
    public bool enableSquareAdvance = true;

    // First FIXED_GROUP_COUNT groups are the fixed procedure list. Anything appended
    // beyond that is a dynamic voice-created task (Add_task) and is the only kind
    // that Delete_task / Complete_task-by-name can remove.
    const int FIXED_GROUP_COUNT = 5; // Changed from 3 to 5

    readonly List<TaskGroup> groups = new List<TaskGroup>
    {
        new TaskGroup("Exit Recovery Mode (ERM) (1/5)",
            "Get ERM steps from AIA",
            "Follow steps",
            "Wait for ERM confirmation",
            "Move to next task"),

        new TaskGroup("System Diagnosis (2/5)",
            "Ask AIA to run diagnosis",
            "Do visual check",
            "Wait for results",
            "Follow fix instructions from AIA"),

        new TaskGroup("System Restart (3/5)",
            "Follow AIA restart steps",
            "Wait for completion",
            "Verify position data"),

        // --- Hardcoded Task 4 --- 
        new TaskGroup("Task 4 (4/5)",
             "Do step 1",
             "Do step 2",
             "Do step 3"),

        // --- Hardcoded Task 5 ---
        new TaskGroup("Task 5 (5/5)",
            "Do step 1",
            "Do step 2")
    };
    // -------------------------------------------------------

    int completedUpTo = -1;
    TaskGroup activeGroup;

    void Start()
    {
        Debug.Log($"[TaskDetailScreen] Start called on '{gameObject.name}'");
        Debug.Log($"[TaskDetailScreen] titleText={(titleText == null ? "NULL" : titleText.name)}, taskTexts.Count={taskTexts.Count}");

        if (mainMenuTaskItems != null)
        {
            foreach (GameObject btn in mainMenuTaskItems)
            {
                if (btn != null) slotPositions.Add(btn.transform.localPosition);
            }
        }

        ShowTaskMainMenu();
    }

    void Update()
    {
        if (!enableSquareAdvance) return;

        bool squarePressed = Gamepad.current != null && Gamepad.current.buttonWest.wasPressedThisFrame;

        if (squarePressed)
        {
            MarkStepDone();
        }
    }

    public void ShowGroup(int index)
    {
        Debug.Log($"[TaskDetailScreen] ShowGroup({index})");
        if (index < 0 || index >= groups.Count) { Debug.Log($"[TaskDetailScreen] index {index} out of range"); return; }
        activeGroup    = groups[index];
        completedUpTo  = -1;

        if (titleText != null)
        {
            titleText.text  = activeGroup.title;
            titleText.color = titleColor;
        }

        RefreshSlots();
    }

    public void ShowTaskMainMenu()
    {
        ShowGroup(0);
        if (taskMainMenuRoot != null) taskMainMenuRoot.SetActive(true);
        if (taskDetailMenuRoot != null) taskDetailMenuRoot.SetActive(false);
    }

    public void ShowTaskDetailMenu(int index)
    {
        ShowGroup(index);
        if (taskMainMenuRoot != null) taskMainMenuRoot.SetActive(false);
        if (taskDetailMenuRoot != null) taskDetailMenuRoot.SetActive(true);
    }

    public void MarkStepDone()
    {
        if (activeGroup == null) return;

        int nextCompleted = completedUpTo + 1;
        if (nextCompleted >= activeGroup.tasks.Length)
        {
            // Close the detail menu only on the press AFTER all steps were completed.
            
            // Find out which task index we just finished
            int currentTaskIndex = groups.IndexOf(activeGroup);

            // Check if we have a matching main menu item for this index, and hide it
            if (currentTaskIndex >= 0 && currentTaskIndex < mainMenuTaskItems.Count)
            {
                if (mainMenuTaskItems[currentTaskIndex] != null)
                {
                    mainMenuTaskItems[currentTaskIndex].SetActive(false);
                    UpdateMainMenuLayout();
                }
            }

            ShowTaskMainMenu();
            return;
        }

        completedUpTo = nextCompleted;
        RefreshSlots();
    }

    /// <summary>
    /// Append a new dynamic task group (one-step) created from a voice command.
    /// Returns true on success. Speaks-side description is left to the caller.
    /// </summary>
    public bool AddTaskGroup(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return false;
        groups.Add(new TaskGroup(name.Trim(), name.Trim()));
        return true;
    }

    /// <summary>
    /// Remove a dynamic task group whose title fuzzy-matches <paramref name="name"/>.
    /// Fixed procedure groups (index 0..FIXED_GROUP_COUNT-1) cannot be removed.
    /// </summary>
    public bool DeleteTaskGroupByName(string name, out string resolvedName)
    {
        resolvedName = null;
        int i = FindDynamicGroupIndex(name);
        if (i < 0) return false;
        resolvedName = groups[i].title;
        bool wasActive = (activeGroup == groups[i]);
        groups.RemoveAt(i);
        if (wasActive) ShowTaskMainMenu();
        return true;
    }

    /// <summary>
    /// Best-effort "complete" by name. Tries (in order):
    ///   1. Match against the next step in the active group: call <see cref="MarkStepDone"/>.
    ///   2. Match against any step in any group: switch to that group and advance.
    ///   3. Match against a dynamic group title: remove that single-step group.
    /// Returns true on a successful match; false otherwise (caller may fall back to
    /// <see cref="MarkStepDone"/> on the currently active group).
    /// </summary>
    public bool CompleteByName(string name, out string resolvedName)
    {
        resolvedName = null;
        if (string.IsNullOrWhiteSpace(name)) return false;
        string needle = name.Trim().ToLowerInvariant();

        // 1) Next step in the currently active group
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

        // 2) Search every group's steps; on a hit, open that group and advance to (just past) the step
        for (int g = 0; g < groups.Count; g++)
        {
            TaskGroup grp = groups[g];
            if (grp == null || grp.tasks == null) continue;
            for (int s = 0; s < grp.tasks.Length; s++)
            {
                string step = grp.tasks[s];
                if (step == null) continue;
                if (step.ToLowerInvariant().Contains(needle))
                {
                    resolvedName = step;
                    ShowTaskDetailMenu(g);
                    completedUpTo = s; // mark this step (and prior) as done
                    RefreshSlots();
                    return true;
                }
            }
        }

        // 3) Match a dynamic group by title - remove it
        int dyn = FindDynamicGroupIndex(name);
        if (dyn >= 0)
        {
            resolvedName = groups[dyn].title;
            bool wasActive = (activeGroup == groups[dyn]);
            groups.RemoveAt(dyn);
            if (wasActive) ShowTaskMainMenu();
            return true;
        }

        return false;
    }

    int FindDynamicGroupIndex(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return -1;
        string needle = name.Trim().ToLowerInvariant();
        for (int i = FIXED_GROUP_COUNT; i < groups.Count; i++)
        {
            if (groups[i]?.title == null) continue;
            string title = groups[i].title.ToLowerInvariant();
            if (title == needle || title.Contains(needle) || needle.Contains(title))
                return i;
        }
        return -1;
    }

    void RefreshSlots()
    {
        Debug.Log($"RefreshSlots: taskTexts.Count={taskTexts.Count}, group={activeGroup.title}");

        int startTask = completedUpTo == -1 ? 0 : completedUpTo;

        for (int slot = 0; slot < taskTexts.Count; slot++)
        {
            if (taskTexts[slot] == null) { Debug.Log($"Slot {slot} is NULL"); continue; }

            int taskIndex = startTask + slot;

            if (taskIndex < activeGroup.tasks.Length)
            {
                taskTexts[slot].transform.parent.gameObject.SetActive(true);
                taskTexts[slot].text  = activeGroup.tasks[taskIndex];
                bool isDone = (slot == 0 && completedUpTo >= 0);
                taskTexts[slot].color = isDone ? doneColor : activeColor;
                Debug.Log($"[TaskDetailScreen] Slot {slot} → '{activeGroup.tasks[taskIndex]}' | selfActive={taskTexts[slot].gameObject.activeSelf} | inHierarchy={taskTexts[slot].gameObject.activeInHierarchy} | parent='{taskTexts[slot].transform.parent.name}' parentActive={taskTexts[slot].transform.parent.gameObject.activeSelf}");
            }
            else
            {
                taskTexts[slot].transform.parent.gameObject.SetActive(false);
                Debug.Log($"Slot {slot} hidden (no task at index {taskIndex})");
            }
        }
    }

    public void UpdateMainMenuLayout()
    {
        int availableSlotIndex = 0;

        for (int i = 0; i < mainMenuTaskItems.Count; i++)
        {
            GameObject button = mainMenuTaskItems[i];

            if (button != null && button.activeSelf == true)
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
    public string   title;
    public string[] tasks;

    public TaskGroup(string title, params string[] tasks)
    {
        this.title = title;
        this.tasks = tasks;
    }
}
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

    [Header("Colors")]
    public Color titleColor    = Color.white;
    public Color activeColor   = Color.white;
    public Color doneColor     = Color.gray;

    [Header("Input")]
    [Tooltip("Enable to advance task steps with gamepad/XR square (West) button.")]
    public bool enableSquareAdvance = true;
    readonly TaskGroup[] groups = new TaskGroup[]
    {
        new TaskGroup("Exit Recovery Mode (ERM) (1/3)",
            "Get ERM steps from AIA",
            "Follow steps",
            "Wait for ERM confirmation",
            "Move to next task"),

        new TaskGroup("System Diagnosis (2/3)",
            "Ask AIA to run diagnosis",
            "Do visual check",
            "Wait for results",
            "Follow fix instructions from AIA"),

        new TaskGroup("System Restart (3/3)",
            "Follow AIA restart steps",
            "Wait for completion",
            "Verify position data"),
    };
    // -------------------------------------------------------

    int completedUpTo = -1;
    TaskGroup activeGroup;

    void Start()
    {
        Debug.Log($"[TaskDetailScreen] Start called on '{gameObject.name}'");
        Debug.Log($"[TaskDetailScreen] titleText={(titleText == null ? "NULL" : titleText.name)}, taskTexts.Count={taskTexts.Count}");
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
        if (index < 0 || index >= groups.Length) { Debug.Log($"[TaskDetailScreen] index {index} out of range"); return; }
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
            ShowTaskMainMenu();
            return;
        }

        completedUpTo = nextCompleted;
        RefreshSlots();
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
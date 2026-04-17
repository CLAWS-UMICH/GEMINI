using MixedReality.Toolkit.UX;
using UnityEngine;

public class ScreenManager : MonoBehaviour
{
    public GameObject main;
    public GameObject screens;
    public GameObject vitals;
    public GameObject navigation;
    public GameObject PR;
    public GameObject UIA;
    public GameObject messaging;
    public GameObject tasklist;
    public ToggleCollection menuToggleCollection;
    [Header("Navigation Radial Menu")]
    [Tooltip("Radial navigation menu GameObject (e.g. 'RadialMenu' in the main scene).")]
    public GameObject radialMenu;
    private bool messagingSuppressionLogged;

    void Update()
    {
        // Legacy scene callbacks can still attempt to re-open Messaging.
        // Keep Messaging hard-disabled in this workflow.
        if (messaging != null && messaging.activeSelf)
        {
            messaging.SetActive(false);
            if (!messagingSuppressionLogged)
            {
                Debug.Log("ScreenManager: Suppressed Messaging reactivation.");
                messagingSuppressionLogged = true;
            }
        }
    }

    private void EnterUia()
    {
        if (UIA == null) return;
        UIA.SetActive(true);
        var uiaController = UIA.GetComponent<UIAController>();
        uiaController?.openFeatureScreen();
    }

    private void ExitUia()
    {
        if (UIA == null) return;
        var uiaController = UIA.GetComponent<UIAController>();
        if (uiaController != null)
        {
            uiaController.closeFeatureScreen();
        }
        else
        {
            UIA.SetActive(false);
        }
    }



    void Start()
    {
        menuToggleCollection.OnToggleSelected.AddListener(OnToggleChanged);
        transform.Find("Screens").gameObject.SetActive(true);
        DeactivateAllScreens();

        // Ensure radial menu starts hidden and in default state
        if (radialMenu != null)
        {
            radialMenu.SetActive(false);
            var builder = radialMenu.GetComponent<RadialMenuBuilder>();
            if (builder != null)
            {
                builder.BuildMenu();
                builder.CloseMenu();
            }
        }
    }


    private void OnToggleChanged(int index)
    {
        Debug.Log($"Toggle changed to index: {index}");
        openScreen(index);
    }


    public void openScreen(int index)
    {
        main.transform.localPosition = new Vector3(0, 0, 0);
        DeactivateAllScreens();
        switch (index)
        {
            case 0:
                Debug.Log("Opening UIA screen");
                EnterUia();
                break;
            case 1:
                Debug.Log("Opening Navigation radial menu");

                // Show radial navigation instead of the old Navigation screen
                if (radialMenu != null)
                {
                    radialMenu.SetActive(true);
                    var builder = radialMenu.GetComponent<RadialMenuBuilder>();
                    if (builder != null)
                    {
                        // Reset state to default whenever Navigation is selected
                        builder.BuildMenu();
                        builder.OpenMenu();
                    }
                }
                break;
            case 2:
                Debug.Log("Opening Tasklist screen");
                if (tasklist == null)
                {
                    Debug.LogWarning("Tasklist is not assigned on ScreenManager.");
                    break;
                }
                tasklist.SetActive(true);
                TaskDetailScreen taskDetailScreen = tasklist.GetComponent<TaskDetailScreen>();
                if (taskDetailScreen != null)
                {
                    taskDetailScreen.ShowTaskMainMenu();
                }
                else
                {
                    Debug.LogWarning("TaskDetailScreen component is missing on Tasklist GameObject.");
                }
                break;
            case 4:
                Debug.Log("Opening Vitals screen");
                vitals.SetActive(true);
                VitalsController vitalsController = vitals.GetComponent<VitalsController>();
                if (vitalsController != null)
                {
                    vitalsController.openFeatureScreen();
                }
                else
                {
                    foreach (Transform child in vitals.transform)
                    {
                        child.gameObject.SetActive(true);
                    }
                }
                break;
             case 5:
                Debug.Log("Opening PR screen");
                PR.SetActive(true);
                PR.GetComponent<RoverSettings>().openFeatureScreen();
                break;
        }
    }


    public void DeactivateAllScreens()
    {
        screens.SetActive(true);
        Debug.Log("Deactivating all screens");
        ExitUia();
        navigation.SetActive(true);
        foreach (Transform child in navigation.transform)
        {
            child.gameObject.SetActive(false);
        }
        PR.SetActive(true);
        foreach (Transform child in PR.transform)
        {
            child.gameObject.SetActive(false);
        }
        messaging.SetActive(false);
        if (tasklist != null)
        {
            tasklist.SetActive(false);
        }
        vitals.SetActive(true);
        foreach (Transform child in vitals.transform)
        {
            child.gameObject.SetActive(false);
        }

        // Hide radial menu whenever switching away; its state will be reset next time Navigation is opened
        if (radialMenu != null)
        {
            radialMenu.SetActive(false);
        }
    }


    private void OnDestroy()
    {
        if (menuToggleCollection != null)
        {
            menuToggleCollection.OnToggleSelected.RemoveListener(OnToggleChanged);
        }
    }
}

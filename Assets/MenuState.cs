using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using MixedReality.Toolkit.UX;

public class MenuState : MonoBehaviour
{
    [SerializeField] private ToggleCollection toggleCollection;
    [SerializeField] private GameObject screenManager;
    [SerializeField] private GameObject vitals;
    [SerializeField] private GameObject tasklist;
    [SerializeField] private GameObject messages;
    [SerializeField] private GameObject navigation;
    [SerializeField] private GameObject uia;
    private const int UiaToggleIndex = 0;

    private void EnterUia()
    {
        if (uia == null) return;
        uia.SetActive(true);
        UIAController uiaController = uia.GetComponent<UIAController>();
        uiaController?.openFeatureScreen();
    }

    private void ExitUia()
    {
        if (uia == null) return;
        UIAController uiaController = uia.GetComponent<UIAController>();
        if (uiaController != null)
        {
            uiaController.closeFeatureScreen();
        }
        else
        {
            uia.SetActive(false);
        }
    }

    private void Start()
    {
        // Subscribe to the OnToggleSelected event
        toggleCollection.OnToggleSelected.AddListener(HandleToggleSelection);
    }

    private void OnDestroy()
    {
        if (toggleCollection != null)
        {
            toggleCollection.OnToggleSelected.RemoveListener(HandleToggleSelection);
        }
    }

    private void HandleToggleSelection(int selectedIndex)
    {
        Debug.Log("Toggle selected: " + selectedIndex);

        // Deactivate all screens
        screenManager.SetActive(true);
        vitals.SetActive(false);
        tasklist.SetActive(false);
        messages.SetActive(false);
        navigation.SetActive(false);
        ExitUia();

        // Activate the respective screen based on the selected index
        switch (selectedIndex)
        {
            case UiaToggleIndex:
                EnterUia();
                Debug.Log("UIA screen opened.");
                break;
            case 1:
                navigation.SetActive(true);
                Debug.Log("Navigation screen opened.");
                break;
            case 2:
                messages.SetActive(true);
                Debug.Log("Messages screen opened.");
                break;
            case 4:
                vitals.SetActive(true);
                //suit_helmet_pressure vitals
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
                Debug.Log("Vitals screen opened.");
                break;
            case 5:
                tasklist.SetActive(true);
                Debug.Log("Tasklist screen opened.");
                break;
            case 6:
                // case is for closing any menu
                screenManager.SetActive(false);
                break;
            default:
                Debug.LogWarning("Invalid toggle index selected: " + selectedIndex);
                break;
        }
    }
}

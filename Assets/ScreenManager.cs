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
    public ToggleCollection menuToggleCollection;
    [Header("Navigation Radial Menu")]
    [Tooltip("Radial navigation menu GameObject (e.g. 'RadialMenu' in the main scene).")]
    public GameObject radialMenu;



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
                UIA.SetActive(true);
                UIA.GetComponent<UIAController>().openFeatureScreen();
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
                Debug.Log("Opening Messaging screen");
                messaging.SetActive(true);
                messaging.GetComponent<FrontEndButton>().openFeatureScreen();
                break;
            case 4:
                Debug.Log("Opening Vitals screen");
                vitals.SetActive(true);
                vitals.GetComponent<VitalsController>().openFeatureScreen();
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
        UIA.SetActive(true);
        foreach (Transform child in UIA.transform)
        {
            child.gameObject.SetActive(false);
        }
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
        messaging.SetActive(true);
        foreach (Transform child in messaging.transform)
        {
            child.gameObject.SetActive(false);
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

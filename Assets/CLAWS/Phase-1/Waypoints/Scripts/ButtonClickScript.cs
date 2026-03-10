using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

public class ButtonClickScript : MonoBehaviour
{
    GameObject DangerButton;
    GameObject POIButton;
    GameObject HighlightedDangerButton;
    GameObject HighlightedPOIButton;
    string gameObjectName;

    public static GameObject FindGameObjectEvenIfInactive(string name)
    {
        GameObject[] allObjects = Resources.FindObjectsOfTypeAll<GameObject>();
        foreach (GameObject obj in allObjects)
        {
            if (obj.name == name && obj.scene.IsValid())
            {
                return obj;
            }
        }
        return null;
    }
    void Start()
    {
        DangerButton = FindGameObjectEvenIfInactive("DangerButton");
        POIButton = FindGameObjectEvenIfInactive("POIButton");
        HighlightedDangerButton = FindGameObjectEvenIfInactive("HighlightedDangerButton");
        HighlightedPOIButton = FindGameObjectEvenIfInactive("HighlightedPOIButton");

        gameObjectName = gameObject.name;

        Debug.Log(gameObjectName);
    }

    void Update()
    {
        
    }

    public void OnClick()
    {
        if(gameObjectName == "DangerButton")
        {
            gameObject.SetActive(false);
            POIButton.SetActive(true);
            HighlightedDangerButton.SetActive(true);
            HighlightedPOIButton.SetActive(false);
        }
        else if(gameObjectName == "POIButton")
        {
            gameObject.SetActive(false);
            DangerButton.SetActive(true);
            HighlightedDangerButton.SetActive(false);
            HighlightedPOIButton.SetActive(true);
        }
        else if(gameObjectName == "HighlightedDangerButton" || gameObjectName == "HighlightedPOIButton")
        {
            DangerButton.SetActive(true);
            POIButton.SetActive(true);  
            HighlightedDangerButton.SetActive(false);
            HighlightedPOIButton.SetActive(false);
        }
    }
}

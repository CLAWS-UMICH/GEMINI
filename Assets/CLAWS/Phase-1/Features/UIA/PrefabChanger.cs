using UnityEngine;

public class PrefabChanger : MonoBehaviour
{
    [Header("Prefab Settings")]
    [Tooltip("Drag and drop your prefabs here in the Inspector.")]
    public GameObject[] prefabs;
    
    [Tooltip("The transform where the prefabs will spawn. Can be an empty GameObject.")]
    public Transform overlayTarget; 

    private GameObject currentInstantiatedPrefab;
    private int currentIndex = 0;

    void Start()
    {
        // Spawn the first prefab when the scene starts, assuming the array isn't empty
        if (prefabs.Length > 0 && overlayTarget != null)
        {
            InstantiatePrefab(currentIndex);
        }
        else
        {
            Debug.LogWarning("Please assign prefabs and an overlay target in the Inspector!");
        }
    }

    void Update()
    {
        // Keyboard inputs for quick testing
        if (Input.GetKeyDown(KeyCode.RightArrow))
        {
            NextPrefab();
        }
        else if (Input.GetKeyDown(KeyCode.LeftArrow))
        {
            PreviousPrefab();
        }
    }

    // Call this method from a UI Button's OnClick event
    public void NextPrefab()
    {
        if (prefabs.Length == 0) return;

        currentIndex++;
        // Loop back to the first prefab if we go past the end of the array
        if (currentIndex >= prefabs.Length)
        {
            currentIndex = 0; 
        }
        InstantiatePrefab(currentIndex);
    }

    // Call this method from a UI Button's OnClick event
    public void PreviousPrefab()
    {
        if (prefabs.Length == 0) return;

        currentIndex--;
        // Loop to the last prefab if we go below zero
        if (currentIndex < 0)
        {
            currentIndex = prefabs.Length - 1; 
        }
        InstantiatePrefab(currentIndex);
    }

    private void InstantiatePrefab(int index)
    {
        // Destroy the currently displayed model to prevent overlap
        if (currentInstantiatedPrefab != null)
        {
            Destroy(currentInstantiatedPrefab);
        }

        // Spawn the new model at the target's position and rotation
        currentInstantiatedPrefab = Instantiate(prefabs[index], overlayTarget.position, overlayTarget.rotation);

        // Parent the new model to the target so it moves seamlessly with your overlay
        currentInstantiatedPrefab.transform.SetParent(overlayTarget);
    }
}
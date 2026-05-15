using UnityEngine;
using TMPro;

/// <summary>
/// Page-cycling controller for the radial vitals dashboard. Each entry in
/// <see cref="pages"/> is shown one at a time; the radial wedges call
/// <see cref="ButtonLeftClick"/> / <see cref="ButtonRightClick"/> to step
/// through them with wrap-around. The shared backplate and RadialButtons
/// GameObject must live OUTSIDE the page roots so they remain visible
/// regardless of which page is active.
/// </summary>
public class ButtonHandler : MonoBehaviour
{
    [Header("Pages")]
    [Tooltip("One GameObject per dashboard page. Only the active index is enabled at a time.")]
    [SerializeField] private GameObject[] pages;

    [Tooltip("Title shown in mainTitleText for each page (parallel to pages[]).")]
    [SerializeField] private string[] pageTitles;

    [Header("Shared UI")]
    [Tooltip("Persistent header text updated when the page changes.")]
    [SerializeField] private TextMeshPro mainTitleText;

    private int currentIndex = 0;

    private void OnEnable()
    {
        Apply();
    }

    private void Start()
    {
        Apply();
    }

    public void ButtonRightClick()
    {
        if (pages == null || pages.Length == 0) return;
        currentIndex = (currentIndex + 1) % pages.Length;
        Apply();
    }

    public void ButtonLeftClick()
    {
        if (pages == null || pages.Length == 0) return;
        currentIndex = (currentIndex - 1 + pages.Length) % pages.Length;
        Apply();
    }

    private void Apply()
    {
        if (pages == null || pages.Length == 0) return;

        if (currentIndex < 0 || currentIndex >= pages.Length)
            currentIndex = 0;

        for (int i = 0; i < pages.Length; i++)
        {
            if (pages[i] != null)
                pages[i].SetActive(i == currentIndex);
        }

        if (mainTitleText != null && pageTitles != null && currentIndex < pageTitles.Length)
            mainTitleText.text = pageTitles[currentIndex];
    }
}

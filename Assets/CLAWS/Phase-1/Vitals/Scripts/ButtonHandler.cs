using UnityEngine;
using TMPro;

public class ButtonHandler : MonoBehaviour
{
    [System.Serializable]
    public struct MetricData
    {
        [TextArea(1, 2)]
        public string label;    // e.g., "Suit Total Pressure"
        public string unit;     // e.g., "PSI"
        public string value;    // TODO: Pull live values here
    }

    [System.Serializable]
    public struct DashboardPage
    {
        public string pageTitle; // e.g., "Suit & Helmet Pressure"
        public MetricData[] metrics; // Array of metrics for this specific page
    }

    [Header("UI Display References")]
    [SerializeField] private TextMeshPro mainTitleText;
    [SerializeField] private TextMeshPro[] metricLabelTexts; 
    [SerializeField] private TextMeshPro[] metricValueTexts; 
    [SerializeField] private TextMeshPro[] metricUnitTexts;

    [Header("Dashboard Content")]
    [SerializeField] private DashboardPage[] allPages;

    private int currentIndex = 0;

    private void Start() 
    {
        UpdateDashboard();
    }

    public void ButtonRightClick()
    {
        if (allPages.Length == 0) return;
        currentIndex = (currentIndex + 1) % allPages.Length;
        UpdateDashboard();
    }

    public void ButtonLeftClick()
    {
        if (allPages.Length == 0) return;
        currentIndex = (currentIndex - 1 + allPages.Length) % allPages.Length;
        UpdateDashboard();
    }

    private void UpdateDashboard()
    {
        if (allPages.Length == 0) return;

        DashboardPage currentPage = allPages[currentIndex];

        if (mainTitleText != null) 
        {
            mainTitleText.text = currentPage.pageTitle;
        }

        // Loop through the UI slots and apply the data from the current page
        for (int i = 0; i < metricLabelTexts.Length; i++) // loops through 5 values
        {
            // Make sure we have data for this specific metric slot
            if (i < currentPage.metrics.Length)
            {
                // Update Label
                if (metricLabelTexts[i] != null) 
                {
                    metricLabelTexts[i].text = currentPage.metrics[i].label;
                }

                // Update Value
                if (metricValueTexts[i] != null) 
                {
                    metricValueTexts[i].text = currentPage.metrics[i].value;
                }

                // Update Unit 
                if (i < metricUnitTexts.Length && metricUnitTexts[i] != null) 
                {
                    metricUnitTexts[i].text = currentPage.metrics[i].unit;
                }
            }
        }
    }
}
#if UNITY_EDITOR
using System.Collections.Generic;
using TMPro;
using UnityEditor;
using UnityEngine;

/// <summary>
/// One-shot tooling to convert <c>Suit_Helmet_Pressure.prefab</c> from a single
/// suit-pressure panel into a 5-page paged vitals dashboard.
///
/// Run via menu: <c>Tools/Vitals/Build Paged Vitals Pages</c>.
///
/// Idempotent: re-running will detect existing page roots and skip recreating
/// them, so it is safe to re-invoke after manual tweaks.
/// </summary>
public static class VitalsPageBuilder
{
    private const string PrefabPath = "Assets/CLAWS/Phase-1/Vitals/Suit_Helmet_Pressure.prefab";

    private static readonly string[] ExistingRingNames =
    {
        "STP", "O2_suitP", "CO2_suitP", "CO2_P", "Other"
    };

    private struct RingSpec
    {
        public string objectName;
        public string titleLabel;
        public string unitLabel;
        public VitalsRingPage.VitalsRingMetric metric;
        public string valueFormat;
    }

    private struct PageSpec
    {
        public string pageRootName;
        public string pageTitle;
        public RingSpec[] rings;
    }

    [MenuItem("Tools/Vitals/Build Paged Vitals Pages")]
    public static void Build()
    {
        GameObject root = PrefabUtility.LoadPrefabContents(PrefabPath);
        if (root == null)
        {
            Debug.LogError($"VitalsPageBuilder: could not load prefab at {PrefabPath}");
            return;
        }

        try
        {
            BuildInto(root);
            PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            Debug.Log("VitalsPageBuilder: rebuilt Suit_Helmet_Pressure.prefab with 5 paged screens.");
        }
        finally
        {
            PrefabUtility.UnloadPrefabContents(root);
        }
    }

    private static void BuildInto(GameObject root)
    {
        Transform rootT = root.transform;

        Transform pageAtmosphere = rootT.Find("Page_Atmosphere");
        if (pageAtmosphere == null)
        {
            pageAtmosphere = new GameObject("Page_Atmosphere").transform;
            pageAtmosphere.SetParent(rootT, worldPositionStays: false);
            pageAtmosphere.SetAsFirstSibling();

            foreach (string ringName in ExistingRingNames)
            {
                Transform ring = rootT.Find(ringName);
                if (ring != null)
                    ring.SetParent(pageAtmosphere, worldPositionStays: false);
            }
        }

        PageSpec[] specs = GetPageSpecs();
        RenameAndTrimRings(pageAtmosphere, specs[0]);
        ConfigureRingPage(pageAtmosphere.gameObject, specs[0]);

        Transform template = pageAtmosphere;

        for (int i = 1; i < specs.Length; i++)
        {
            PageSpec spec = specs[i];
            Transform existing = rootT.Find(spec.pageRootName);
            if (existing != null && PageNeedsRebuild(existing, spec))
            {
                Object.DestroyImmediate(existing.gameObject);
                existing = null;
            }

            if (existing != null)
            {
                RenameAndTrimRings(existing, spec);
                ConfigureRingPage(existing.gameObject, spec);
                continue;
            }

            GameObject duplicate = Object.Instantiate(template.gameObject, rootT, worldPositionStays: false);
            duplicate.name = spec.pageRootName;
            duplicate.SetActive(false);

            RenameAndTrimRings(duplicate.transform, spec);
            ConfigureRingPage(duplicate, spec);
        }

        StripOldHelmetColorScript(root);
    }

    private static bool PageNeedsRebuild(Transform pageRoot, PageSpec spec)
    {
        int ringCount = 0;
        foreach (Transform c in pageRoot)
            ringCount++;

        if (ringCount != spec.rings.Length)
            return true;

        for (int i = 0; i < spec.rings.Length; i++)
        {
            Transform ring = pageRoot.Find(spec.rings[i].objectName);
            if (ring == null)
                return true;
        }

        return pageRoot.Find("O2_Time") != null || pageRoot.Find("Batt_Time") != null;
    }

    private static void RenameAndTrimRings(Transform pageRoot, PageSpec spec)
    {
        List<Transform> ringChildren = new List<Transform>();
        foreach (Transform c in pageRoot)
            ringChildren.Add(c);

        for (int i = 0; i < ringChildren.Count; i++)
        {
            if (i < spec.rings.Length)
            {
                RingSpec ringSpec = spec.rings[i];
                ringChildren[i].name = ringSpec.objectName;
                SetChildText(ringChildren[i], "Title", ringSpec.titleLabel);
                SetChildText(ringChildren[i], "Unit", ringSpec.unitLabel);
                SetChildText(ringChildren[i], "Value", "--");
            }
            else
            {
                Object.DestroyImmediate(ringChildren[i].gameObject);
            }
        }
    }

    private static void SetChildText(Transform ring, string childName, string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        Transform child = ring.Find(childName);
        if (child == null) return;
        TextMeshPro tmp = child.GetComponent<TextMeshPro>();
        if (tmp != null)
            tmp.text = text;
    }

    private static void ConfigureRingPage(GameObject pageRoot, PageSpec spec)
    {
        VitalsRingPage page = pageRoot.GetComponent<VitalsRingPage>();
        if (page == null)
            page = pageRoot.AddComponent<VitalsRingPage>();

        SerializedObject so = new SerializedObject(page);
        SerializedProperty bindings = so.FindProperty("bindings");
        bindings.arraySize = spec.rings.Length;

        for (int i = 0; i < spec.rings.Length; i++)
        {
            RingSpec ringSpec = spec.rings[i];
            Transform ring = pageRoot.transform.Find(ringSpec.objectName);
            TextMeshPro valueText = null;
            TextMeshPro unitText = null;
            SpriteRenderer ringFull = null;
            if (ring != null)
            {
                Transform v = ring.Find("Value");
                if (v != null) valueText = v.GetComponent<TextMeshPro>();
                Transform u = ring.Find("Unit");
                if (u != null) unitText = u.GetComponent<TextMeshPro>();
                Transform rf = ring.Find("RingFull");
                if (rf != null) ringFull = rf.GetComponent<SpriteRenderer>();
            }

            SerializedProperty element = bindings.GetArrayElementAtIndex(i);
            element.FindPropertyRelative("metric").enumValueIndex = (int)ringSpec.metric;
            element.FindPropertyRelative("valueText").objectReferenceValue = valueText;
            element.FindPropertyRelative("unitText").objectReferenceValue = unitText;
            element.FindPropertyRelative("ringFull").objectReferenceValue = ringFull;
            element.FindPropertyRelative("arcMax").floatValue = 0f;
            element.FindPropertyRelative("valueFormat").stringValue = ringSpec.valueFormat;
        }

        so.ApplyModifiedPropertiesWithoutUndo();
    }

    private static void StripOldHelmetColorScript(GameObject root)
    {
        SuitHelmetRingHealthColors old = root.GetComponent<SuitHelmetRingHealthColors>();
        if (old != null)
            Object.DestroyImmediate(old, allowDestroyingAssets: true);
    }

    private static PageSpec[] GetPageSpecs()
    {
        return new[]
        {
            new PageSpec
            {
                pageRootName = "Page_Atmosphere",
                pageTitle = "Suit Atmosphere",
                rings = new[]
                {
                    new RingSpec { objectName = "STP",       titleLabel = "SUIT TOT", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.SuitPressureTotal,     valueFormat = "F1" },
                    new RingSpec { objectName = "O2_suitP",  titleLabel = "SUIT O2",  unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.SuitPressureOxy,       valueFormat = "F1" },
                    new RingSpec { objectName = "CO2_suitP", titleLabel = "SUIT CO2", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.SuitPressureCo2,       valueFormat = "F2" },
                    new RingSpec { objectName = "CO2_P",     titleLabel = "HELM CO2", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.HelmetPressureCo2,     valueFormat = "F2" },
                    new RingSpec { objectName = "Other",     titleLabel = "OTHER",    unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.SuitPressureOther,     valueFormat = "F1" }
                }
            },
            new PageSpec
            {
                pageRootName = "Page_OxygenSupply",
                pageTitle = "Oxygen Supply",
                rings = new[]
                {
                    new RingSpec { objectName = "O2_PriStor", titleLabel = "PRI STOR", unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.OxyPriStorage,  valueFormat = "F0" },
                    new RingSpec { objectName = "O2_SecStor", titleLabel = "SEC STOR", unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.OxySecStorage,  valueFormat = "F0" },
                    new RingSpec { objectName = "O2_PriPres", titleLabel = "PRI PRES", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.OxyPriPressure, valueFormat = "F0" },
                    new RingSpec { objectName = "O2_SecPres", titleLabel = "SEC PRES", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.OxySecPressure, valueFormat = "F0" }
                }
            },
            new PageSpec
            {
                pageRootName = "Page_PowerThermal",
                pageTitle = "Power & Coolant",
                rings = new[]
                {
                    new RingSpec { objectName = "Batt_Pri",  titleLabel = "PRI BATT", unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.PrimaryBatteryLevel,   valueFormat = "F0" },
                    new RingSpec { objectName = "Batt_Sec",  titleLabel = "SEC BATT", unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.SecondaryBatteryLevel, valueFormat = "F0" },
                    new RingSpec { objectName = "Coolant",   titleLabel = "COOLANT",  unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.CoolantStorage,        valueFormat = "F0" },
                    new RingSpec { objectName = "Cool_Liq",  titleLabel = "COOL LIQ", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.CoolantLiquidPressure, valueFormat = "F0" },
                    new RingSpec { objectName = "Cool_Gas",  titleLabel = "COOL GAS", unitLabel = "psi", metric = VitalsRingPage.VitalsRingMetric.CoolantGasPressure,    valueFormat = "F0" }
                }
            },
            new PageSpec
            {
                pageRootName = "Page_LifeSupport",
                pageTitle = "Life Support",
                rings = new[]
                {
                    new RingSpec { objectName = "Fan_Pri",    titleLabel = "PRI FAN",  unitLabel = "rpm", metric = VitalsRingPage.VitalsRingMetric.FanPriRpm,    valueFormat = "N0" },
                    new RingSpec { objectName = "Fan_Sec",    titleLabel = "SEC FAN",  unitLabel = "rpm", metric = VitalsRingPage.VitalsRingMetric.FanSecRpm,    valueFormat = "N0" },
                    new RingSpec { objectName = "Scrubber_A", titleLabel = "SCRUB A",  unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.ScrubberACo2, valueFormat = "F0" },
                    new RingSpec { objectName = "Scrubber_B", titleLabel = "SCRUB B",  unitLabel = "%",   metric = VitalsRingPage.VitalsRingMetric.ScrubberBCo2, valueFormat = "F0" }
                }
            },
            new PageSpec
            {
                pageRootName = "Page_Biomedical",
                pageTitle = "Crew Biomedical",
                rings = new[]
                {
                    new RingSpec { objectName = "HR",       titleLabel = "HEART",    unitLabel = "bpm",     metric = VitalsRingPage.VitalsRingMetric.HeartRate,      valueFormat = "F0" },
                    new RingSpec { objectName = "Temp",     titleLabel = "TEMP",     unitLabel = "°C",      metric = VitalsRingPage.VitalsRingMetric.Temperature,    valueFormat = "F0" },
                    new RingSpec { objectName = "O2_Cons",  titleLabel = "O2 CONS",  unitLabel = "psi/min", metric = VitalsRingPage.VitalsRingMetric.OxyConsumption, valueFormat = "F2" },
                    new RingSpec { objectName = "CO2_Prod", titleLabel = "CO2 PROD", unitLabel = "psi/min", metric = VitalsRingPage.VitalsRingMetric.Co2Production,  valueFormat = "F2" }
                }
            }
        };
    }

    /// <summary>Returns the page titles in the same order as the page roots; used to seed ButtonHandler.pageTitles.</summary>
    public static string[] GetPageTitles()
    {
        PageSpec[] specs = GetPageSpecs();
        string[] titles = new string[specs.Length];
        for (int i = 0; i < specs.Length; i++)
            titles[i] = specs[i].pageTitle;
        return titles;
    }

    /// <summary>
    /// In the active scene, finds the selected Suit_Helmet_Pressure GameObject
    /// (or the only one in the scene) and its sibling/child RadialButtons,
    /// then wires the ButtonHandler with pages, pageTitles, and the top Title TMP.
    /// Run with the Suit_Helmet_Pressure GameObject selected for unambiguous results.
    /// </summary>
    [MenuItem("Tools/Vitals/Wire Vitals ButtonHandler (selected Suit_Helmet_Pressure)")]
    public static void WireButtonHandler()
    {
        GameObject selected = Selection.activeGameObject;
        if (selected == null)
        {
            Debug.LogError("VitalsPageBuilder: select the Suit_Helmet_Pressure GameObject in the scene first.");
            return;
        }

        Transform shp = selected.transform;
        if (shp.name != "Suit_Helmet_Pressure")
        {
            Transform parent = shp;
            while (parent != null && parent.name != "Suit_Helmet_Pressure")
                parent = parent.parent;
            if (parent == null)
            {
                Debug.LogError("VitalsPageBuilder: selection is not under a Suit_Helmet_Pressure GameObject.");
                return;
            }
            shp = parent;
        }

        ButtonHandler handler = shp.GetComponentInChildren<ButtonHandler>(includeInactive: true);
        if (handler == null)
        {
            Debug.LogError("VitalsPageBuilder: no ButtonHandler found in Suit_Helmet_Pressure (expected on RadialButtons).");
            return;
        }

        PageSpec[] specs = GetPageSpecs();
        GameObject[] pages = new GameObject[specs.Length];
        for (int i = 0; i < specs.Length; i++)
        {
            Transform page = shp.Find(specs[i].pageRootName);
            if (page == null)
            {
                Debug.LogError($"VitalsPageBuilder: missing page '{specs[i].pageRootName}' under Suit_Helmet_Pressure. Run 'Build Paged Vitals Pages' first.");
                return;
            }
            pages[i] = page.gameObject;
        }

        TextMeshPro topTitle = null;
        Transform titleT = shp.Find("Title");
        if (titleT != null)
            topTitle = titleT.GetComponent<TextMeshPro>();

        SerializedObject so = new SerializedObject(handler);
        SerializedProperty pagesProp = so.FindProperty("pages");
        pagesProp.arraySize = pages.Length;
        for (int i = 0; i < pages.Length; i++)
            pagesProp.GetArrayElementAtIndex(i).objectReferenceValue = pages[i];

        SerializedProperty titlesProp = so.FindProperty("pageTitles");
        string[] titleStrings = GetPageTitles();
        titlesProp.arraySize = titleStrings.Length;
        for (int i = 0; i < titleStrings.Length; i++)
            titlesProp.GetArrayElementAtIndex(i).stringValue = titleStrings[i];

        SerializedProperty titleProp = so.FindProperty("mainTitleText");
        titleProp.objectReferenceValue = topTitle;

        so.ApplyModifiedProperties();

        SuitHelmetRingHealthColors stale = shp.GetComponent<SuitHelmetRingHealthColors>();
        if (stale != null)
        {
            Object.DestroyImmediate(stale);
            Debug.Log("VitalsPageBuilder: removed leftover SuitHelmetRingHealthColors from scene Suit_Helmet_Pressure.");
        }

        Debug.Log("VitalsPageBuilder: wired ButtonHandler with 5 pages, titles, and Title TMP.");
    }
}
#endif

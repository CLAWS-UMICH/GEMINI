using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

[RequireComponent(typeof(ARTrackedImageManager))]
public class PlaceTrackedImages : MonoBehaviour
{
    private ARTrackedImageManager _trackedImagesManager;

    public GameObject[] ArPrefabs;

    private readonly Dictionary<string, GameObject> _instantiatedPrefabs = new Dictionary<string, GameObject>();

    private void Awake()
    {
        _trackedImagesManager = GetComponent<ARTrackedImageManager>();
    }

    private void OnEnable()
    {
        _trackedImagesManager.trackedImagesChanged += OnTrackedImagesChanged;
    }

    private void OnDisable()
    {
        _trackedImagesManager.trackedImagesChanged -= OnTrackedImagesChanged;
    }

    /// <summary>
    /// Destroys all spawned overlay instances (e.g. when leaving UIA mode).
    /// </summary>
    public void ClearInstantiatedPrefabs()
    {
        foreach (var kv in _instantiatedPrefabs)
        {
            if (kv.Value != null)
            {
                Destroy(kv.Value);
            }
        }

        _instantiatedPrefabs.Clear();
    }

    private void OnTrackedImagesChanged(ARTrackedImagesChangedEventArgs eventArgs)
    {
        TryInstantiateForImages(eventArgs.added);
        TryInstantiateForImages(eventArgs.updated);

        UpdateVisibility(eventArgs.updated);
        UpdateVisibility(eventArgs.added);

        foreach (var trackedImage in eventArgs.removed)
        {
            var imageName = trackedImage.referenceImage.name;
            if (!_instantiatedPrefabs.TryGetValue(imageName, out var instance))
            {
                continue;
            }

            Destroy(instance);
            _instantiatedPrefabs.Remove(imageName);
        }
    }

    private void TryInstantiateForImages(IEnumerable<ARTrackedImage> images)
    {
        if (images == null)
        {
            return;
        }

        foreach (var trackedImage in images)
        {
            var imageName = trackedImage.referenceImage.name;

            foreach (var curPrefab in ArPrefabs)
            {
                if (curPrefab == null)
                {
                    continue;
                }

                if (string.Compare(curPrefab.name, imageName, StringComparison.OrdinalIgnoreCase) != 0)
                {
                    continue;
                }

                if (_instantiatedPrefabs.ContainsKey(imageName))
                {
                    break;
                }

                var newPrefab = Instantiate(curPrefab, trackedImage.transform);
                _instantiatedPrefabs[imageName] = newPrefab;
                break;
            }
        }
    }

    private void UpdateVisibility(IEnumerable<ARTrackedImage> images)
    {
        if (images == null)
        {
            return;
        }

        foreach (var trackedImage in images)
        {
            var imageName = trackedImage.referenceImage.name;
            if (!_instantiatedPrefabs.TryGetValue(imageName, out var instance) || instance == null)
            {
                continue;
            }

            instance.SetActive(trackedImage.trackingState == TrackingState.Tracking);
        }
    }
}

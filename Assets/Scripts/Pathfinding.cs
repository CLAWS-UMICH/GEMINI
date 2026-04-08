using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class Pathfinding : MonoBehaviour
{
    public Astronaut astronaut; 
    // Existing path renderer is the world path.
    public LineRenderer pathRenderer;
    [Tooltip("Dedicated minimap path renderer. Assign a separate LineRenderer GameObject on the Minimap Only layer.")]
    [SerializeField] private LineRenderer minimapPathRenderer;

    [Header("Path line")]
    [Tooltip("Width of the world path line (meters).")]
    [SerializeField] private float worldPathLineWidth = 0.5f;
    [Tooltip("Width of the minimap path line (meters). Can be wider than world path.")]
    [SerializeField] private float minimapPathLineWidth = 1.2f;

    [Header("Ground snapping")]
    [Tooltip("Raycast downward from each path point to stick the line to the ground. Leave as Nothing to keep the path at fixed height.")]
    public LayerMask groundMask = -1;
    [Tooltip("Max distance to raycast down when snapping to ground.")]
    public float groundRaycastDistance = 20f;
    [Tooltip("Small height offset above ground to avoid z-fighting (meters).")]
    public float groundOffset = 0.02f;

    [Header("Destination waypoint")]
    [Tooltip("Optional world-space indicator shown only while active world navigation is displayed.")]
    [SerializeField] private Transform destinationWaypointIndicator;
    [Tooltip("Optional minimap destination indicator. Leave empty if minimap path does not need a floating endpoint marker.")]
    [SerializeField] private Transform minimapDestinationWaypointIndicator;
    [Tooltip("Height in meters above the destination point for the waypoint indicator.")]
    [SerializeField] private float waypointHeightAboveGround = 2.5f;

    private Grid grid;
    private List<Node> currentPath;
    private Vector3 currentTargetPosition;
    private Vector3[] cachedPathPositions;

    void Awake()
    {
        grid = GetComponent<Grid>();
        if (pathRenderer != null)
        {
            ConfigureRenderer(pathRenderer, worldPathLineWidth);
        }
        if (minimapPathRenderer != null)
        {
            ConfigureRenderer(minimapPathRenderer, minimapPathLineWidth);
        }

        HideWorldDestinationWaypoint();
        HideMinimapDestinationWaypoint();
    }

    public void SetTarget(Vector3 targetPosition)
    {
        currentTargetPosition = targetPosition;
        CalculatePath(currentTargetPosition);
    }

    /// <summary>Clears all navigation paths and destination indicators.</summary>
    public void ClearTarget()
    {
        currentPath = null;
        currentTargetPosition = default;
        cachedPathPositions = null;
        if (pathRenderer != null)
            pathRenderer.positionCount = 0;
        if (minimapPathRenderer != null)
            minimapPathRenderer.positionCount = 0;
        if (pathRenderer != null) pathRenderer.enabled = false;
        if (minimapPathRenderer != null) minimapPathRenderer.enabled = false;
        HideWorldDestinationWaypoint();
        HideMinimapDestinationWaypoint();
    }

    /// <summary>Current world position of the navigation target (valid after SetTarget and when a path exists).</summary>
    public Vector3 GetCurrentTargetPosition() => currentTargetPosition;

    /// <summary>True when a path to the target has been found and the destination waypoint can be shown.</summary>
    public bool HasActivePath() => currentPath != null && currentPath.Count > 0;

    private void ConfigureRenderer(LineRenderer renderer, float width)
    {
        if (renderer == null) return;
        renderer.useWorldSpace = true;
        renderer.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
        renderer.startWidth = width;
        renderer.endWidth = width;
        renderer.positionCount = 0;
        renderer.enabled = false;
    }

    void HideWorldDestinationWaypoint()
    {
        if (destinationWaypointIndicator != null)
            destinationWaypointIndicator.gameObject.SetActive(false);
    }

    void HideMinimapDestinationWaypoint()
    {
        if (minimapDestinationWaypointIndicator != null)
            minimapDestinationWaypointIndicator.gameObject.SetActive(false);
    }

    private void UpdateDestinationWaypointPositions()
    {
        Vector3 indicatorPosition = currentTargetPosition + Vector3.up * waypointHeightAboveGround;
        if (destinationWaypointIndicator != null)
        {
            destinationWaypointIndicator.position = indicatorPosition;
        }
        if (minimapDestinationWaypointIndicator != null)
        {
            minimapDestinationWaypointIndicator.position = indicatorPosition;
        }
    }

    /// <summary>Show only minimap navigation visuals after selecting a waypoint.</summary>
    public void ShowMinimapOnly()
    {
        if (minimapPathRenderer != null && minimapPathRenderer.positionCount > 0)
            minimapPathRenderer.enabled = true;
        if (pathRenderer != null)
            pathRenderer.enabled = false;

        HideWorldDestinationWaypoint();
        if (minimapDestinationWaypointIndicator != null && minimapPathRenderer != null && minimapPathRenderer.positionCount > 0)
            minimapDestinationWaypointIndicator.gameObject.SetActive(true);
        else
            HideMinimapDestinationWaypoint();
    }

    /// <summary>Show world navigation visuals while keeping minimap path visible.</summary>
    public void ShowWorldAndMinimap()
    {
        if (pathRenderer != null && pathRenderer.positionCount > 0)
            pathRenderer.enabled = true;
        if (minimapPathRenderer != null && minimapPathRenderer.positionCount > 0)
            minimapPathRenderer.enabled = true;

        if (destinationWaypointIndicator != null && pathRenderer != null && pathRenderer.positionCount > 0)
            destinationWaypointIndicator.gameObject.SetActive(true);
        else
            HideWorldDestinationWaypoint();

        if (minimapDestinationWaypointIndicator != null && minimapPathRenderer != null && minimapPathRenderer.positionCount > 0)
            minimapDestinationWaypointIndicator.gameObject.SetActive(true);
    }

    public void CalculatePath(Vector3 targetWorldPosition)
    {
        Vector3 startPos = GetAstronautWorldPosition();
        Debug.Log($"Start position: {startPos}");
        FindPath(startPos, targetWorldPosition);
    }

    Vector3 GetAstronautWorldPosition()
    {
        return new Vector3(
            (float)astronaut.current.posX,
            0,
            (float)astronaut.current.posZ // Ensure Z uses posZ
        );
    }

    void InitializeLineRenderer()
    {
        pathRenderer.startWidth = 0.3f;
        pathRenderer.endWidth = 0.3f;
        pathRenderer.material = new Material(Shader.Find("Sprites/Default")) { 
            color = Color.cyan 
        };
        pathRenderer.positionCount = 0;
    }

    // void Update()
    // {
    //     Vector3 startPos = new Vector3(
    //         (float)astronaut.current.posX,
    //         (float)astronaut.current.posY,
    //         (float)astronaut.current.posZ
    //     );
        
    //     FindPath(startPos, target.position);
    // }

    public void FindPath(Vector3 startPos, Vector3 targetPos)
    {
        Node startNode = grid.NodeFromWorldPoint(startPos);
        Node targetNode = grid.NodeFromWorldPoint(targetPos);
        
        if (startNode == null) Debug.LogError($"Start node is null at position {startPos}");
        if (targetNode == null) Debug.LogError($"Target node is null at position {targetPos}");

        if (!ValidateNodes(startNode, targetNode))
        {
            Debug.LogError("Node validation failed");
            if (pathRenderer != null) pathRenderer.positionCount = 0;
            if (minimapPathRenderer != null) minimapPathRenderer.positionCount = 0;
            if (pathRenderer != null) pathRenderer.enabled = false;
            if (minimapPathRenderer != null) minimapPathRenderer.enabled = false;
            HideWorldDestinationWaypoint();
            HideMinimapDestinationWaypoint();
            return;
        }

        Debug.Log("Starting A* search...");
        ResetNodeCosts();
        AStarSearch(startNode, targetNode);
    }

    bool ValidateNodes(Node start, Node target)
    {
        if (start == null)
        {
            Debug.LogError($"Invalid start position (outside grid bounds?)");
            return false;
        }
        
        if (target == null)
        {
            Debug.LogError($"Invalid target position (outside grid bounds?)");
            return false;
        }

        if (target.bIsWall)
        {
            Debug.LogError("Target node is blocked by wall");
            return false;
        }

        return true;
    }

    void ResetNodeCosts()
    {
        foreach (Node node in grid.NodeArray)
        {
            node.gCost = int.MaxValue;
            node.hCost = 0;
            node.parent = null;
        }
    }

    void AStarSearch(Node startNode, Node targetNode)
    {
        Heap<Node> openSet = new Heap<Node>(grid.MaxSize);
        HashSet<Node> closedSet = new HashSet<Node>();
        
        startNode.gCost = 0;
        startNode.hCost = GetDistance(startNode, targetNode);
        openSet.Add(startNode);

        while (openSet.Count > 0)
        {
            Node currentNode = openSet.RemoveFirst();
            closedSet.Add(currentNode);

            if (currentNode == targetNode)
            {
                currentPath = RetracePath(startNode, targetNode);
                UpdatePathVisualization();
                UpdateDestinationWaypointPositions();
                return;
            }

            ProcessNeighbors(currentNode, targetNode, openSet, closedSet);
        }
        
        Debug.LogWarning("No path exists between points");
        if (pathRenderer != null) pathRenderer.positionCount = 0;
        if (minimapPathRenderer != null) minimapPathRenderer.positionCount = 0;
        if (pathRenderer != null) pathRenderer.enabled = false;
        if (minimapPathRenderer != null) minimapPathRenderer.enabled = false;
        HideWorldDestinationWaypoint();
        HideMinimapDestinationWaypoint();
    }

    void ProcessNeighbors(Node current, Node target, Heap<Node> openSet, HashSet<Node> closedSet)
    {
        foreach (Node neighbor in grid.GetNeighboringNodes(current))
        {
            if (neighbor.bIsWall || closedSet.Contains(neighbor)) 
                continue;

            int newCost = current.gCost + GetDistance(current, neighbor) + neighbor.movementPenalty;
            
            if (newCost < neighbor.gCost || !openSet.Contains(neighbor))
            {
                neighbor.gCost = newCost;
                neighbor.hCost = GetDistance(neighbor, target);
                neighbor.parent = current;

                if (!openSet.Contains(neighbor))
                    openSet.Add(neighbor);
                else 
                    openSet.UpdateItem(neighbor);
            }
        }
    }

    List<Node> RetracePath(Node start, Node end)
    {
        List<Node> path = new List<Node>();
        Node current = end;

        while (current != start && current != null)
        {
            path.Add(current);
            current = current.parent;
        }
        
        if (current == null)
        {
            Debug.LogError("Path broken - null parent detected");
            return new List<Node>();
        }

        path.Reverse();
        return path;
    }

    void UpdatePathVisualization()
    {
        if (currentPath == null || currentPath.Count == 0) return;

        cachedPathPositions = new Vector3[currentPath.Count];
        for (int i = 0; i < currentPath.Count; i++)
        {
            cachedPathPositions[i] = currentPath[i].worldPosition + Vector3.up * 0.5f;
        }

        if (pathRenderer != null)
        {
            pathRenderer.positionCount = cachedPathPositions.Length;
            pathRenderer.SetPositions(cachedPathPositions);
        }
        if (minimapPathRenderer != null)
        {
            minimapPathRenderer.positionCount = cachedPathPositions.Length;
            minimapPathRenderer.SetPositions(cachedPathPositions);
        }
    }

    int GetDistance(Node a, Node b)
    {
        int dx = Mathf.Abs(a.iGridX - b.iGridX);
        int dy = Mathf.Abs(a.iGridY - b.iGridY);
        
        return dx > dy ? 
            14 * dy + 10 * (dx - dy) : 
            14 * dx + 10 * (dy - dx);
    }

    public List<Node> GetCurrentPath()
    {
        return currentPath;
    }
}

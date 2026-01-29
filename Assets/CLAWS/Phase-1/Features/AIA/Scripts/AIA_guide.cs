using UnityEngine;

public class AIA_guide : MonoBehaviour
{

    [SerializeField] private Animator AIA_Animator;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.P))
        {
            // This line communicates with the Animator's parameter
            AIA_Animator.SetBool("isAwake", true);
        }
        if (Input.GetKeyDown(KeyCode.P))
        {
            // This line communicates with the Animator's parameter
            AIA_Animator.SetBool("isAwake", false);
        }
    }
}

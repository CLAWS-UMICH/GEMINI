using UnityEngine;

public class AIA_guide : MonoBehaviour
{

    public Animator myAnimator;
    public transform myAnimator;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space))
        {
            // This line communicates with the Animator's parameter
            myAnimator.on(true);
        }
        if (Input.GetKeyUp(KeyCode.Space))
        {
            // This line communicates with the Animator's parameter
            myAnimator.on(true);
        }
    }
}

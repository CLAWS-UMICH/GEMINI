using UnityEngine;
using System.Collections;
using System.Collections.Generic;

public class DialogueTrigger : MonoBehaviour
{
    public Dialogue dialogue;
    public DialogueManager manager; 

    public void TriggerDialogue()
    {
       // Call the function ON the manager
       manager.StartDialogue(dialogue);
    }
}

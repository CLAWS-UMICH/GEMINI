using UnityEngine;
using System.Collections;
using System.Collections.Generic;

public class DialogueManager : MonoBehaviour
{
   
   private Queue<string> sentences;
   
   // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        sentences = new Queue<string>();
    }
}

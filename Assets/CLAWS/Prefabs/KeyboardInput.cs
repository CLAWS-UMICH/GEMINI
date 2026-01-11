using TMPro;
using UnityEngine;

// Last Updated:
//     Molly M. -- 10/1/2025

public class KeyboardInput : MonoBehaviour
{
    private TouchScreenKeyboard keyboard;
    [SerializeField] private TMP_Text keyboardText;
    private bool isKeyboardActive = false;

    public void OpenSystemKeyboard()
    {
        keyboard = TouchScreenKeyboard.Open("", TouchScreenKeyboardType.Default, false, false, false, false);
        isKeyboardActive = true;
    }

    private void Update()
    {
        if (!isKeyboardActive || keyboard == null || keyboardText == null)
            return;

        // Check if keyboard still exists before accessing properties
        if (TouchScreenKeyboard.visible)
        {
            // Update text in real-time
            keyboardText.text = keyboard.text;
        }
        else
        {
            // Keyboard was closed - get final text
            keyboardText.text = keyboard.text;
            keyboard = null;
            isKeyboardActive = false;
        }
    }

    // private void Update()
    // {
    //     if (keyboard != null)
    //     {
    //         // Check if enter key is pressed or the keyboard is closed
    //         if (keyboard.status == TouchScreenKeyboard.Status.Done || keyboard.status == TouchScreenKeyboard.Status.Canceled)
    //         {
    //             // Update the TextMeshPro text with the final input
    //             keyboardText.text = keyboard.text;
    //             keyboard = null;
    //         }
    //         else
    //         {
    //             // Update the TextMeshPro text in real-time as the user types
    //             keyboardText.text = keyboard.text;
    //         }
    //     }
    // }
}

using TMPro;
using CLAWS.Networking;
using UnityEngine;

// Last Updated:
//     Molly M. -- 10/1/2025

public class KeyboardInput : MonoBehaviour
{
    private TouchScreenKeyboard keyboard;
    [SerializeField] private GameObject keyboardObject;
    [SerializeField] private CorvusController _corvusController;

    public void OpenSystemKeyboard()
    {
        keyboard = TouchScreenKeyboard.Open("", TouchScreenKeyboardType.Default, false, false, false, false);
    }

    private void Update()
    {
        if (keyboard != null)
        {
            // Check if enter key is pressed or the keyboard is closed
            if (keyboard.status == TouchScreenKeyboard.Status.Done || keyboard.status == TouchScreenKeyboard.Status.Canceled)
            {
                string input = keyboard.text;
                // Update the TextMeshPro text with the final input
                keyboardObject.GetComponent<TextMeshPro>().text = input;
                if(_corvusController != null && !string.IsNullOrEmpty(input)) {
                    _ = _corvusController.SendCommandAsync(input);
                }
                keyboard = null;
            }
            else
            {
                // Update the TextMeshPro text in real-time as the user types
                keyboardObject.GetComponent<TextMeshPro>().text = keyboard.text;
            }
        }
    }
}

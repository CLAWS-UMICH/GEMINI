using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using SocketIOClient;
using System;
using System.Threading.Tasks;
using PimDeWitte.UnityMainThreadDispatcher;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json;

// [ NASA TSS ]  --->  [ LMCC (Ingest + DB + LLM + WebSocket Relay) ]
//           \          /                /      |     
//             \     /                 /       |       
//              [PR]                [EV1]    [EV2]    

public class LMCC : MonoBehaviour
{
    private SocketIOClient.SocketIO client;
    private string serverUrl;
    private string assignedId; // Store the unique ID assigned by the server as a string

    public async Task<bool> ReConnect(string connectionString)
    {
        try
        {
            serverUrl = connectionString;
            await InitializeSocket();
            return true;
        }
        catch (Exception ex)
        {
            Debug.LogError("Error occurred in ReConnect: " + ex.Message);
            return false;
        }
    }

    private async Task InitializeSocket()
    {
        if (client != null)
        {
            await client.DisconnectAsync();
        }

        client = new SocketIOClient.SocketIO(serverUrl);

        // Emit "connect_hololens" after connecting
        client.OnConnected += async (server, e) =>
        {
            Debug.Log("Connected to server, emitting 'connect_hololens'");
            await client.EmitAsync("connect_hololens");
        };

        // Listen for 'assign_id' event to receive the unique ID
        client.On("assign_id", response =>
        {

            // Parse the response (which is an array in this case)
            JArray jsonResponseArray = JArray.Parse(response.ToString());

            // Extract the 'id' value from the first item in the array
            if (jsonResponseArray.Count > 0)
            {
                JObject jsonResponse = (JObject)jsonResponseArray[0];
                assignedId = jsonResponse["id"]?.ToString();  // Get the "id" value
                Debug.Log($"Received ID from server: {assignedId}");
            }
            else
            {
                Debug.LogError("No valid 'id' received in the response");
            }
        });

        // Listen for 'hololens_data' event to receive data
        client.On("hololens_data", response =>
        {
            try
            {
                Debug.Log($"Raw response from WEB: {response}");
                try
                {
                    JObject jsonObject = null;
                    try
                    {
                        jsonObject = JObject.Parse(response.ToString());
                        JObject data = (JObject)"{data}";
                        UnityMainThreadDispatcher.Instance().Enqueue(() =>
                        HandleJsonMessage(data.ToString()));
                    }
                    catch (JsonReaderException)
                    {
                        try
                        {
                            JArray jsonArray = JArray.Parse(response.ToString());
                            if (jsonArray.Count > 0)
                            {
                                JObject outer = (JObject)jsonArray[0];
                                JObject data = (JObject)outer["data"];
                                Debug.Log($"Parsed data: {data}");
                                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                                HandleJsonMessage(data.ToString()));
                            }
                            else
                            {
                                Debug.LogError("Received empty JSON array.");
                                return;
                            }
                        }
                        catch (JsonReaderException ex)
                        {
                            Debug.LogError($"Failed to parse JSON as JObject or JArray: {ex.Message}");
                            return;
                        }
                    }
                }
                catch (JsonException ex)
                {
                    Debug.LogError($"Error parsing JSON: {ex.Message}");
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error parsing hololens_data response: {ex.Message}");
            }
        });
        await client.ConnectAsync();
        Debug.Log("connected! " + client);
        Debug.Log("This instance: " + this);
    }

    private void OnDestroy()
    {
        Debug.Log("destroyed!");
        if (client != null)
        {
            client.DisconnectAsync();
        }
    }

    public void HandleJsonMessage(string jsonData)
    {
        try
        {
            // Log the received data
            Debug.Log($"Received data: {jsonData}");

            // Parse the incoming JSON string into a JObject
            JObject jsonObject = JObject.Parse(jsonData);

            if (jsonObject["client"] == null)
            {
                Debug.LogError("Missing 'client' in the received JSON.");
                return; // Exit early if 'client' is missing
            }
            string client = (string)jsonObject["client"];

            if (jsonObject["type"] == null)
            {
                Debug.LogError("Missing 'type' in the received JSON.");
                return; // Exit early if 'room' is missing
            }
            string type = (string)jsonObject["type"];

            if (jsonObject["data"] == null)
            {
                Debug.LogError("Missing 'data' in the received JSON.");
                return; // Exit early if 'data' is missing
            }
            JToken dataToken = jsonObject["data"];
            JObject data;
            if (dataToken.Type == JTokenType.String)
            {
                // If data is a string, parse it again
                data = JObject.Parse((string)dataToken);
            }
            else
            {
                data = (JObject)dataToken;
            }
            // Handle different types based on the 'type' field
            // all data incoming from LMCC, publish events or call functions as needed
            switch (type)
            {
                case "VITALS":
                    // handle EV1 and EV2 vitals data
                    break;

                case "WAYPOINTS":
                    // handle waypoints data
                    // may be split up into further cases later depending on types
                    break;

                case "MESSAGING":
                    // handle all messaging data from LMCC EVs and PR
                    break;

                case "ASTRONAUT":
                    // handle other EV data such as location updates
                    break;

                case "PR_TELEMETRY":
                    // handle PR telemetry data
                    break;

                case "PR_LOCATION":
                    // handle PR location data
                    break;

                case "LTV_LOCATION":
                    // handle LTV location data
                    break;

                case "ALERTS":
                    // handle Vitals alerts data for EVs
                    break;

                case "CORVUS":

                    break;

                default:
                    // Log if the 'type' is not recognized
                    Debug.LogWarning($"Unhandled 'type': {type}");
                    break;
            }
        }
        catch (JsonException ex)
        {
            // Catch any JSON parsing errors
            Debug.LogError($"Error parsing JSON: {ex.Message}");
        }
    }


    /////////////////////////////////////////////////////////////////////////////////////////
    //////////////////////////////////  SENDING DATA ////////////////////////////////////////
    /////////////////////////////////////////////////////////////////////////////////////////

    public async void SendJsonData(Dictionary <string, object> message, string room, int clientId)
    {
        Debug.Log("This instance: " + this);
        if (client != null)
        {
            // Determine the target client based on clientId
            string targetClient = clientId switch
            {
                1 => "hololens_1", // EV1
                2 => "hololens_2", // EV2
                3 => "pr_client",  // PR
                4 => "lmcc",       // LMCC
            };

            if (targetClient == null)
            {
                Debug.LogError("Invalid clientId provided.");
                return;
            }

            // Create the data object
            Data data = new Data
            {
                client = targetClient,
                type = room,
                data = message
            };

            // Serialize the data to JSON
            string jsonString = JsonConvert.SerializeObject(data, Formatting.Indented);
           
            // Emit the appropriate event
            string eventName = clientId switch
            {
                3 => "send_to_pr",       // PR client
                4 => "send_to_room",     // LMCC client
                _ => "send_to_hololens"  // Default for hololens clients
            };

            await client.EmitAsync(eventName, jsonString);
            
            Debug.Log($"Sent message to {targetClient} in room '{room}': {jsonString}");
        }
        else
        {
            Debug.LogError("Socket client is not connected.");
        }
    }
}

# CHANGE THE ENDPOINT URL TO BE IAN'S TTTBTTT thing

# Run TSS, IAN's thing, and this script to set up the polling

# Outstanding TODOs:

* Flesh out the warning emit call for this code IDK if it works
* Fix and test the slope business
* Fix and test the other navigation stuff (only the threshold stuff seems to work theoretically)

# Monkey-patching IAN's code to inject fake TSS data

Use the script with the really long name to replace app.py in the backend folder of Ian's code. This will allow for the injection of fake TSS data and help with testing out the warnings based on thresholds

You can then run all 3 services (TSS, ian thing, and this script) and run test_warnings.py to inject fake data and test the warning system of the service.

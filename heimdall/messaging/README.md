# Messaging

The plugin does not require any user interaction while running. However, the user will need to be able to configure the plugin, and MQTT messages will need to be published. This submodule manages all communication sent to and from the plugin while active.


## HTTP

Interaction from the frontend is done through paths registered through Moonraker.

## MQTT

Events generated through the plugin (such as detecting a failure) are dispatched as MQTT messages through moonraker.
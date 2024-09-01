# dbus-battery-monitor

Initially developped to populate /Historic/ChargedEnergy and Historic/DischargedEnergy
on a system using a Multiplus II GX with Pylontec Batteries connected over canbus
as these values are not automatically populated by Pylontec batteries.

Reads battery current and voltage values on the dbus at a high rate interval (100 ms)
  and calculate how much energy has been exchanged with the battery during this interval
  A positive value is added to the /Historic/ChargedEnergy value
  A negative value is substracted to /Historic/DischargedEnergy value
Writes both calculated values on the dbus
Saves the values once per hour either on a usb key if mounted on '/run/media/sda1' or on the current folder if no usb key is mounted

At init, checks if saved values are available in the directory defined to save the values
  if yes use these values to initialize values
  if not values are set to 0
  
To stop the program nicely, create a file named kill in the module directory
  This will result in having the actual values saved at the location used to save the values

Module must be installed on /data to survive to firmware updates

To lauch automatically at system start up, insert a rc.local file in /data
  with the following instructions (or add the instruction to the rc.local file if it exists)
  python3 /data/dbus-battery-monitor/batterymonitor.py

To lauch manually from console ./run.sh while in the /data/dbus-battery-monitor folder
Nota: do not forget to make run.sh file executable after transferring the module in the Multiplus



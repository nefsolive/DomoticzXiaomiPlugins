# Python Plugin for Xiaomi Miio Plug
#
# Author: xiaoyao9184 
#
"""
<plugin key="Xiaomi-Miio-Chuangmi-Plug" 
    name="Xiaomi Miio Chuangmi Plug" 
    author="xiaoyao9184" version="0.1" 
    externallink="https://github.com/xiaoyao9184/DomoticzXiaomiPlugins">
    <params>
        <param field="Address" label="IP" width="100px" required="true"/>
        <param field="Mode1" label="Token" width="250px" required="true"/>
        <param field="Mode2" label="Mode" width="150px">
            <options>
                <option label="chuangmi.plug.m1" value="chuangmi.plug.m1" default="chuangmi.plug.m1"/>
                <option label="chuangmi.plug.v1" value="chuangmi.plug.v1"/>
                <option label="chuangmi.plug.v2" value="chuangmi.plug.v2"/>
                <option label="chuangmi.plug.v3" value="chuangmi.plug.v3"/>
            </options>
        </param>
        <param field="Mode3" label="Debug" width="200px">
            <options>
                <option label="None" value="none" default="none"/>
                <option label="Debug(Only Domoticz)" value="debug"/>
                <option label="Debug(Attach by ptvsd)" value="ptvsd"/>
            </options>
        </param>
    </params>
</plugin>
"""

# Fix import of libs installed with pip as PluginSystem has a wierd pythonpath...
import os
import sys
import site
for mp in site.getsitepackages():
    sys.path.append(mp)
import miio

import Domoticz

class CacheStatus(object):
    def __init__(self, status):
      self.status = status
      self.cache = {}

    def __getattr__(self, name):
        if name not in self.cache:
            value = getattr(self.status, name)
            if value is not None:
                self.cache[name] = value
            else:
                return None
        return self.cache[name]

    def __setattr__(self, name, value):
        if(name == 'status' or name == 'cache'):
            super(CacheStatus, self).__setattr__(name, value)
            return
        self.cache[name] = value


class ChuangmiPlugPlugin:

    unit_main = 1
    unit_temp = 2
    unit_load = 3
    unit_usb = 4
    unit_led = 5

    def __init__(self):
        self.miio = None
        self.status = None
        self.heartbeatCount = 0
        return

    def onStart(self):
        # Debug
        debug = 0
        if (Parameters["Mode3"] != "none"):
            Domoticz.Debugging(1)
            debug = 1
        
        if (Parameters["Mode3"] == 'ptvsd'):
            Domoticz.Log("Debugger ptvsd started, use 0.0.0.0:5678 to attach")
            import ptvsd 
            ptvsd.enable_attach()
            ptvsd.wait_for_attach()
        elif (Parameters["Mode3"] == 'rpdb'):
            Domoticz.Log("Debugger rpdb started, use 'telnet 0.0.0.0 4444' to connect")
            import rpdb
            rpdb.set_trace()


        # Create miio
        ip = Parameters["Address"]
        token = Parameters["Mode1"]
        mode = Parameters["Mode2"]
        self.miio = miio.chuangmi_plug.ChuangmiPlug(ip, token, 0, debug, True, mode)
        Domoticz.Debug("Xiaomi Miio Chuangmi created with address '" + ip
            + "' and token '" + token
            + "' and mode '" + mode + "'")

        # Add main devices
        if (self.unit_main not in Devices):
            # See https://github.com/domoticz/domoticz/blob/development/hardware/hardwaretypes.h for device types
            Domoticz.Device(
                Name = "Chuangmi plug", 
                Unit = self.unit_main, 
                Type = 244, 
                Subtype = 62,
                Image = 1).Create()
        if (self.unit_temp not in Devices):
            Domoticz.Device(
                Name = "Chuangmi plug temperature", 
                Unit = self.unit_temp, 
                Type = 80, 
                Subtype = 5).Create()
        
        # Read function
        self.UpdateStatus(False)

        # Add optional devices
        if (self.status.load_power is not None 
            and self.unit_load not in Devices):
            Domoticz.Device(
                Name = "Chuangmi plug electric", 
                Unit = self.unit_load, 
                Type = 243, 
                Subtype = 29).Create()
        if (self.status.usb_power is not None 
            and self.unit_usb not in Devices):
            Domoticz.Device(
                Name = "Chuangmi plug usb", 
                Unit = self.unit_usb, 
                Type = 244, 
                Subtype = 62,
                Image = 1).Create()
        if (self.status.wifi_led is not None 
            and self.unit_led not in Devices):
            Domoticz.Device(
                Name = "Chuangmi plug led", 
                Unit = self.unit_led, 
                Type = 244, 
                Subtype = 62).Create()

        # Read initial state
        self.UpdateStatus()

        DumpConfigToLog()

        return

    def onStop(self):
        Domoticz.Debug("onStop called")
        return

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called: Connection=" + str(Connection) + ", Status=" + str(Status) + ", Description=" + str(Description))
        return

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called: Connection=" + str(Connection) + ", Data=" + str(Data))
        return

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called: Unit=" + str(Unit) + ", Parameter=" + str(Command) + ", Level=" + str(Level))

        if (self.unit_main == Unit):
            if ("On" == Command):
                self.TurnOn()
            elif ("Off" == Command):
                self.TurnOff()
        elif (self.unit_usb == Unit):
            if ("On" == Command):
                self.TurnOnUsb()
            elif ("Off" == Command):
                self.TurnOffUsb()
        elif (self.unit_led == Unit):
            if ("On" == Command):
                self.TurnOnWifiLed()
            elif ("Off" == Command):
                self.TurnOffWifiLed()
        else:
            Domoticz.Error("Unknown Unit number : " + str(Unit))

        # update status
        self.UpdateStatus()
        return

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)
        return

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")
        return

    def onHeartbeat(self):
        self.heartbeatCount += 1
        if (self.heartbeatCount == 10): # Each minute
            self.UpdateStatus()
            self.heartbeatCount = 0
        return

        
    def UpdateStatus(self, updateDevice = True):
        if not hasattr(self, 'miio'):
            return
        self.status = self.miio.status()
        log = "Status : On = " + str(self.status.is_on) + \
                ", Power = " + str(self.status.power) + \
                ", Temperature = " + str(self.status.temperature)
        if(self.status.load_power):
            log = log + ", Load Power = " + str(self.status.load_power)
        if(self.status.usb_power):
            log = log + ", Usb Power = " + str(self.status.usb_power)
        if(self.status.wifi_led):
            log = log + ", Wifi Led = " + str(self.status.wifi_led)

        Domoticz.Debug(log)

        if (not updateDevice):
            self.status = CacheStatus(self.status)
            return

        if (self.status.is_on == True):
            UpdateDevice(self.unit_main, 1, "On")
        else:
            UpdateDevice(self.unit_main, 0, "Off")

        if (self.status.usb_power == True):
            UpdateDevice(self.unit_usb, 1, "On")
        elif (self.status.usb_power == False):
            UpdateDevice(self.unit_usb, 0, "Off")

        if (self.status.wifi_led == True):
            UpdateDevice(self.unit_led, 1, "On")
        elif (self.status.wifi_led == False):
            UpdateDevice(self.unit_led, 0, "Off")

        if (self.status.temperature):
            UpdateDevice(self.unit_temp, self.status.temperature, str(self.status.temperature))
        if (self.status.load_power):
            # https://www.domoticz.com/forum/viewtopic.php?t=21978
            # https://www.domoticz.com/wiki/Domoticz_API/JSON_URL%27s#Electricity_.28instant_and_counter.29
            UpdateDevice(self.unit_load, 0, str(self.status.load_power) + ';0.000')

        self.status = CacheStatus(self.status)
        return

    def TurnOn(self):
        if (self.status.is_on == False):
            result = self.miio.on()
            Domoticz.Log("Turn on result:" + str(result))
            if (result == ["ok"] or result == []):
                self.status.is_on = True
                UpdateDevice(self.unit_main, 1, "On")
            else:
                Domoticz.Log("Turn on failure:" + str(result))
        return

    def TurnOff(self):
        if (self.status.is_on == True):
            result = self.miio.off()
            Domoticz.Log("Turn off result:" + str(result))
            if (result == ["ok"] or result == []):
                self.status.is_on = False
                UpdateDevice(self.unit_main, 0, "Off")
            else:
                Domoticz.Log("Turn off failure:" + str(result))
        return

    def TurnOnUsb(self):
        if (self.status.usb_power == False):
            result = self.miio.usb_on()
            Domoticz.Log("Turn usb on result:" + str(result))
            if (int(result) == 0 or result == ["ok"]):
                self.status.usb_power = True
                UpdateDevice(self.unit_usb, 1, "On")
            else:
                Domoticz.Log("Turn usb on failure:" + str(result))
        return

    def TurnOffUsb(self):
        if (self.status.usb_power == True):
            result = self.miio.usb_off()
            Domoticz.Log("Turn usb off result:" + str(result))
            if (int(result) == 0 or result == ["ok"]):
                self.status.usb_power = False
                UpdateDevice(self.unit_usb, 0, "Off")
            else:
                Domoticz.Log("Turn usb off failure:" + str(result))
        return

    def TurnOnWifiLed(self):
        if (self.status.wifi_led == False):
            result = self.miio.set_wifi_led(True)
            Domoticz.Log("Turn led on result:" + str(result))
            if (result == ["ok"]):
                self.status.wifi_led = True
                UpdateDevice(self.unit_led, 1, "On")
            else:
                Domoticz.Log("Turn usb off failure:" + str(result))
        return

    def TurnOffWifiLed(self):
        if (self.status.wifi_led == True):
            result = self.miio.set_wifi_led(False)
            Domoticz.Log("Turn led off result:" + str(result))
            if (result == ["ok"]):
                self.status.wifi_led = False
                UpdateDevice(self.unit_led, 0, "Off")
            else:
                Domoticz.Log("Turn usb off failure:" + str(result))
        return

global _plugin
_plugin = ChuangmiPlugPlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


# Generic helper functions

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
    
def UpdateDevice(Unit, nValue, sValue):
    if (Unit not in Devices): return
    if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
        Domoticz.Debug("Update '" + Devices[Unit].Name + "' : " + str(nValue) + " - " + str(sValue))
        # Warning: The lastest beta does not completly support python 3.5
        # and for unknown reason crash if Update methode is called whitout explicit parameters
        Devices[Unit].Update(nValue = nValue, sValue = str(sValue))
    return
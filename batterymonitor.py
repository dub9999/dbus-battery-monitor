#!/usr/bin/env python3 -u
# -u to force the stdout and stderr streams to be unbuffered

from argparse import ArgumentParser
import dbus
import dbus.mainloop.glib
import faulthandler
import signal
import os
import sys
from time import tzset
from datetime import datetime
import traceback
from gi.repository import GLib

# Import local modules (sub-folder /ext/velib_python)
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusItemImport
from ve_utils import wrap_dbus_value, unwrap_dbus_value

import logging
log = logging.getLogger()

NAME = os.path.basename(__file__)
VERSION = "0.01"

__all__ = ['NAME', 'VERSION']

FOLDER = os.path.dirname(os.path.abspath(__file__))
DEF_PATH = "/run/media/sda1"
LOGFILE = '/batterymonitor.log'

UPDATE_INTERVAL = 100

# Adjusting time zone as system is not aligned with the time zone set in the UI 
os.environ['TZ'] = 'Europe/Paris'
tzset()

class BatteryMonitor(object):
    def __init__(self):
        # Connect to session bus whenever present, else use the system bus
        self.bus=dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
        self.dbus_name='com.victronenergy.battery.socketcan_can0'
        self.dbus_entities={
            'voltage' : {'path' : '/Dc/0/Voltage', 'value' : 0, 'import' : None},
            'current' : {'path' : '/Dc/0/Current', 'value' : 0, 'import' : None},
            'charged' : {'path' : '/History/ChargedEnergy', 'value' : 0, 'import' : None},
            'discharged' : {'path' : '/History/DischargedEnergy', 'value' : 0, 'import' : None}
        }
        self.dbus_objects={}
        # Last recorded system time
        self.last_seen = None
        # Path for file exchange
        self.file_path=(DEF_PATH if os.path.exists(DEF_PATH) else FOLDER)
        self.is_historized=True
        self.values_refreshed=False

    #to read and write values on dbus      
    def __update_dbus__(self):
        try:
            #write battery/history
            self.dbus_objects['charged'].set_value(self.dbus_entities['charged']['value'])
            self.dbus_objects['discharged'].set_value(self.dbus_entities['discharged']['value'])
            #read voltage and current
            self.dbus_entities['voltage']['value'] = self.dbus_objects['voltage'].get_value()
            self.dbus_entities['current']['value'] = self.dbus_objects['current'].get_value()
            success=True
        except:
            log.error(f'exception occured during __update_dbus__(): ', exc_info=True)
            success=False
        #initialiser temps de la dernière lecture
        self.last_seen = datetime.now()
        return success

    #to read an index value in a file
    def __read_index__(self, filename):
        index = None
        if os.path.isfile(filename):
            f = open(filename, "r")
            index=float(f.read())
            f.close()
        return index

    #to write an index value in a file
    def __write_index__(self, filename, index):
        f = open(filename, "w")
        f.write(str(index))
        f.close()

    #to save everything that we want to save
    def __save__(self):
        #écrire l'index de charge
        filename=self.file_path+'/index_charged'
        index=self.dbus_entities['charged']['value']
        self.__write_index__(filename, index)
        log.debug(f'{self.dbus_entities["charged"]["path"]} saved in {filename}')
        #écrire l'index de décharge
        filename=self.file_path+'/index_discharged'
        index=self.dbus_entities['discharged']['value']
        self.__write_index__(filename, index)
        log.debug(f'{self.dbus_entities["discharged"]["path"]} saved in {filename}')

    #to nicely end the glib loop
    def __soft_exit__(self):
        log.info(f'terminated on request')
        self.__save__()
        os._exit(1)

    def init(self):
        # initialize charge and discharge indexes
        charged_index=self.__read_index__(self.file_path+'/index_charged')
        if isinstance (charged_index, (float)):
            self.dbus_entities['charged']['value'] = charged_index
        discharged_index=self.__read_index__(self.file_path+'/index_discharged')
        if isinstance (discharged_index, (float)):
            self.dbus_entities['discharged']['value'] = discharged_index
        try:
            for name, dbus_entity in self.dbus_entities.items():
                #initialize dbus objects
                self.dbus_objects[name]=VeDbusItemImport(self.bus, self.dbus_name, dbus_entity['path'])
            #write battery/history
            self.dbus_objects['charged'].set_value(self.dbus_entities['charged']['value'])
            self.dbus_objects['discharged'].set_value(self.dbus_entities['discharged']['value'])
            #read voltage and current
            self.dbus_entities['voltage']['value'] = self.dbus_objects['voltage'].get_value()
            self.dbus_entities['current']['value'] = self.dbus_objects['current'].get_value()
            self.values_refreshed=True
            self.last_seen = datetime.now()
        except:
            log.error(
                f' {NAME}: exception occured during init(), program aborted',
                exc_info=True
                )
            os._exit(1)
        log.info(f'{self.dbus_entities["charged"]["path"]} = {self.dbus_entities["charged"]["value"]}')
        log.info(f'{self.dbus_entities["discharged"]["path"]} = {self.dbus_entities["discharged"]["value"]}')

    #to update values
    def update(self):
        #if a file named kill exists in the folder of this file, exit the program
        if os.path.isfile(FOLDER+'/kill'):
            os.remove(FOLDER+'/kill')
            self.__soft_exit__()
        try:
            #get system time and calculate time lag since last calculation
            this_time =	datetime.now()
            interval = this_time - self.last_seen
            self.last_seen = this_time
            #calculate energy using previously stored values 
            # Calcul en kWh
            if self.values_refreshed and (interval.total_seconds() > 0):
                energy = (
                    self.dbus_entities['voltage']['value'] * self.dbus_entities['current']['value']
                    * interval.total_seconds()
                    )/3600000
                self.values_refreshed=False
            else:
                energy = 0
            # Mettre à jour les valeurs dans l'array
            if (energy >= 0): 
                self.dbus_entities['charged']['value'] += energy
            elif (energy < 0):
                self.dbus_entities['discharged']['value'] -= energy
            #update values on dbus
            self.values_refreshed=self.__update_dbus__()
            # Historiser toutes les heures
            if datetime.now().minute == 0 and self.is_historized == False:
                self.__save__()
                self.is_historized=True
        
            if datetime.now().minute != 0 and self.is_historized == True:
                self.is_historized = False
        except:
            log.error('uncaught exception in update', exc_info=True)
         
        return True

def main():
    logging.basicConfig(
        filename=(DEF_PATH+LOGFILE if os.path.exists(DEF_PATH) else os.path.abspath(__file__)+'.log'),
        format='%(asctime)s - %(levelname)s - %(filename)-8s %(message)s', 
        datefmt="%Y-%m-%d %H:%M:%S", 
        level=logging.INFO
        )

    log.info('')
    log.info('------------------------------------------------------------')
    log.info(
     f'started, logging to '
        f'{DEF_PATH+LOGFILE if os.path.exists(DEF_PATH) else os.path.abspath(__file__)+".log"}'
        )

    signal.signal(signal.SIGINT, lambda s, f: os._exit(1))
    faulthandler.register(signal.SIGUSR1)
  
    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    mainloop = GLib.MainLoop()

    batmon = BatteryMonitor()

    batmon.init()
    log.info(f'initialization completed, now running permanent loop')
    GLib.timeout_add(UPDATE_INTERVAL, batmon.update)
    mainloop.run()
 
if __name__ == '__main__':
    main()

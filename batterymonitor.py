#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fichier permettant de calculer les échanges d'énergie de la batterie (charge et décharge)
et de publier les cumuls sur le dbus dans les chemins prévus par victron
Les cumuls sont historisés chaque heure dans la clé usb
Le code est lancé automatiquement lorsque le Multiplus est mis en marche
Une boucle permanente est lancée après lune initalisation
Il est préférable d'arrêter le code avant d'éteindre le Multiplus en créant un fichier kill vide dans le répertoire du fichier
Ceci a pour effet d'historiser les valeurs actuelles dans la clé usb branchée sur le multiplus
Le fichier kill est effacé automatiquement lors de l'arrêt
"""

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

# Import des modules locaux (sous dossier /ext/velib_python)
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from ve_utils import wrap_dbus_value, unwrap_dbus_value

import logging
log = logging.getLogger()

NAME = os.path.basename(__file__)
VERSION = "0.01"

__all__ = ['NAME', 'VERSION']

UPDATE_INTERVAL = 100

# Ajustement du fuseau horaire 
os.environ['TZ'] = 'Europe/Paris'
tzset()

class BatteryMonitor(object):
  def __init__(self):
    # Connect to session bus whenever present, else use the system bus
    self.bus=dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
    self.dbus_name='com.victronenergy.battery.socketcan_can0'
    self.dbus_objects={
      'voltage' : {'path' : '/Dc/0/Voltage', 'value' : 10, 'proxy' : None},
      'current' : {'path' : '/Dc/0/Current', 'value' : 10, 'proxy' : None},
      'charged' : {'path' : '/History/ChargedEnergy', 'value' : 10, 'proxy' : None},
      'discharged' : {'path' : '/History/DischargedEnergy', 'value' : 10, 'proxy' : None}
    }
    # Temps systeme lors de la dernière lecture
    self.last_seen = None
    # Chemin pour historiser les valeurs des index de charge et de décharge
    #dans la clé usb si elle présente
    if os.path.exists('/run/media/sda1'):
      self.file_path='/run/media/sda1'
    #sinon dans le répertoire du fichier
    else:
      self.file_path=os.getcwd()
    self.is_historized=True

  # Fonction pour initialiser les valeurs de l'objet dbusObjects
  # A appeler après la création de l'objet
  # Si les valeurs ChargedEnergy et DischargedEnergy sont à none, on initialise les valeurs dans le dbus à 0
  # On récupère aussi le temps système
  def init(self):
    # initialiser les index de charge et de décharge
    charged_index=self.__read_index__(self.file_path+'/index_charged')
    if isinstance (charged_index, (float)):
      self.dbus_objects['charged']['value'] = charged_index
    discharged_index=self.__read_index__(self.file_path+'/index_discharged')
    if isinstance (discharged_index, (float)):
      self.dbus_objects['discharged']['value'] = discharged_index
    #initialiser les échanges avec le dbus
    try:
      # initialiser les proxy
      for name, dbus_object in self.dbus_objects.items():
        dbus_object['proxy'] = self.bus.get_object(self.dbus_name, dbus_object['path'], introspect=False)
      #écrire les index
      self.dbus_objects['charged']['proxy'].SetValue(wrap_dbus_value(charged_index))
      self.dbus_objects['discharged']['proxy'].SetValue(wrap_dbus_value(discharged_index))
      # lire la tension et le courant
      self.dbus_objects['voltage']['value'] = unwrap_dbus_value(self.dbus_objects['voltage']['proxy'].GetValue())
      self.dbus_objects['current']['value'] = unwrap_dbus_value(self.dbus_objects['current']['proxy'].GetValue())
    except:
      log.error('Exception occured during battery_monitor init, program ended', exc_info=True)
      log.error('------------------------------------------------------------')
      os._exit(1)
    #initialiser temps de la dernière lecture
    self.last_seen = datetime.now()
    log.debug('Battery monitor initialized')

  #pour terminer la boucle permanente de façon propre
  def __exit_program__ (self):
    log.info('Program terminated on request')
    try:
      self.__save__()
      log.info('------------------------------------------------------------')
    except:
      log.error('Exception occured when saving battery_monitor', exc_info=True)
      log.info('------------------------------------------------------------')
    os.remove(os.getcwd()+'/kill')
    os._exit(1)

  #pour historiser les valeurs des index de charge et de décharge
  def __save__(self):
    #écrire l'index de charge
    self.__write_index__(self.file_path+'/index_charged', self.dbus_objects['charged']['value'])
    #écrire l'index de charge
    self.__write_index__(self.file_path+'/index_discharged', self.dbus_objects['discharged']['value'])

  #pour lire la valeur d'un index dans un fichier
  def __read_index__(self, filename):
    index = None
    if os.path.isfile(filename):
      f = open(filename, "r")
      index=float(f.read())
      f.close()
    return index

  #pour écrire la valeur d'un index dans un fichier
  def __write_index__(self, filename, index):
    f = open(filename, "w")
    f.write(str(index))
    f.close()

  def update(self):
    #pour arrêter proprement la boucle permanente si besoin
    #si un fichier kill existe dans le répertoire du fichier
    if os.path.isfile(os.getcwd()+'/kill'):
      self.__exit_program__()
    # Lire le temps systeme, calculer l'intervalle de temps par rapport à la mesure précédente et mettre à jour le temps de la dernière lecture
    this_time =	datetime.now()
    interval = this_time - self.last_seen
    self.last_seen = this_time
    # Calculer l'énergie transférée dans l'intervalle en utilisant les valeurs de tension et de courant stockées
    # Calcul en mWh en arrondissant les valeurs de tension et de courant à 2 digits
    if (interval.total_seconds() > 0):
      energy = (self.dbus_objects['voltage']['value'] * self.dbus_objects['current']['value'] * interval.total_seconds())/3600000
    else:
      energy = 0
    # Mettre à jour les valeurs dans l'array
    if (energy > 0): 
      self.dbus_objects['charged']['value'] += energy
    elif (energy < 0):
      self.dbus_objects['discharged']['value'] -= energy
    #
    try:
      # Historiser toutes les heures
      if datetime.now().minute == 0 and self.is_historized == False:
        self.__save__()
        self.is_historized=True
        
      if datetime.now().minute != 0 and self.is_historized == True:
        self.is_historized = False
      
      # Ecrire la valeur dans le bus
      self.dbus_objects['charged']['proxy'].SetValue(wrap_dbus_value(self.dbus_objects['charged']['value']))
      self.dbus_objects['discharged']['proxy'].SetValue(wrap_dbus_value(self.dbus_objects['discharged']['value']))
      #Lire les nouvelles valeurs de voltage et current
      self.dbus_objects['voltage']['value'] = unwrap_dbus_value(self.dbus_objects['voltage']['proxy'].GetValue())
      self.dbus_objects['current']['value'] = unwrap_dbus_value(self.dbus_objects['current']['proxy'].GetValue())
      
    except:
      log.error('Exception occured during update, program ended', exc_info=True)
      log.info('------------------------------------------------------------')
      os._exit(1)
    return True

def main():
  logging.basicConfig(
    filename=os.getcwd()+'/batterymonitor.log', 
    format='%(asctime)s: %(levelname)-8s %(message)s', 
    datefmt="%Y-%m-%d %H:%M:%S", 
    level=logging.INFO)

  log.info('------------------------------------------------------------')
  log.info('Program started')

  signal.signal(signal.SIGINT, lambda s, f: os._exit(1))
  faulthandler.register(signal.SIGUSR1)
  
  dbus.mainloop.glib.threads_init()
  dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
  mainloop = GLib.MainLoop()

  batmon = BatteryMonitor()

  batmon.init()

  GLib.timeout_add(UPDATE_INTERVAL, batmon.update)
  mainloop.run()
 
if __name__ == '__main__':
    main()

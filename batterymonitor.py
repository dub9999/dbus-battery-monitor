#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dbus
import datetime
import time
from utils import private_bus
from ve_utils import wrap_dbus_value, unwrap_dbus_value
import logging
import os
from math import floor

log = logging.getLogger()

class BatteryMonitor(object):
	def __init__(self, dbusConn):
		self.bus=dbusConn
		self.dbusName='com.victronenergy.battery.socketcan_can0'
		self.dbusObjects={
			'voltage' : {'path' : '/Dc/0/Voltage', 'value' : 0, 'proxy' : None},
			'current' : {'path' : '/Dc/0/Current', 'value' : 0, 'proxy' : None},
			'charged' : {'path' : '/History/ChargedEnergy', 'value' : 0, 'proxy' : None},
			'discharged' : {'path' : '/History/DischargedEnergy', 'value' : 0, 'proxy' : None}
			}
		self.previousTime = None

	# Fonction pour initialiser les valeurs de l'objet dbusObjects
	# A appeler après la création de l'objet
	# Si les valeurs ChargedEnergy et DischargedEnergy sont à none, on initialise les valeurs dans le dbus à 0
	# On récupère aussi le temps système
	def init(self):
		# initialiser les proxy
		for name, dbusObject in self.dbusObjects.items():
			dbusObject['proxy'] = self.bus.get_object(self.dbusName, dbusObject['path'], introspect=False)
		# initialiser les index de charge et de décharge
		if os.path.isfile('/data/home/root/venus.dbus-homedub/index_charged'):
			f = open("/data/home/root/venus.dbus-homedub/index_charged", "r")
			charged_index=float(f.read())
			f.close()
			if isinstance (charged_index, (float)):
				self.dbusObjects['charged']['value'] = charged_index
				self.dbusObjects['charged']['proxy'].SetValue(wrap_dbus_value(charged_index))
		if os.path.isfile('/data/home/root/venus.dbus-homedub/index_discharged'):
			f = open("/data/home/root/venus.dbus-homedub/index_discharged", "r")
			discharged_index=float(f.read())
			f.close()
			if isinstance (discharged_index, (float)):
				self.dbusObjects['discharged']['value'] = discharged_index
				self.dbusObjects['discharged']['proxy'].SetValue(wrap_dbus_value(discharged_index))
		self.dbusObjects['voltage']['value'] = unwrap_dbus_value(self.dbusObjects['voltage']['proxy'].GetValue())
		self.dbusObjects['current']['value'] = unwrap_dbus_value(self.dbusObjects['current']['proxy'].GetValue())
		self.previousTime = datetime.datetime.now()
		log.debug('Battery monitor initialized')

	# Fonction pour écrire les valeurs des index de charge et de décharge dans des fichiers
	# A appeler lors de l'arrêt du programme homedub.py
	def save(self):
		charged_index=self.dbusObjects['charged']['value']
		f = open("/data/home/root/venus.dbus-homedub/index_charged", "w")
		f.write(str(charged_index))
		f.close()
		discharged_index=self.dbusObjects['discharged']['value']
		f = open("/data/home/root/venus.dbus-homedub/index_discharged", "w")
		f.write(str(discharged_index))
		f.close()

	def update(self):
		# Lire le temps systeme, calculer l'intervalle de temps par rapport à la mesure précédente et mettre à jour le temps de la dernière lecture
		thisTime =	datetime.datetime.now()
		interval = thisTime - self.previousTime
		self.previousTime = thisTime
		# Calculer l'énergie transférée dans l'intervalle en utilisant les valeurs de tension et de courant stockées
		# Calcul en mWh en arrondissant les valeurs de tension et de courant à 2 digits
		if (interval.total_seconds() > 0):
			energy = (self.dbusObjects['voltage']['value'] * self.dbusObjects['current']['value'] * interval.total_seconds())/3600000
		else:
			energy = 0
		# Mettre à jour les valeurs dans l'array
		if (energy > 0): 
			self.dbusObjects['charged']['value'] += energy
		elif (energy < 0):
			self.dbusObjects['discharged']['value'] -= energy

		# Ecrire la valeur dans le bus
		self.dbusObjects['charged']['proxy'].SetValue(wrap_dbus_value(self.dbusObjects['charged']['value']))
		self.dbusObjects['discharged']['proxy'].SetValue(wrap_dbus_value(self.dbusObjects['discharged']['value']))
		#Lire les nouvelles valeurs de voltage et current
		self.dbusObjects['voltage']['value'] = unwrap_dbus_value(self.dbusObjects['voltage']['proxy'].GetValue())
		self.dbusObjects['current']['value'] = unwrap_dbus_value(self.dbusObjects['current']['proxy'].GetValue())
		"""
		print (interval.total_seconds(), energy)
		print ('charged', ' : ', self.dbusObjects['charged']['kWh'],
			self.dbusObjects['charged']['Wh'], self.dbusObjects['charged']['mWh'], self.dbusObjects['charged']['value'])
		print ('discharged', ' : ', self.dbusObjects['discharged']['kWh'],
			self.dbusObjects['discharged']['Wh'], self.dbusObjects['discharged']['mWh'], self.dbusObjects['discharged']['value'])
		"""

	def printAttributes(self):
		for name, dbusObject in self.dbusObjects.items():
			if (name == 'charged') or (name == 'discharged'):
				print (name, ' : ', dbusObject['kWh'], dbusObject['Wh'], dbusObject['mWh'], dbusObject['value'])
			else:
				print (name, ' : ', dbusObject['value'])
		print('Previous time : ', self.previousTime)
	
# Pour tester les fonctionalités en executant directement le fichier
if __name__ == '__main__':
	logging.basicConfig(
    filename='/data/home/root/venus.dbus-homedub/sunspec.log', 
    format='%(asctime)s: %(levelname)-8s %(message)s', 
    datefmt="%Y-%m-%d %H:%M:%S", 
    level=logging.INFO)

	dbusConn = private_bus()
	batmon = BatteryMonitor (dbusConn)
	batmon.printAttributes()
	batmon.init()
	batmon.printAttributes()
	
	i = 0
	while i < 1000:
		i = i +1
		time.sleep(0.25)
		batmon.update()
		if os.path.isfile('/data/home/root/venus.dbus-homedub/kill'):
			batmon.save()
			print('Program interrupted on purpose')
			os.remove('kill')
			os._exit(1)

	batmon.printAttributes()
		

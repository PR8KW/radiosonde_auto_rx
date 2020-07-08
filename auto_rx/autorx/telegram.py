#!/usr/bin/env python
#
#   radiosonde_auto_rx - Telegram Notification
#   Modified from @jasonmid Pushover Notification branch https://github.com/jasonmid/radiosonde_auto_rx/tree/testing1.2/master
#   Based on email_notification.py Copyright (C) 2018 Philip Heron <phil@sanslogic.co.uk>
#   Released under GNU GPL v3 or later

import datetime
import logging
import time
import socket
import httplib, urllib

from threading import Thread
from .utils import position_info
from .config import read_auto_rx_config

try:
    # Python 2
    from Queue import Queue

except ImportError:
    # Python 3
    from queue import Queue


class TelegramNotification(object):
    """ Radiosonde Telegram Notification Class.

    Accepts telemetry dictionaries from a decoder, and sends a Telegram Notification on newly detected sondes.
    Incoming telemetry is processed via a queue, so this object should be thread safe.

    """

    # We require the following fields to be present in the input telemetry dict.
    REQUIRED_FIELDS = [ 'id', 'lat', 'lon', 'alt', 'type', 'freq']

    def __init__(self,  bot_token = "undefined", chat_id = "undefined", landing_lat1 = 0.0, landing_lon1 = 0.0, landing_alt1 = 0.0, landing_distance1 = 5.0, landing_altitude1 = 5.0, timeout = 0):
        """ Init a new Telegram Notification Thread """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.landing_lat1 = landing_lat1
        self.landing_lon1 = landing_lon1
        self.landing_alt1 = landing_alt1
        self.landing_distance1 = landing_distance1
        self.landing_altitude1 = landing_altitude1
        self.timeout = timeout
        
        # Dictionary to track sonde IDs
        self.sondes = {}
        self.sondes_landing = {}
        self.sondes_landing_lost = {}

        # Input Queue.
        self.input_queue = Queue()

        # Start queue processing thread.
        self.input_processing_running = True
        self.input_thread = Thread(target = self.process_queue)
        self.input_thread.start()

        self.log_info("Started Telegram Notifier Thread")

    # Uncomment the next line to check Telegram configuration
    # self.log_info("Started Telegram Notifier Thread Bot_Token: %s Chat_Id: %s" % (self.app_token,self.user_key))

    def add(self, telemetry):
        """ Add a telemetry dictionary to the input queue. """
        # Check the telemetry dictionary contains the required fields.
        for _field in self.REQUIRED_FIELDS:
            if _field not in telemetry:
                self.log_error("JSON object missing required field %s" % _field)
                return

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(telemetry)
        else:
            self.log_error("Processing not running, discarding.")


    def process_queue(self):
        """ Process packets from the input queue. """
        while self.input_processing_running:

            # Process everything in the queue.
            while self.input_queue.qsize() > 0:
                try:
                    _telem = self.input_queue.get_nowait()
                    self.process_telemetry(_telem)

                except Exception as e:
                    self.log_error("Error processing telemetry dict - %s" % str(e))

            # Send last RX position 
            self.process_lost()
            # Sleep while waiting for some new data.
            time.sleep(0.5)

    def get_ip_address(self):
    	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.connect(("1.1.1.1", 80))
	return s.getsockname()[0]



    def process_telemetry(self, telemetry):
        """ Process a new telemmetry dict, and send an notification if it is a new sonde. """
        _id = telemetry['id']

        if _id not in self.sondes:
            try:
                # This is a new sonde. Send the notification.

                IPAddr = self.get_ip_address()

                msg  = 'Sonde launch detected:\n'
                msg += '\n'
                msg += 'Callsign:  %s\n' % _id
                msg += 'Type:      %s\n' % telemetry['type']
                msg += 'Frequency: %s\n' % telemetry['freq']
                msg += 'Position:  %.5f,%.5f\n' % (telemetry['lat'], telemetry['lon'])
                msg += 'Altitude:  %dm\n' % round(telemetry['alt'])
                msg += '\n'
                msg += 'https://aprs.fi/#!call=a/%s\n' % _id
                msg += '\n'
                msg += 'https://sondehub.org/%s\n' % _id

                conn = httplib.HTTPSConnection("api.telegram.org:443")
                conn.request("POST", "/bot%s/sendMessage" % self.bot_token,
                    urllib.urlencode({
                    "chat_id": self.chat_id,
                    "text": msg,
                    "disable_web_page_preview": True,
                    }), { "Content-type": "application/x-www-form-urlencoded" })
                conn.getresponse()

                self.log_info("Telegram Notification sent.")
                
            except Exception as e:
                self.log_error("Error sending Telegram Notification - %s" % str(e))

        self.sondes[_id] = { 'last_time': time.time() }

        if _id not in self.sondes_landing :
            try:
                # This is an existing sonde.  Send a single notification if it is falling
                # and is within the range specified.
                # self.log_info("geofence:  %.5f,%.5f" % (self.landing_lat1, self.landing_lon1))
                if self.landing_lat1 != 0.0 and self.landing_lon1 != 0.0:

                    # Calculate the distance from the desired position to the payload.
                    _listener = (self.landing_lat1, self.landing_lon1, self.landing_alt1)
                    _payload = (telemetry['lat'], telemetry['lon'], telemetry['alt'])

                    # Calculate using positon_info function from rotator_utils.py
                    _info = position_info(_listener, _payload)

                    # self.log_info("Sonde Location.  %dm, %dm, %dkm/h" % (_info['straight_distance'], telemetry['alt'], telemetry['vel_h']))

                    if (_info['straight_distance'] < self.landing_distance1) and (telemetry['alt'] < self.landing_altitude1) and (telemetry['vel_v'] < 0):

                        IPAddr = self.get_ip_address()

                        msg = 'Sonde falling near position 1:\n'
                        msg += '\n'
                        msg += 'Callsign:  %s\n' % _id
                        msg += 'Type:      %s\n' % telemetry['type']
                        msg += 'Frequency: %s\n' % telemetry['freq']
                        msg += 'Position:  %.5f,%.5f\n' % (telemetry['lat'], telemetry['lon'])
                        msg += '\n'
                        msg += 'Range:     %dm\n' % _info['straight_distance']
                        msg += 'Altitude:  %dm\n' % round(telemetry['alt'])
                        msg += '\n'
                        msg += 'https://aprs.fi/#!call=a/%s\n' % _id
                        msg += '\n'
                        msg += 'https://sondehub.org/%s\n' % _id

                        conn = httplib.HTTPSConnection("api.telegram.org:443")
                        conn.request("POST", "/bot%s/sendMessage" % self.bot_token,
                            urllib.urlencode({
                            "chat_id": self.chat_id,
                            "text": msg,
                            "disable_web_page_preview": True,
                            }), {"Content-type": "application/x-www-form-urlencoded"})
                        conn.getresponse()

                        self.log_info("Telegram Notification sent.")
                        self.sondes_landing[_id] = {'last_time': time.time()}

            except Exception as e:
                self.log_error("Error sending Telegram Notification - %s" % str(e))

    def process_lost(self):
        """ Send Last sonde position when rx timeout, if on landing notification. """

        _now = time.time()
        for _id in self.sondes.copy().keys():
            if (_id not in self.sondes_landing_lost) and (_id in self.sondes_landing) :
                try:
                # This is an existing sonde with falling region notification.  
                # Send a single notification when rx timeout.

                    if _now > (self.sondes[_id]['last_time'] + self.timeout):
				
                        # Calculate the distance from the desired position to the payload.
                        _listener = (self.landing_lat1, self.landing_lon1, self.landing_alt1)
                        _payload = (telemetry['lat'], telemetry['lon'], telemetry['alt'])

                        # Calculate using positon_info function from rotator_utils.py
                        _info = position_info(_listener, _payload)

                        # self.log_info("Sonde Location.  %dm, %dm, %dkm/h" % (_info['straight_distance'], telemetry['alt'], telemetry['vel_h']))

                        # if (_info['straight_distance'] < self.landing_distance1) and (telemetry['alt'] < self.landing_altitude1) and (telemetry['vel_v'] < 0):

                        IPAddr = self.get_ip_address()

                        msg = 'Sonde lost RX near position 1:\n'
                        msg += '\n'
                        msg += 'Callsign:  %s\n' % _id
                        msg += 'Type:      %s\n' % telemetry['type']
                        msg += 'Frequency: %s\n' % telemetry['freq']
                        msg += 'Position:  %.5f,%.5f\n' % (telemetry['lat'], telemetry['lon'])
                        msg += '\n'
                        msg += 'Range:     %dm\n' % _info['straight_distance']
                        msg += 'Altitude:  %dm\n' % round(telemetry['alt'])
                        msg += '\n'
                        msg += 'https://aprs.fi/#!call=a/%s\n' % _id
                        msg += '\n'
                        msg += 'https://sondehub.org/%s\n' % _id

                        conn = httplib.HTTPSConnection("api.telegram.org:443")
                        conn.request("POST", "/bot%s/sendMessage" % self.bot_token,
                            urllib.urlencode({
                            "chat_id": self.chat_id,
                            "text": msg,
                            "disable_web_page_preview": True,
                            }), {"Content-type": "application/x-www-form-urlencoded"})
                        conn.getresponse()

                        self.log_info("Telegram Notification sent.")
                        self.sondes_landing_lost[_id] = {'last_time': time.time()}

                except Exception as e:
                    self.log_error("Error sending Telegram Notification - %s" % str(e))




    def close(self):
        """ Close input processing thread. """
        self.log_debug("Waiting for processing thread to close...")
        self.input_processing_running = False

        if self.input_thread is not None:
            self.input_thread.join()


    def running(self):
        """ Check if the logging thread is running.

        Returns:
            bool: True if the logging thread is running.
        """
        return self.input_processing_running


    def log_debug(self, line):
        """ Helper function to log a debug message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.debug("Telegram - %s" % line)


    def log_info(self, line):
        """ Helper function to log an informational message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.info("Telegram - %s" % line)


    def log_error(self, line):
        """ Helper function to log an error message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.error("Telegram - %s" % line)


if __name__ == "__main__":
    # Test Script - Send an example telegram launch and landing detection, using the settings in station.cfg

    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)
    
    # Read in the station config, which contains the email settings.
    config = read_auto_rx_config('station.cfg', no_sdr_test=True)

    # Start up an telegram notifification object.
    _telegram_notification = TelegramNotification(
        bot_token = config['telegram_bot_token'],
        chat_id = config['telegram_chat_id'],
        landing_lat1 = -10.01,
        landing_lon1 = 10.01,
        landing_alt1 = 0,
        landing_distance1 = 10000,
        landing_altitude1 = 5000,
        timeout = 10,
    )

    # Wait a second..
    time.sleep(1)

    # Add in a packet of telemetry, which will cause the email notifier to send an email.
    _telegram_notification.add({'id':'R1234567', 'frame':10, 'lat':-10.0, 'lon':10.0, 'alt':4999, 'temp':1.0, 'type':'RS41', 'freq':'401.520 MHz', 'freq_float':401.52, 'heading':0.0, 'vel_h':5.1, 'vel_v':-5.0, 'datetime_dt':datetime.datetime.utcnow()})

    # Wait a little bit before shutting down.
    time.sleep(20)
    _telegram_notification.close()


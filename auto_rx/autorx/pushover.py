#!/usr/bin/env python
#
#   radiosonde_auto_rx - Pushover Notification
#
#   Based on email_notification.py Copyright (C) 2018 Philip Heron <phil@sanslogic.co.uk>
#   Released under GNU GPL v3 or later

import logging
import time
import socket
import httplib, urllib

from threading import Thread
from autorx.utils import position_info

try:
    # Python 2
    from Queue import Queue

except ImportError:
    # Python 3
    from queue import Queue


class PushoverNotification(object):
    """ Radiosonde Pushover Notification Class.

    Accepts telemetry dictionaries from a decoder, and sends a Pushover Notification on newly detected sondes.
    Incoming telemetry is processed via a queue, so this object should be thread safe.

    """

    # We require the following fields to be present in the input telemetry dict.
    REQUIRED_FIELDS = [ 'id', 'lat', 'lon', 'alt', 'type', 'freq']

    def __init__(self,  app_token = "undefined", user_key = "undefined", landing_lat1 = 0.0, landing_lon1 = 0.0, landing_alt1 = 0.0, landing_distance1 = 5.0, landing_altitude1 = 5.0):
        """ Init a new Pushover Notification Thread """
        self.app_token = app_token
        self.user_key = user_key
        self.landing_lat1 = landing_lat1
        self.landing_lon1 = landing_lon1
        self.landing_alt1 = landing_alt1
        self.landing_distance1 = landing_distance1
        self.landing_altitude1 = landing_altitude1
        
        # Dictionary to track sonde IDs
        self.sondes = {}
        self.sondes_landing = {}

        # Input Queue.
        self.input_queue = Queue()

        # Start queue processing thread.
        self.input_processing_running = True
        self.input_thread = Thread(target = self.process_queue)
        self.input_thread.start()

        self.log_info("Started Pushover Notifier Thread")

    # Uncomment the next line to check Pushover configuration
    # self.log_info("Started Pushover Notifier Thread AT: %s UK: %s" % (self.app_token,self.user_key))

    def add(self, telemetry):
        """ Add a telemetery dictionary to the input queue. """
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
                msg += 'http://%s:5000\n' % IPAddr
                msg += '\n'
                msg += 'https://sondehub.org/%s\n' % _id

                conn = httplib.HTTPSConnection("api.pushover.net:443")
                conn.request("POST", "/1/messages.json",
                    urllib.urlencode({
                    "token": self.app_token,
                    "user": self.user_key,
                    "message": msg,
                    }), { "Content-type": "application/x-www-form-urlencoded" })
                conn.getresponse()

                self.log_info("Pushover Notification sent.")
                
            except Exception as e:
                self.log_error("Error sending Pushover Notification - %s" % str(e))

        self.sondes[_id] = { 'last_time': time.time() }

        if _id not in self.sondes_landing :
            try:
                # This is an existing sonde.  Send a single notification if it is falling
                # and is within the range specified.

                if self.landing_lat1 != 0.0 and self.landing_lon1 != 0.0:

                    # Calculate the distance from the desired position to the payload.
                    _listener = (self.landing_lat1, self.landing_lon1, self.landing_alt1)
                    _payload = (telemetry['lat'], telemetry['lon'], telemetry['alt'])

                    # Calculate using positon_info function from rotator_utils.py
                    _info = position_info(_listener, _payload)

                    if (_info['straight_distance'] < self.landing_distance1 * 1000) and (telemetry['alt'] < self.landing_altitude1 * 1000) and (telemetry['vel_h'] < 0):

                        #self.log_info("Sonde falling:  %dm, %dm, %dkm/h" % )

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
                        msg += 'http://%s:5000\n' % IPAddr
                        msg += '\n'
                        msg += 'https://sondehub.org/%s\n' % _id

                        conn = httplib.HTTPSConnection("api.pushover.net:443")
                        conn.request("POST", "/1/messages.json",
                            urllib.urlencode({
                            "token": self.app_token,
                            "user": self.user_key,
                            "message": msg,
                            }), {"Content-type": "application/x-www-form-urlencoded"})
                        conn.getresponse()

                        self.log_info("Pushover Notification sent.")
                        self.sondes_landing[_id] = {'last_time': time.time()}

            except Exception as e:
                self.log_error("Error sending Pushover Notification - %s" % str(e))





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
        logging.debug("Pushover - %s" % line)


    def log_info(self, line):
        """ Helper function to log an informational message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.info("Pushover - %s" % line)


    def log_error(self, line):
        """ Helper function to log an error message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.error("Pushover - %s" % line)


if __name__ == "__main__":
    # Test Script
    pass


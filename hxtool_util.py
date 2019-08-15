#!/usr/bin/env python
# -*- coding: utf-8 -*-

from functools import wraps
import os
import uuid
import threading
import datetime
import re
import colorsys
import logging
import traceback

try:
	from flask import request, session, redirect, url_for
except ImportError:
	print("hxtool requires the 'Flask' module, please install it.")
	exit(1)

# pycryptodome imports
try:
	from Crypto.Cipher import AES
	from Crypto.Protocol.KDF import PBKDF2
	from Crypto.Hash import HMAC, SHA256
except ImportError:
	print("hxtool requires the 'pycryptodome' module, please install it.")
	exit(1)

import hxtool_global	
from hx_lib import *

def get_N_HexCol(N=5):
	HSV_tuples = [(x * 1.0 / N, 0.7, 0.7) for x in range(N)]
	hex_out = []
	for rgb in HSV_tuples:
		rgb = map(lambda x: int(x * 255), colorsys.hsv_to_rgb(*rgb))
		hex_out.append('#%02x%02x%02x' % tuple(rgb))
	return hex_out

def valid_session_required(f):
	@wraps(f)
	def is_session_valid(*args, **kwargs):
		ret = redirect(url_for('login', redirect_uri = request.full_path))	
		if (session and 'ht_user' in session and 'ht_api_object' in session):
			o = HXAPI.deserialize(session['ht_api_object'])
			h = hash(o)
			if o.restIsSessionValid():
				kwargs['hx_api_object'] = o
				ret = f(*args, **kwargs)
				session['ht_api_object'] = o.serialize()
				return ret	
			else:
				hxtool_global.get_logger().warn("The HX API token for the current session has expired, redirecting to the login page.")
		return ret
	return is_session_valid
	
def validate_json(keys, j):
	for k in keys:
		if not k in j or not j[k]:
			return False	
	return True
		
def make_response_by_code(code):
	code_table = {200 : {'message' : 'OK'},
				400 : {'message' : 'Invalid request'},
				404 : {'message' : 'Object not found'}}
	return (json.dumps(code_table.get(code)), code)
	

"""
Generate a random byte string for use in encrypting the background processor credentails
"""
def crypt_generate_random(length):
	return os.urandom(length)

"""
Return a PBKDF2 HMACSHA256 digest of a salt and password
"""
def crypt_pbkdf2_hmacsha256(salt, data):
	return PBKDF2(data, salt, dkLen = 32, count = 20000, prf = lambda p, s: HMAC.new(p, s, SHA256).digest())

"""
AES-256 operation
"""
def crypt_aes(key, iv, data, decrypt = False, base64_coding = True):
	cipher = AES.new(key, AES.MODE_OFB, iv)
	if decrypt:
		if base64_coding:
			data = HXAPI.b64(data, True)
		data = cipher.decrypt(data).decode('utf-8')
		# Implement PKCS7 de-padding
		pad_length = ord(data[-1:])
		if 1 <= pad_length <= 15:
			if all(c == chr(pad_length) for c in data[-pad_length:]):
				data = data[:len(data) - pad_length:]
		return data
	else:
		# Implement PKCS7 padding
		pad_length = 16 - (len(data) % 16)
		if pad_length < 16:
			data += (chr(pad_length) * pad_length)
		data = data.encode('utf-8')			
		data = cipher.encrypt(data)
		if base64_coding:
			data = HXAPI.b64(data)
		return data
	
"""
Iter over a Requests response object
and yield the chunk
"""
def iter_chunk(r, chunk_size = 1024):
	for chunk in r.iter_content(chunk_size = chunk_size):
		yield chunk

def download_directory_base():
	# TODO: check configuration, if none, return the default
	return "bulkdownload"
		
def combine_app_path(path, *paths):
	if not os.path.isabs(path):
		return os.path.join(hxtool_global.app_instance_path, path, *paths)
	else:
		return path
		
def get_download_filename(host_name, host_id):
	return '{0}_{1}.zip'.format(host_name, host_id)

def make_download_directory(hx_host, download_id, job_type=None):
	download_directory = combine_app_path(download_directory_base(), hx_host, str(download_id))
	if job_type:
		download_directory = combine_app_path(download_directory_base(), hx_host, job_type, str(download_id))
	if not os.path.exists(download_directory):
		try:
			os.makedirs(download_directory)
		except:
			if not os.path.exists(download_directory): raise
			
	return download_directory

def secure_uuid4():
	return uuid.UUID(bytes=crypt_generate_random(16), version=4)

def format_activity_log(**kwargs):
	mystring = "ACTIVITY:"
	for key, value in kwargs.items():
		mystring += " " + key + "='" + HXAPI.compat_str(value) + "'"
	return(mystring)
	
# Workaround https://bugs.python.org/issue19377 on older Python versions		
def set_svg_mimetype():
	import mimetypes
	if not '.svg' in mimetypes.types_map:
		mimetypes.add_type('image/svg+xml', '.svg')
				
def set_time_macros(s):
	(s, n) = re.subn('--\#\{(now|\-(\d{1,5})(m|h))\}--', _time_replace, s, re.I) 
	return s, n > 0
	
def _time_replace(m):
	if m:
		now_time = datetime.datetime.utcnow()
		r = None
		
		if m.group(1).lower() == 'now':
			r = now_time
		elif m.group(3).lower() == 'm':
			r = now_time - datetime.timedelta(minutes = int(m.group(2)))
		elif m.group(3).lower() == 'h':
			r = now_time - datetime.timedelta(hours = int(m.group(2)))
		return HXAPI.hx_strftime(r)
	return None

def pretty_exceptions(e):
	return "{} in {}".format(e, traceback.format_exc())
	
class TemporaryFileLock(object):
	def __init__(self, file_path, file_name = 'lock_file'):
		self.file_name = os.path.join(file_path, file_name)
		self._stop_event = threading.Event()
		self.file_handle = None
	
	def acquire(self):
		while not self._stop_event.is_set():
			if not os.path.isfile(self.file_name):
				break
			self._stop_event.wait(1)
		self.file_handle = open(self.file_name, 'w')
		
	def release(self):
		self._stop_event.set()
		if self.file_handle:
			self.file_handle.close()
			os.remove(self.file_name)
	
	def __enter__(self):
		self.acquire()
		return self
		
	def __exit__(self, exc_type, exc_value, traceback):
		self.release()	

		
from hxtool_scheduler import *
from hxtool_task_modules import *
	
def submit_bulk_job(hx_api_object, script_xml, hostset_id = None, hosts = {}, hxtool_host_list_id = None, start_time = None, schedule = None, comment = None, download = True, task_profile = None, skip_base64 = False):
	if int(hostset_id) > 0:
		(ret, response_code, response_data) = hx_api_object.restListHostsInHostset(hostset_id)
		if ret:
			hosts = response_data['data']['entries']
	elif hxtool_host_list_id:
		pass
		
	if len(hosts) == 0:
		hxtool_global.get_logger().warn("Host list for bulk acquisition {} is empty. Bailing!".format(comment))
		return None

	bulk_download_eid = None
	task_list = []
	
	bulk_acquisition_task = hxtool_scheduler_task(session['ht_profileid'], 'Bulk Acquisition ID: pending', start_time = start_time)
	if schedule:
		bulk_acquisition_task.set_schedule(**schedule)
	
	if download:
		bulk_download_eid = hxtool_global.hxtool_db.bulkDownloadCreate(session['ht_profileid'], hostset_id = hostset_id, task_profile = task_profile)
		bulk_acquisition_hosts = {}
		_task_profile = None
		for host in hosts:
			bulk_acquisition_hosts[host['_id']] = {'downloaded' : False, 'hostname' :  host['hostname']}
			download_and_process_task = hxtool_scheduler_task(session['ht_profileid'], 
															'Bulk Acquisition Download: {}'.format(host['hostname']), 
															parent_id = bulk_acquisition_task.task_id, 
															start_time = bulk_acquisition_task.start_time,
															defer_interval = hxtool_global.hxtool_config['background_processor']['poll_interval'])
															
				
			download_and_process_task.add_step(bulk_download_task_module, kwargs = {
														'bulk_download_eid' : bulk_download_eid,
														'agent_id' : host['_id'],
														'host_name' : host['hostname']
													})

			# TODO: remove static parameter mappings for task modules
			# The bulk_acquisition_task_module passes the host_id and host_name values to these modules
			if task_profile:
				if task_profile == 'stacking':
					hxtool_global.get_logger().debug("Using stacking task module.")
					download_and_process_task.add_step(stacking_task_module, kwargs = {
																'delete_bulk_download' : True
															})
					comment = "HXTool Stacking Acquisition"										
				elif task_profile == 'file_listing':
					hxtool_global.get_logger().debug("Using file listing task module.")
					download_and_process_task.add_step(file_listing_task_module, kwargs = {
																'delete_bulk_download' : False
															})
					comment = "HXTool Multifile File Listing Acquisition"										
				else:
					if not _task_profile:
						_task_profile = hxtool_global.hxtool_db.taskProfileGet(task_profile)
						
					if _task_profile and 'params' in _task_profile:
						#TODO: once task profile page params are dynamic, remove static mappings
						for task_module_params in _task_profile['params']:						
							if task_module_params['module'] == 'ip':
								hxtool_global.get_logger().debug("Using taskmodule 'ip' with parameters: protocol {}, ip {}, port {}".format(task_module_params['protocol'], task_module_params['targetip'], task_module_params['targetport']))
								download_and_process_task.add_step(streaming_task_module, kwargs = {
																	'stream_host' : task_module_params['targetip'],
																	'stream_port' : task_module_params['targetport'],
																	'stream_protocol' : task_module_params['protocol'],
																	'batch_mode' : (task_module_params['eventmode'] != 'per-event'),
																	'delete_bulk_download' : False
																})
							elif task_module_params['module'] == 'file':
								hxtool_global.get_logger().debug("Using taskmodule 'file' with parameters: filepath {}".format(task_module_params['filepath']))
								download_and_process_task.add_step(file_write_task_module, kwargs = {
																	'file_name' : task_module_params['filepath'],
																	'batch_mode' : (task_module_params['eventmode'] != 'per-event'),
																	'delete_bulk_download' : False
																})
							elif task_module_params['module'] == 'helix':
								hxtool_global.get_logger().debug("Using taskmodule 'helix' with parameters: helix_url {}, helix_apikey: {}".format(task_module_params['helix_url'], task_module_params['helix_apikey']))
								download_and_process_task.add_step(helix_task_module, kwargs = {
																	'url' : task_module_params['helix_url'],
																	'apikey' : task_module_params['helix_apikey'],
																	'batch_mode' : (task_module_params['eventmode'] != 'per-event'),
																	'delete_bulk_download' : False
																})
							elif task_module_params['module'] == 'x15':
								hxtool_global.get_logger().debug("Using taskmodule 'x15' with parameters: x15_host: {}, x15_port: {}, x15_database: {}, x15_table: {}, x15_user: {}, x15_password: {}".format(task_module_params['x15_host'], task_module_params['x15_port'], task_module_params['x15_database'], task_module_params['x15_table'], task_module_params['x15_user'], "********"))
								task_module_args = {
									'batch_mode' : False, # Hardcode per-event as X15 might not handle large lists well
									'delete_bulk_download' : False
								}
								task_module_args.update(task_module_params)
								del task_module_args['module']
								download_and_process_task.add_step(x15_postgres_task_module, kwargs = task_module_args)
																
			task_list.append(download_and_process_task)
		
		hxtool_global.hxtool_db.bulkDownloadUpdate(bulk_download_eid, hosts = bulk_acquisition_hosts)
		
	bulk_acquisition_task.add_step(bulk_acquisition_task_module, kwargs = {
									'script' : script_xml,
									'hostset_id' : hostset_id,
									'comment' : comment,
									'skip_base64' : skip_base64,
									'download' : download,
									'bulk_download_eid' : bulk_download_eid
								})
	
	# Add the child tasks first, otherwise we end up with a nasty race condition
	hxtool_global.hxtool_scheduler.add_list(task_list)
	hxtool_global.hxtool_scheduler.add(bulk_acquisition_task)		
	
	return bulk_download_eid
	
def parse_schedule(request_params):
	start_time = None
	schedule = None
	
	schedule_type = request_params.get('schedule', None)
	if schedule_type:
		if schedule_type == "run_at":
			start_time = HXAPI.dt_from_str(request_params['run_at_value'])
		elif schedule_type == "run_interval":
			schedule = {}
			
			interval_value = int(request_params['interval_value'])
			interval_unit = request_params['interval_unit']
			
			if interval_unit == "second":
				schedule['seconds'] = interval_value
			elif interval_unit == "minute":
				schedule['minutes'] = interval_value
			elif interval_unit == "hour":
				schedule['hours'] = interval_value	
			elif interval_unit == "day":
				schedule['days'] = interval_value
			elif interval_unit == "week":
				schedule['weeks'] = interval_value
			elif interval_unit == "month":
				schedule['months'] = interval_value
				
			if request_params['interval_start'] == "interval_start_at":
				start_time = HXAPI.dt_from_str(request_params['interval_start_value'])

	return (start_time, schedule)
	
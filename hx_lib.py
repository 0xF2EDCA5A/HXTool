#!/usr/bin/env python
# -*- coding: utf-8 -*-

##########################
### HX REST functions
### Henrik Olsson @FireEye
##########################

import urllib2
import urllib
import base64
import json
import ssl
import logging
import datetime
import pickle


class HXAPI:
	HX_DEFAULT_PORT = 3000

	def __init__(self, hx_host, hx_port = HX_DEFAULT_PORT, headers = None, cookies = None, disable_certificate_verification = True, logger = logging.getLogger(__name__)):
		self.logger = logger

		self.logger.debug('__init__ start.')
		
		self.hx_host = hx_host
		self.logger.debug('hx_host set to %s.', self.hx_host)
		self.hx_port = hx_port
		self.logger.debug('hx_port set to %s.', self.hx_port)
		self.headers = {}
		if headers:
			self.logger.debug('Appending additional headers passed to __init__')
			self.headers.update(headers)
		self.cookies = {}
		if cookies:
			self.logger.debug('Appending additional cookies passed to __init__')
			self.cookies.update(cookies)
		
		if disable_certificate_verification and hasattr(ssl, '_create_unverified_context'):
			ssl._create_default_https_context = ssl._create_unverified_context
			self.logger.info('SSL/TLS certificate verification disabled.')
		
		self.fe_token = None
		
		self.logger.debug('__init__ complete.')
		
	def serialize(self):
		return base64.b64encode(pickle.dumps(self, pickle.HIGHEST_PROTOCOL))
	
	# Mmmm, base64 flavored pickles...
	@staticmethod
	def deserialize(base64_pickle):
		return pickle.loads(base64.b64decode(base64_pickle))
	
	# Loggers don't pickle nicely	
	def __getstate__(self):
		d = self.__dict__.copy()
		if 'logger' in d.keys():
			d['logger'] = d['logger'].name
		return d

	def __setstate__(self, d):
		if 'logger' in d.keys():
			d['logger'] = logging.getLogger(d['logger'])
		self.__dict__.update(d)	

	###################
	## Generic functions
	###################

	def build_request(self, url, method = 'GET', data = None, content_type = 'application/json', accept = 'application/json'):
	
		full_url = "https://{0}:{1}{2}".format(self.hx_host, self.hx_port, url)
		self.logger.debug('Full URL is: %s', full_url)
		
		if len(self.headers) > 0:
			request = urllib2.Request(full_url, data = data, headers = self.headers)
			self.logger.debug('Creating request with additional headers.')
		else:
			request = urllib2.Request(full_url, data = data)
			self.logger.debug('Creating request without additional headers.')
		
		request.get_method = lambda: method
		self.logger.debug('HTTP method set to: %s', request.get_method)
		request.add_header('Accept', accept)
		self.logger.debug('Accept header set to: %s', accept)
		request.add_header('User-Agent', 'HXTool/2.0')
		if method != 'GET' and method != 'DELETE':
			self.logger.debug('HTTP method is not GET or DELETE, Content-Type header set to: %s', content_type)
			request.add_header('Content-Type', content_type)
		if self.fe_token:
			self.logger.debug('We have a token, appending it to the request.')
			request.add_header('X-FeApi-Token', self.get_token()['token'])
		for header in self.headers:
			self.logger.debug('Appending additional headers to request.')
			request.add_header(header[0], header[1])
		if len(self.cookies) > 0:
			self.logger.debug('Appending additional cookies to request.')
			request.add_header('Cookie', ';'.join('='.join(_) for _ in self.cookies.items()) + ';')
		
		self.logger.debug('Request created, returning.')
		return request

	def handle_response(self, request, expect_multiple_json_objects = False):
		
		has_http_error = False

		try:
			response = urllib2.urlopen(request)
		except urllib2.HTTPError as e:
			self.logger.debug('HTTPError occured. Status code: %s, reason: %s', e.code, e.reason)
			response = e
			has_http_error = True		
		except urllib2.URLError as e:
			self.logger.debug('URLError occured. Reason: %s', e.reason)
			return(False, None, e.reason, None)
		
		response_data = response.read() 
		
		content_type = response.info().getheader('Content-Type')
		if content_type:
			if 'json' in content_type:
				response_data = response_data.decode(response.info().getheader('charset') or 'utf-8')
				if expect_multiple_json_objects:
					response_data = [json.loads(_) for _ in response_data.splitlines() if _.startswith('{')]
				else:
					response_data = json.loads(response_data)
			elif 'text' in content_type:
				response_data = response_data.decode(response.info().getheader('charset') or 'utf-8')
				
		return(not has_http_error, response.code, response_data, response.info())

	def set_token(self, token):
		self.logger.debug('set_token called')
		
		timestamp = str(datetime.datetime.utcnow())
		if token:
			self.fe_token = {'token' : token, 'grant_timestamp' : timestamp, 'last_use_timestamp' : timestamp}
		else:
			self.fe_token = None
		
	def get_token(self, update_last_use_timestamp = True):
		self.logger.debug('get_token called, update_last_use_timestamp=%s', update_last_use_timestamp)
		
		if not self.fe_token:
			self.logger.debug('fe_token is empty.')
		elif update_last_use_timestamp:
			self.fe_token['last_use_timestamp'] = str(datetime.datetime.utcnow())

		return(self.fe_token)
			
	###################
	## Generic GET
	###################
	def restGetUrl(self, url):

		request = self.build_request(url)
		(ret, response_code, response_data, response_headers) = handle_response(request)
		
		return(ret, response_code, response_data)

	###################
	## Authentication
	###################

	# Authenticate and return X-FeApi-Token
	# A response code of 204 means that the
	# authentication request was sucessful.
	# A response code of 401 means that the
	# authentication request failed.
	# See page 47 in the API guide
	def restLogin(self, hx_user, hx_password):
	
		request = self.build_request('/hx/api/v1/token')
		request.add_header('Authorization', 'Basic {0}'.format(base64.b64encode('{0}:{1}'.format(hx_user, hx_password))))

		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		if ret and response_code == 204:
			self.set_token(response_headers.getheader('X-FeApi-Token'))
		
		return(ret, response_code, response_data)

	# Logout
	# 204 = Success
	# 304 = Failed due to missing API token
	# See page 746 of the API guide
	def restLogout(self):

		request = self.build_request('/hx/api/v1/token', method = 'DELETE')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		self.logger.debug('Setting token to None.')
		self.set_token(None)
		
		return(ret, response_code, response_data)
		
	# Session expire after 15 minutes of inactivity
	# or 2.5 hours, whichever comes first.
	# See page 47 of the API guide
	def restIsSessionValid(self):
		
		current_token = self.get_token(update_last_use_timestamp=False)
		if current_token:
			last_use_delta = (datetime.datetime.utcnow() - datetime.strptime(current_token['last_use_timestamp'], '%Y-%m-%d %H:%M:%S.%f')).seconds / 60
			grant_time_delta = (datetime.datetime.utcnow() - datetime.strptime(current_token['grant_timestamp'], '%Y-%m-%d %H:%M:%S.%f')).seconds / 60
			return(last_use_delta < 15 and grant_time_delta < 150) 
		else:
			return(False)
			
			
	def restGetVersion(self):

		request = self.build_request('/hx/api/v2/version')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	################
	## Resolve hosts
	################

	def restFindHostbyString(self, string):

		request = self.build_request('/hx/api/v1/hosts?search={0}'.format(urllib.urlencode(string)))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

			


	## Indicators
	#############

	# List indicator categories
	def restListIndicatorCategories(self):

		request = self.build_request('/hx/api/v1/indicator_categories')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# List all IOCs
	def restListIndicators(self, limit=10000):

		request = self.build_request('/hx/api/v3/indicators?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	# Add a new condition
	def restAddCondition(self, ioc_category, ioc_guid, condition_class, condition_data):

		request = self.build_request('/hx/api/v1/indicators/{0}/{1}/conditions/{2}'.format(ioc_category, ioc_guid, condition_class), method = 'POST', data = condition_data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Add a new indicator
	def restAddIndicator(self, create_user, display_name, platforms, ioc_category):

		data = json.dumps({"create_text" : create_user, "display_name" : display_name, "platforms" : platforms})
		
		request = self.build_request('/hx/api/v3/indicators/{0}'.format(ioc_category), method = 'POST', data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Submit a new category
	def restCreateCategory(self, category_name):

		request = self.build_request('/hx/api/v1/indicator_categories/{0}'.format(category_name), method = 'PUT', data = '{}')
		request.add_header('If-None-Match', '*')
		
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Grab conditions from an indicator
	def restGetCondition(self, ioc_category, ioc_uri, condition_class, limit=10000):

		request = self.build_request('/hx/api/v1/indicators/{0}/{1}/conditions/{2}?limit={3}'.format(ioc_category, ioc_uri, condition_class, limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# List all indicators
	def restListIndicators(self, limit=10000):

		request = self.build_request('/hx/api/v3/indicators?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Get indicator based on condition
	def restGetIndicatorFromCondition(self, condition_id):

		request = self.build_request('/hx/api/v2/conditions/{0}/indicators'.format(condition_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Delete an indicator by name
	def restDeleteIndicator(self, ioc_category, ioc_name):
		
		request = self.build_request('/hx/api/v3/indicators/{0}/{1}'.format(ioc_category, ioc_name), method = 'DELETE')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	## Acquisitions
	###############

	# Acquire triage
	def restAcquireTriage(self, agent_id, timestamp = False):

		data = '{}'
		if timestamp:
			data = json.dumps({'req_timestamp' : timestamp})

		request = self.build_request('/hx/api/v1/hosts/{0}/triages'.format(agent_id), data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# Acquire file
	def restAcquireFile(self, agent_id, path, filename, mode):

		newpath = path.replace('\\','\\\\')
		data = json.dumps({'req_path' : newpath, 'req_filename' : filename, 'req_use_api' : str(mode != "RAW").lower()})
		
		request = self.build_request('/hx/api/v1/hosts/{0}/files'.format(agent_id), method = 'POST', data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
		
	# List Bulk Acquisitions
	def restListBulkAcquisitions(self, limit=1000):

		request = self.build_request('/hx/api/v2/acqs/bulk?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	# List hosts in Bulk acquisition
	def restListBulkDetails(self, bulk_id, limit=10000):

		request = self.build_request('/hx/api/v2/acqs/bulk/{0}/hosts?limit={1}'.format(bulk_id, limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	# Get Bulk acquistion detail
	def restGetBulkDetails(self, bulk_id):

		request = self.build_request('/hx/api/v2/acqs/bulk/{0}'.format(bulk_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	# Download bulk data
	def restDownloadBulkAcq(self, url):

		request = self.build_request(url, accept = 'application/octet-stream')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# New Bulk acquisition

	def restNewBulkAcq(self, script, host_set):

		data = json.dumps({'host_set' : {'_id' : int(host_set)}, 'script' : {'b64' : base64.b64encode(script)}})
		
		request = self.build_request('/hx/api/v2/acqs/bulk', method = 'POST', data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# List normal acquisitions
	def restListAcquisitions(self):

		request = self.build_request('/hx/api/v2/acqs')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
		
	# List file acquisitions
	def restListFileaq(self, limit=10000):

		request = self.build_request('/hx/api/v2/acqs/files?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restListTriages(self, limit=10000):

		request = self.build_request('/hx/api/v2/acqs/triages?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	#######################
	## Enterprise Search ##
	#######################

	def restListSearches(self):

		request = self.build_request('/hx/api/v2/searches')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	def restSubmitSweep(self, b64ioc, host_set):

		data = json.dumps({'indicator' : b64ioc, 'host_set' : {'_id' : int(host_set)}})
		
		request = self.build_request('/hx/api/v2/searches', method = 'POST', data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restCancelJob(self, path, id):

		request = self.build_request('{0}{2}/actions/stop'.format(path, id), method = 'POST')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restDeleteJob(self, path, id):

		request = self.build_request('{0}{1}'.format(path, id), method = 'DELETE')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
		
	def restGetSearchHosts(self, search_id):

		request = self.build_request('/hx/api/v2/searches/{0}/hosts?errors=true'.format(search_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restGetSearchResults(self, search_id):

		request = self.build_request('/hx/api/v3/searches/{0}/results'.format(search_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	##########
	# Alerts #
	##########

	def restGetAlertID(self, alert_id):

		request = self.build_request('/hx/api/v3/alerts/{0}'.format(alert_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restGetAlerts(self, limit):

		request = self.build_request('/hx/api/v3/alerts?sort=reported_at+desc&limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	# NOTE: this function does not return data in the usual way, the response is a list of alerts
	def restGetAlertsTime(self, start_date, end_date):

		data = json.dumps({'event_at' : 
							{'min' : '{0}T00:00:00.000Z'.format(start_date), 
							'max' : '{0}T23:59:59.999Z'.format(end_date)}
						})
							
		request = self.build_request('/hx/api/v3/alerts/filter', method = 'POST', data = data)
		
		(ret, response_code, response_data, response_headers) = self.handle_response(request, expect_multiple_json_objects = True)
		
		if ret:
			from operator import itemgetter
			sorted_alert_list = sorted(response_data, key=itemgetter('reported_at'), reverse=True);
			return(True, response_code, sorted_alert_list)
		
		else:
			return(ret, response_code, response_data)
			


	##############
	# Query host
	##############

	def restGetHostSummary(self, host_id):

		request = self.build_request('/hx/api/v2/hosts/{0}'.format(host_id))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)



	########
	# Hosts
	########

	def restListHosts(self, limit=100000):

		request = self.build_request('/hx/api/v2/hosts?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)


	def restListHostsets(self, limit=100000):

		request = self.build_request('/hx/api/v2/host_sets?limit=100000'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)

	def restCheckAccessCustomConfig(self, limit=1):

		request = self.build_request('/hx/api/v3/host_policies/channels?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
			
	def restListCustomConfigChannels(self, limit=1000):

		request = self.build_request('/hx/api/v3/host_policies/channels?limit={0}'.format(limit))
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
	
	def restNewConfigChannel(self, name, description, priority, host_sets, conf):

		myhostsets = []
		for hs in host_sets:
			myhostsets.append({"_id": int(hs)})
		
		try:
			myconf = json.loads(conf)
		except ValueError:
			print "Failed to parse incoming json"
			print conf
		
		data = json.dumps({'name' : name, 'description' : description, 'priority' : int(priority), 'host_sets' : myhostsets, 'configuration' : myconf})
		
		request = self.build_request('/hx/api/v3/host_policies/channels', method = 'POST', data = data)
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
	
	def restDeleteConfigChannel(self, channel_id):

		request = self.build_request('/hx/api/v3/host_policies/channels/{0}'.format(channel_id), method = 'DELETE')
		(ret, response_code, response_data, response_headers) = self.handle_response(request)
		
		return(ret, response_code, response_data)
		
			
	####
	# Generic functions
	####
	@staticmethod
	def prettyTime(time=False):
		
		from datetime import datetime

		now = datetime.utcnow()
		if type(time) is int:
			diff = now - datetime.fromtimestamp(time)
		elif isinstance(time,datetime):
			diff = now - time
		elif not time:
			diff = now - now

		second_diff = diff.seconds
		day_diff = diff.days

		if day_diff < 0:
			return ''

		if day_diff == 0:
			if second_diff < 10:
				return "just now"
			if second_diff < 60:
				return str(second_diff) + " seconds ago"
			if second_diff < 120:
				return "a minute ago"
			if second_diff < 3600:
				return str(second_diff / 60) + " minutes ago"
			if second_diff < 7200:
				return "an hour ago"
			if second_diff < 86400:
				return str(second_diff / 3600) + " hours ago"
		if day_diff == 1:
			return "Yesterday"
		if day_diff < 7:
			return str(day_diff) + " days ago"
		if day_diff < 31:
			return str(day_diff / 7) + " weeks ago"
		if day_diff < 365:
			return str(day_diff / 30) + " months ago"
		
		return str(day_diff / 365) + " years ago"

	@staticmethod	
	def gt(dt_str):
		
		dt, _, us= dt_str.partition(".")
		dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
		us = int(us.rstrip("Z"), 10)
		return dt + datetime.timedelta(microseconds=us)

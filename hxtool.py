#!/usr/bin/env python
# -*- coding: utf-8 -*-

##################################################
# hxTool - 3rd party user-interface for FireEye HX 
#
# Henrik Olsson
# henrik.olsson@fireeye.com
#
# For license information see the 'LICENSE' file
##################################################

# Core python imports
import base64
import sys
import logging
import json
import io
import os
import datetime
import time
import signal
import xml.etree.ElementTree as ET
from string import Template
from xml.sax.saxutils import escape as xmlescape
import re
from io import BytesIO

# Flask imports
try:
	from flask import Flask, request, Response, session, redirect, render_template, send_file, g, url_for, abort, Blueprint
	from jinja2 import evalcontextfilter, Markup, escape
except ImportError:
	print("hxtool requires the 'Flask' module, please install it.")
	exit(1)
	
# hx_tool imports
import hxtool_global
from hx_lib import *
from hxtool_util import *
from hxtool_formatting import *
from hxtool_db import *
from hxtool_config import *
from hxtool_data_models import *
from hxtool_session import *
from hxtool_scheduler import *
from hxtool_task_modules import *

# Import HXTool API Flask blueprint
from hxtool_api import ht_api

app = Flask(hxtool_global.root_logger_name, static_url_path='/static')

# Register HXTool API blueprint
app.register_blueprint(ht_api)

HXTOOL_API_VERSION = 1
default_encoding = 'utf-8'

### Flask/Jinja Filters
####################################

_newline_re = re.compile(r'(?:\r\n|\r|\n){1,}')
@app.template_filter()
@evalcontextfilter
def nl2br(eval_ctx, value):
	result = '<br />\n'.join(escape(p) for p in _newline_re.split(value or ''))
	if eval_ctx.autoescape:
		result = Markup(result)
	return result

### Dashboard page
@app.route('/', methods=['GET'])
@valid_session_required
def dashboard(hx_api_object):
	return render_template('ht_main-dashboard.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### AV Dashboard
@app.route('/dashboard-av', methods=['GET'])
@valid_session_required
def dashboardav(hx_api_object):
	return render_template('ht_dashboard-av.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### New host drilldown page
@app.route('/hostview', methods=['GET'])
@valid_session_required
def host_view(hx_api_object):
	myscripts = app.hxtool_db.scriptList()
	scripts = formatScriptsFabric(myscripts)

	mytaskprofiles = app.hxtool_db.taskProfileList()
	taskprofiles = formatTaskprofilesFabric(mytaskprofiles)

	return render_template('ht_host_view.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), scripts=scripts, taskprofiles=taskprofiles)

### Alerts page
@app.route('/alert', methods=['GET'])
@valid_session_required
def alert(hx_api_object):
	return render_template('ht_alert.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Scheduler page
@app.route('/scheduler', methods=['GET'])
@valid_session_required
def scheduler_view(hx_api_object):
	return render_template('ht_scheduler.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Script builder page
@app.route('/scriptbuilder', methods=['GET', 'POST'])
@valid_session_required
def scriptbuilder_view(hx_api_object):
	myauditspacefile = open(combine_app_path('static/acquisitions.json'), 'r')
	auditspace = myauditspacefile.read()
	myauditspacefile.close()
	return render_template('ht_scriptbuilder.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), auditspace=auditspace)

### Task profile page
@app.route('/taskprofile', methods=['GET', 'POST'])
@valid_session_required
def taskprofile(hx_api_object):
	return render_template('ht_taskprofile.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Bulk acq page
@app.route('/bulkacq', methods=['GET'])
@valid_session_required
def bulkacq_view(hx_api_object):
	(ret, response_code, response_data) = hx_api_object.restListHostsets()
	hostsets = formatHostsetsFabric(response_data)

	myscripts = app.hxtool_db.scriptList()
	scripts = formatScriptsFabric(myscripts)

	mytaskprofiles = app.hxtool_db.taskProfileList()
	taskprofiles = formatTaskprofilesFabric(mytaskprofiles)

	return render_template('ht_bulkacq.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), hostsets=hostsets, scripts=scripts, taskprofiles=taskprofiles)

### Hosts
@app.route('/hostsearch', methods=['GET', 'POST'])
@valid_session_required
def hosts(hx_api_object):
	return render_template('ht_hostsearch.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Acquisitions listing
@app.route('/acqs', methods=['GET'])
@valid_session_required
def acqs(hx_api_object):
	return render_template('ht_acqs.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

#### Enterprise Search
@app.route('/search', methods=['GET'])
@valid_session_required
def search(hx_api_object):	
	(ret, response_code, response_data) = hx_api_object.restListHostsets()
	hostsets = formatHostsetsFabric(response_data)

	myiocs = app.hxtool_db.oiocList()
	openiocs = formatOpenIocsFabric(myiocs)
	
	return render_template('ht_searchsweep.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), hostsets=hostsets, openiocs=openiocs)

@app.route('/searchresult', methods=['GET'])
@valid_session_required
def searchresult(hx_api_object):
	if request.args.get('id'):
		(ret, response_code, response_data) = hx_api_object.restGetSearchResults(request.args.get('id'))
		return render_template('ht_search_dd.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))
			
### Manage Indicators
@app.route('/indicators', methods=['GET', 'POST'])
@valid_session_required
def indicators(hx_api_object):
	return render_template('ht_indicators.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

@app.route('/categories', methods=['GET'])
@valid_session_required
def categories(hx_api_object):
	return render_template('ht_categories.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Real-time indicators
@app.route('/rtioc', methods=['GET'])
@valid_session_required
def rtioc(hx_api_object):
			
	myEventFile = open(combine_app_path('static/eventbuffer.json'), 'r')
	eventspace = myEventFile.read()
	myEventFile.close()

	if request.args.get('indicator'):

		uuid = request.args.get('indicator')

		(ret, response_code, response_data) = hx_api_object.restListCategories()
		categories = formatCategoriesSelect(response_data)

		(ret, response_code, response_data) = hx_api_object.restListIndicators(limit=1, filter_term={ 'uri_name': uuid })
		if ret:
			iocname = response_data['data']['entries'][0]['name']
			myiocuri = response_data['data']['entries'][0]['uri_name']
			ioccategory = response_data['data']['entries'][0]['category']['uri_name']
			mydescription = response_data['data']['entries'][0]['description']
			if len(response_data['data']['entries'][0]['platforms']) == 1:
				platform = response_data['data']['entries'][0]['platforms'][0]
			else:
				platform = "all"

			(ret, response_code, condition_class_presence) = hx_api_object.restGetCondition(ioccategory, uuid, 'presence')
			(ret, response_code, condition_class_execution) = hx_api_object.restGetCondition(ioccategory, uuid, 'execution')

			mypre = json.dumps(condition_class_presence['data']['entries'])
			myexec = json.dumps(condition_class_execution['data']['entries'])

			if request.args.get('clone'):
				ioccategory = "Custom"

		return render_template('ht_indicator_create_edit.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), categories=categories, iocname=iocname, myiocuri=myiocuri, myioccategory=ioccategory, mydescription=mydescription, ioccategory=json.dumps(ioccategory), platform=json.dumps(platform), mypre=mypre, myexec=myexec, eventspace=eventspace)
	else:
		(ret, response_code, response_data) = hx_api_object.restListCategories()
		categories = formatCategoriesSelect(response_data)
		return render_template('ht_indicator_create_edit.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), categories=categories, eventspace=eventspace)


# TODO: These two functions should be merged at some point
@app.route('/bulkdownload', methods = ['GET'])
@valid_session_required
def bulkdownload(hx_api_object):
	if request.args.get('id'):
		(ret, response_code, response_data) = hx_api_object.restDownloadFile(request.args.get('id'))
		if ret:
			#app.logger.info('Bulk acquisition download - User: %s@%s:%s', session['ht_user'], hx_api_object.hx_host, hx_api_object.hx_port)
			#app.logger.info('Acquisition download - User: %s@%s:%s - URL: %s', session['ht_user'], hx_api_object.hx_host, hx_api_object.hx_port, request.args.get('id'))
			app.logger.info(format_activity_log(msg="bulk acquisition download", id=request.args.get('id'), user=session['ht_user'], controller=session['hx_ip']))
			flask_response = Response(iter_chunk(response_data))
			flask_response.headers['Content-Type'] = response_data.headers['Content-Type']
			flask_response.headers['Content-Disposition'] = response_data.headers['Content-Disposition']
			return flask_response
		else:
			return "HX controller responded with code {0}: {1}".format(response_code, response_data)
	else:
		abort(404)

		
@app.route('/download')
@valid_session_required
def download(hx_api_object):
	if request.args.get('id'):
		if request.args.get('content') == "json":
			(ret, response_code, response_data) = hx_api_object.restDownloadFile(request.args.get('id'), accept = "application/json")
		else:
			(ret, response_code, response_data) = hx_api_object.restDownloadFile(request.args.get('id'))
		if ret:
			#app.logger.info('Acquisition download - User: %s@%s:%s - URL: %s', session['ht_user'], hx_api_object.hx_host, hx_api_object.hx_port, request.args.get('id'))
			print(response_data.headers)
			app.logger.info(format_activity_log(msg="acquisition download", id=request.args.get('id'), user=session['ht_user'], controller=session['hx_ip']))
			flask_response = Response(iter_chunk(response_data))
			flask_response.headers['Content-Type'] = response_data.headers['Content-Type']
			flask_response.headers['Content-Disposition'] = response_data.headers['Content-Disposition']
			return flask_response
		else:
			return "HX controller responded with code {0}: {1}".format(response_code, response_data)
	else:
		abort(404)		

@app.route('/download_file')
@valid_session_required
def download_multi_file_single(hx_api_object):
	if 'mf_id' in request.args and 'acq_id' in request.args:
		multi_file = app.hxtool_db.multiFileGetById(request.args.get('mf_id'))
		if multi_file:
			file_records = list(filter(lambda f: int(f['acquisition_id']) == int(request.args.get('acq_id')), multi_file['files']))
			if file_records and file_records[0]:
				# TODO: should multi_file be hardcoded?
				path = combine_app_path(download_directory_base(), hx_api_object.hx_host, 'multi_file', request.args.get('mf_id'), '{}_{}.zip'.format(file_records[0]['hostname'], request.args.get('acq_id')))
				#app.logger.info('Acquisition download - User: %s@%s:%s - URL: %s', session['ht_user'], hx_api_object.hx_host, hx_api_object.hx_port, request.args.get('acq_id'))
				app.logger.info(format_activity_log(msg="multi-file acquisition download", id=request.args.get('acq_id'), user=session['ht_user'], controller=session['hx_ip']))
				return send_file(path, attachment_filename=os.path.basename(path), as_attachment=True)
		else:
			return "HX controller responded with code {0}: {1}".format(response_code, response_data)
	abort(404)		

### Scripts
@app.route('/scripts', methods=['GET'])
@valid_session_required
def scripts(hx_api_object):
	return render_template('ht_scripts.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### OpenIOCs
@app.route('/openioc', methods=['GET'])
@valid_session_required
def openioc(hx_api_object):
	return render_template('ht_openioc.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Multifile acquisitions
@app.route('/multifile', methods=['GET'])
@valid_session_required
def multifile(hx_api_object):
	(ret, response_code, response_data) = hx_api_object.restListHostsets()
	hostsets = formatHostsets(response_data)
	return render_template('ht_multifile.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), hostsets=hostsets)

@app.route('/file_listing', methods=['GET'])
@valid_session_required
def file_listing(hx_api_object):
	#TODO: Modify template and move to Ajax
	fl_id = request.args.get('id')
	file_listing = app.hxtool_db.fileListingGetById(fl_id)
	fl_results = file_listing['files']
	display_fields = ['FullPath', 'Username', 'SizeInBytes', 'Modified', 'Sha256sum'] 
	return render_template('ht_file_listing.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), file_listing=file_listing, fl_results=fl_results, display_fields=display_fields)

### Stacking
@app.route('/stacking', methods=['GET'])
@valid_session_required
def stacking(hx_api_object):
	return render_template('ht_stacking.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

@app.route('/stackinganalyze', methods=['GET'])
@valid_session_required
def stackinganalyze(hx_api_object):
	return render_template('ht_stacking_analyze.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

@app.route('/sysinfo', methods=['GET'])
@valid_session_required
def sysinfo(hx_api_object):
	return render_template('ht_sysinfo.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))

### Settings
@app.route('/settings', methods=['GET', 'POST'])
@valid_session_required
def settings(hx_api_object):
	if request.method == 'POST':
		# Generate a new IV - must be 16 bytes
		iv = crypt_generate_random(16)
		salt = crypt_generate_random(32)
		key = crypt_pbkdf2_hmacsha256(salt, app.task_api_key)
		encrypted_password = crypt_aes(key, iv, request.form['bgpass'])
		out = app.hxtool_db.backgroundProcessorCredentialCreate(session['ht_profileid'], request.form['bguser'], HXAPI.b64(iv), HXAPI.b64(salt), encrypted_password)
		app.logger.info(format_activity_log(msg="background processing credentials action", action="set", profile=session['ht_profileid'], user=session['ht_user'], controller=session['hx_ip']))
		hxtool_global.task_hx_api_sessions[session['ht_profileid']] = HXAPI(hx_api_object.hx_host, 
																			hx_port = hx_api_object.hx_port, 
																			proxies = app.hxtool_config['network'].get('proxies'), 
																			headers = app.hxtool_config['headers'], 
																			cookies = app.hxtool_config['cookies'], 
																			logger_name = hxtool_global.get_submodule_logger_name(HXAPI.__name__), 
																			default_encoding = default_encoding)																
		(ret, response_code, response_data) = hxtool_global.task_hx_api_sessions[session['ht_profileid']].restLogin(request.form['bguser'], request.form['bgpass'], auto_renew_token = True)
		if ret:
			app.logger.info("Successfully initialized task API session for profile {}".format(session['ht_profileid']))
		else:
			app.logger.error("Failed to initialized task API session for profile {}".format(session['ht_profileid']))
	if request.args.get('unset'):
		out = app.hxtool_db.backgroundProcessorCredentialRemove(session['ht_profileid'])
		hx_api_object = hxtool_global.task_hx_api_sessions.get(session['ht_profileid'])
		if hx_api_object and hx_api_object.restIsSessionValid():
			(ret, response_code, response_data) = hx_api_object.restLogout()
			del hxtool_global.task_hx_api_sessions[session['ht_profileid']]
		app.logger.info(format_activity_log(msg="background processing credentials action", action="delete", user=session['ht_user'], controller=session['hx_ip']))
		return redirect("/settings", code=302)
	
	bgcreds = formatProfCredsInfo((app.hxtool_db.backgroundProcessorCredentialGet(session['ht_profileid']) is not None))
	
	return render_template('ht_settings.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), bgcreds=bgcreds)


### Custom Configuration Channels
@app.route('/channels', methods=['GET'])
@valid_session_required
def channels(hx_api_object):
	(ret, response_code, response_data) = hx_api_object.restListCustomConfigChannels(limit=1)
	if ret:
		(ret, response_code, response_data) = hx_api_object.restListHostsets()
		hostsets = formatHostsets(response_data)
		
		return render_template('ht_configchannel.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port), hostsets=hostsets)
	else:
		return render_template('ht_noaccess.html', user=session['ht_user'], controller='{0}:{1}'.format(hx_api_object.hx_host, hx_api_object.hx_port))
		

#### Authentication
@app.route('/login', methods=['GET', 'POST'])
def login():
	if (request.method == 'POST'):
		if 'ht_user' in request.form:
			ht_profile = app.hxtool_db.profileGet(request.form['controllerProfileDropdown'])
			if ht_profile:	

				hx_api_object = HXAPI(ht_profile['hx_host'], 
									hx_port = ht_profile['hx_port'], 
									proxies = app.hxtool_config['network'].get('proxies'), 
									headers = app.hxtool_config['headers'], 
									cookies = app.hxtool_config['cookies'], 
									logger_name = hxtool_global.get_submodule_logger_name(HXAPI.__name__), 
									default_encoding = default_encoding)

				(ret, response_code, response_data) = hx_api_object.restLogin(request.form['ht_user'], request.form['ht_pass'], auto_renew_token = True)
				if ret:
					# Set session variables
					session['ht_user'] = request.form['ht_user']
					session['ht_profileid'] = ht_profile['profile_id']
					session['ht_api_object'] = hx_api_object.serialize()
					session['hx_version'] = hx_api_object.hx_version
					session['hx_int_version'] = int(''.join(str(i) for i in hx_api_object.hx_version))
					session['hx_ip'] = hx_api_object.hx_host
					app.logger.info(format_activity_log(msg="user logged in", user=session['ht_user'], controller=session['hx_ip']))
					redirect_uri = request.args.get('redirect_uri')
					if not redirect_uri:
						redirect_uri = "/"
					return redirect(redirect_uri, code=302)
				else:
					return render_template('ht_login.html', fail=response_data)		
		return render_template('ht_login.html', hx_default_port = HXAPI.HX_DEFAULT_PORT, fail = "Invalid profile id.")
	else:	
		return render_template('ht_login.html', hx_default_port = HXAPI.HX_DEFAULT_PORT)
		
@app.route('/logout', methods=['GET'])
def logout():
	if session:
		if 'ht_api_object' in session:
			hx_api_object = HXAPI.deserialize(session['ht_api_object'])
			hx_api_object.restLogout()
			app.logger.info(format_activity_log(msg="user logged out", user=session['ht_user'], controller=session['hx_ip']))
			hx_api_object = None	
		session.clear()
	return redirect("/login", code=302)

		
###########
### Main ##
###########			
def logout_task_sessions():
	for profile_id in hxtool_global.task_hx_api_sessions:
		hx_api_object = hxtool_global.task_hx_api_sessions[profile_id]
		if hx_api_object:
			hx_api_object.restLogout()
			hx_api_object = None


def sigint_handler(signum, frame):
	app.logger.info("Caught SIGINT, exiting...")
	logout_task_sessions()
	if hxtool_global.hxtool_scheduler:
		hxtool_global.hxtool_scheduler.stop()
	if hxtool_global.hxtool_db:
		hxtool_global.hxtool_db.close()
	exit(0)	


def app_init(debug = False):
	hxtool_global.initialize()
	
	hxtool_global.app_instance_path = app.root_path
	
	# Log early init/failures to stdout
	console_log = logging.StreamHandler(sys.stdout)
	console_log.setFormatter(logging.Formatter('[%(asctime)s] {%(module)s} {%(threadName)s} %(levelname)s - %(message)s'))
	app.logger.addHandler(console_log)
	
	db_write_cache_size = 10
	# If we're debugging use a static key
	if debug:
		app.secret_key = 'B%PT>65`)x<3_CRC3S~D6CynM7^F~:j0'.encode(default_encoding)
		app.logger.setLevel(logging.DEBUG)
		app.logger.debug("Running in debugging mode.")
		db_write_cache_size = 1
	else:
		app.secret_key = crypt_generate_random(32)
		app.logger.setLevel(logging.INFO)
	
	# Init DB
	app.hxtool_db = hxtool_db('hxtool.db', logger = app.logger, write_cache_size = db_write_cache_size)
	hxtool_global.hxtool_db = app.hxtool_db
	
	app.hxtool_config = hxtool_config(combine_app_path('conf.json'), logger = app.logger)
	hxtool_global.hxtool_config = app.hxtool_config
	
	# Initialize the scheduler
	hxtool_global.hxtool_scheduler = hxtool_scheduler(logger = app.logger)
	hxtool_global.hxtool_scheduler.start()
	
	app.task_api_key = 'Z\\U+z$B*?AiV^Fr~agyEXL@R[vSTJ%N&'.encode(default_encoding)
	
	# Loop through background credentials and start the API sessions
	profiles = hxtool_global.hxtool_db.profileList()
	for profile in profiles:
		task_api_credential = hxtool_global.hxtool_db.backgroundProcessorCredentialGet(profile['profile_id'])
		if task_api_credential:
			try:
				salt = HXAPI.b64(task_api_credential['salt'], True)
				iv = HXAPI.b64(task_api_credential['iv'], True)
				key = crypt_pbkdf2_hmacsha256(salt, app.task_api_key)
				decrypted_background_password = crypt_aes(key, iv, task_api_credential['hx_api_encrypted_password'], decrypt = True)
				hxtool_global.task_hx_api_sessions[profile['profile_id']] = HXAPI(profile['hx_host'], 
																					hx_port = profile['hx_port'], 
																					proxies = app.hxtool_config['network'].get('proxies'), 
																					headers = app.hxtool_config['headers'], 
																					cookies = app.hxtool_config['cookies'], 
																					logger_name = hxtool_global.get_submodule_logger_name(HXAPI.__name__), 
																					default_encoding = default_encoding)				
				api_login_task = hxtool_scheduler_task(profile['profile_id'], "Task API Login - {}".format(profile['hx_host']), immutable = True)
				api_login_task.add_step(task_api_session_module, kwargs = {
											'profile_id' : profile['profile_id'],
											'username' : task_api_credential['hx_api_username'],
											'password' : decrypted_background_password
				})
				decrypted_background_password = None
				hxtool_global.hxtool_scheduler.add(api_login_task)
			except UnicodeDecodeError:
				app.logger.error("Please reset the background credential for {} ({}).".format(profile['hx_host'], profile['profile_id']))
		else:
			app.logger.info("No background credential for {} ({}).".format(profile['hx_host'], profile['profile_id']))
	
	# Load tasks from the database after the task API sessions have been initialized
	hxtool_global.hxtool_scheduler.load_from_database()
	
	
	# Initialize configured log handlers
	for log_handler in app.hxtool_config.log_handlers():
		app.logger.addHandler(log_handler)
	
	app.config['SESSION_COOKIE_NAME'] = "hxtool_session"
	app.permanent_session_lifetime = datetime.timedelta(days=7)
	app.session_interface = hxtool_session_interface(app, logger = app.logger, expiration_delta=app.hxtool_config['network']['session_timeout'])

	set_svg_mimetype()
	
debug_mode = False
if __name__ == "__main__":
	signal.signal(signal.SIGINT, sigint_handler)
	
	if len(sys.argv) == 2:
		if sys.argv[1].endswith('-debug'):
			debug_mode = True
		elif sys.argv[1] == '--clear-sessions':
			print("Clearing sessions from the database and exiting.")
			hxtool_db = hxtool_db('hxtool.db')
			for s in hxtool_db.sessionList():
				hxtool_db.sessionDelete(s['session_id'])
			hxtool_db.close()
			hxtool_db = None
			exit(0)
		elif sys.argv[1] == '--clear-saved-tasks':
			print("WARNING! WARNING! WARNING!")
			print("This will clear ALL saved tasks in the database for ALL profiles!")
			if raw_input:
				f = raw_input
			else:
				f = input
			r = f("Do you want to proceed (Y/N)?")
			if r.strip().lower() == 'y':
				print("Clearing saved tasks from the database and exiting.")
				hxtool_db = hxtool_db('hxtool.db')
				for t in hxtool_db.taskList():
					hxtool_db.taskDelete(t['profile_id'], t['task_id'])
				hxtool_db.close()
				hxtool_db = None
			exit(0)
	
	app_init(debug_mode)
	
	# WSGI request log - when not running under gunicorn or mod_wsgi
	logger = logging.getLogger('werkzeug')
	if logger:
		logger.setLevel(app.logger.level)
		request_log_handler = logging.handlers.RotatingFileHandler('log/access.log', maxBytes=50000, backupCount=5)
		request_log_formatter = logging.Formatter("[%(asctime)s] {%(threadName)s} %(levelname)s - %(message)s")
		request_log_handler.setFormatter(request_log_formatter)	
		logger.addHandler(request_log_handler)

	# Start
	app.logger.info('Application starting')
	

	
	# TODO: This should really be after app.run, but you cannot run code after app.run, so we'll leave this here for now.
	app.logger.info("Application is running. Please point your browser to http{0}://{1}:{2}. Press Ctrl+C/Ctrl+Break to exit.".format(
																							's' if app.hxtool_config['network']['ssl'] == 'enabled' else '',
																							app.hxtool_config['network']['listen_address'], 
																							app.hxtool_config['network']['port']))
	if app.hxtool_config['network']['ssl'] == "enabled":
		app.config['SESSION_COOKIE_SECURE'] = True
		context = (app.hxtool_config['ssl']['cert'], app.hxtool_config['ssl']['key'])
		app.run(host=app.hxtool_config['network']['listen_address'], 
				port=app.hxtool_config['network']['port'], 
				ssl_context=context, 
				threaded=True)
	else:
		app.run(host=app.hxtool_config['network']['listen_address'], 
				port=app.hxtool_config['network']['port'])
	
else:
	# Running under gunicorn/mod_wsgi
	app_init(False)
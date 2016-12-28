#!/usr/bin/python

###########################################################
# hxTool - 3rd party user-interface for FireEye HX        #
# Henrik Olsson                                           #
# henrik.olsson@fireeye.com                               #
###########################################################

from flask import Flask, request, session, redirect, render_template, send_file
from hx_lib import *
from hxtool_formatting import *
import base64
import json
import io
import os
import sqlite3
from hxtool_db import *
import datetime

conn = sqlite3.connect('hxtool.db')
c = conn.cursor()

app = Flask(__name__, static_url_path='/static')

@app.route('/')
def index():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):

		# get the last 1000 alerts
		alertsjson = restGetAlerts(session['ht_token'], '1000', session['ht_ip'], '3000')

		# Recent alerts
		alerts = formatDashAlerts(alertsjson, session['ht_token'], session['ht_ip'], '3000')
	
		stats = [{'value': 0, 'label': 'Exploit'}, {'value': 0, 'label': 'IOC'}]
		for alert in alertsjson['data']['entries'][:10]:
			if alert['source'] == "EXD":
				stats[0]['value'] = stats[0]['value'] + 1
			if alert['source'] == "IOC":
				stats[1]['value'] = stats[1]['value'] + 1

		stats[0]['value'] = stats[0]['value'] * 10
		stats[1]['value'] = stats[1]['value'] * 10

		# Event timeline last 30 days
		talert_dates = {}

		base = datetime.datetime.today()
		date_list = [base - datetime.timedelta(days=x) for x in range(0, 30)]
		for date in date_list:
			talert_dates[date.strftime("%Y-%m-%d")] = 0

		ioccounter = 0;
		exdcounter = 0;
		for talert in alertsjson['data']['entries']:

			if talert['source'] == "IOC":
				ioccounter = ioccounter + 1
			if talert['source'] == "EXD":
				exdcounter = exdcounter + 1

			date = talert['event_at'][0:10]
			if date in talert_dates.keys():
				talert_dates[date] = talert_dates[date] + 1

		talerts_list = []
		for key in talert_dates:
			talerts_list.append({"date": str(key), "count": talert_dates[key]})

		# Info table
		hosts = restListHosts(session['ht_token'], session['ht_ip'], '3000')

		contcounter = 0;
		hostcounter = 0;
		searchcounter = 0;
		for entry in hosts['data']['entries']:
			hostcounter = hostcounter + 1
			if entry['containment_state'] != "normal":
				contcounter = contcounter + 1

		searches = restListSearches(session['ht_token'], session['ht_ip'], '3000')
		for entry in searches['data']['entries']:
                        if entry['state'] == "RUNNING":
                                searchcounter = searchcounter + 1;

		blk = restListBulkAcquisitions(session['ht_token'], session['ht_ip'], '3000')
		blkcounter = 0;
		for entry in blk['data']['entries']:
			if entry['state'] == "RUNNING":
				blkcounter = blkcounter + 1;

		return render_template('ht_index.html', session=session, alerts=alerts, iocstats=stats, timeline=talerts_list, contcounter=contcounter, hostcounter=hostcounter, searchcounter=searchcounter, blkcounter=blkcounter, exdcounter=exdcounter, ioccounter=ioccounter)
	else:
		return redirect("/login", code=302)


###################
### Alerts Page ###
###################

@app.route('/alerts', methods=['GET', 'POST'])
def alerts():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		if request.method == "POST":
			# We have a new annotation
			if 'annotateText' in request.form:
				# Create entry in the alerts table
				newrowid = sqlAddAlert(c, conn, session['ht_profileid'], request.form['annotateId'])
				# Add annotation to annotation table
				sqlAddAnnotation(c, conn, newrowid, request.form['annotateText'], request.form['annotateState'])
		
		if 'acount' in request.args:
			acount = request.args['acount']
		else:
			acount = 50
		
		acountselect = ""
		for i in [10, 50, 100, 250, 500, 1000]:
			if (i == int(acount)):
				acountselect += "<option value='/alerts?acount=" + str(i) + "' selected='selected'>Last " + str(i) + " Alerts"
			else:
				acountselect += "<option value='/alerts?acount=" + str(i) + "'>Last " + str(i) + " Alerts"
		
		alerts = restGetAlerts(session['ht_token'], str(acount), session['ht_ip'], '3000')
		alertshtml = formatAlertsTable(alerts, session['ht_token'], session['ht_ip'], '3000', session['ht_profileid'], c, conn)
		
		return render_template('ht_alerts.html', session=session, alerts=alertshtml, acountselect=acountselect)

	else:
		return redirect("/login", code=302)

#########################
#### Search and Sweep ###
#########################

@app.route('/search', methods=['GET', 'POST'])
def search():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):

		# If we get a post it's a new sweep
		if request.method == 'POST':
			f = request.files['newioc']
			rawioc = f.read()
			b64ioc = base64.b64encode(rawioc)
			out = restSubmitSweep(session['ht_token'], session['ht_ip'], '3000', b64ioc)

		s = restListSearches(session['ht_token'], session['ht_ip'], '3000')
		searches = formatListSearches(s)
		return render_template('ht_searchsweep.html', session=session, searches=searches)
	else:
		return redirect("/login", code=302)

@app.route('/searchresult', methods=['GET'])
def searchresult():
        if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		if request.args.get('id'):
			hostresults = restGetSearchResults(session['ht_token'], request.args.get('id'), session['ht_ip'], '3000')
			res = formatSearchResults(hostresults)
	                return render_template('ht_search_dd.html', session=session, result=res)
        else:
                return redirect("/login", code=302)


####################################
#### Build a real-time indicator ###
####################################

@app.route('/buildioc', methods=['GET', 'POST'])
def buildioc():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):

		# New IOC to be created
		if request.method == 'POST':
#			print request.form['iocname']
#			print request.form['cats']

			iocuri = restAddIndicator('apia', request.form['iocname'], request.form['cats'], session['ht_token'], session['ht_ip'], '3000')

			condEx = []
			condPre = []

			for fieldname, value in request.form.items():
				if "cond_" in fieldname:
					condComp = fieldname.split("_")
					if (condComp[2] == "presence"):
						condPre.append(value.rstrip(","))
					elif (condComp[2] == "execution"):
						condEx.append(value.rstrip(","))

			for data in condPre:
				data = """{"tests":[""" + data + """]}"""
				data = data.replace('\\', '\\\\')
				res = restAddCondition(iocuri, "presence", data, request.form['cats'], session['ht_token'], session['ht_ip'], '3000')

			for data in condEx:
                                data = """{"tests":[""" + data + """]}"""
                                data = data.replace('\\', '\\\\')
                                res = restAddCondition(iocuri, "execution", data, request.form['cats'], session['ht_token'], session['ht_ip'], '3000')


		categories = restListIndicatorCategories(session['ht_token'], session['ht_ip'], '3000')
		cats = formatCategoriesSelect(categories)
		iocs = restListIndicators(session['ht_token'], session['ht_ip'], '3000')
		indicators = formatIOCResults(iocs)
		return render_template('ht_buildioc.html', session=session, cats=cats, indicators=indicators)
	else:
		return redirect("/login", code=302)

@app.route('/categories')
def categories():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		return render_template('ht_categories.html', session=session)
	else:
		return redirect("/login", code=302)

@app.route('/export')
def exportioc():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		return render_template('ht_export.html', session=session)
	else:
		return redirect("/login", code=302)

@app.route('/import')
def importioc():
	if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		return render_template('ht_import.html', session=session)
	else:
		return redirect("/login", code=302)

#########################
### Bulk Acqusiitions ###
#########################

@app.route('/bulk', methods=['GET', 'POST'])
def listbulk():
        if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
		if request.method == 'POST':
                        f = request.files['bulkscript']
                        bulkscript = f.read()
			newbulk = restNewBulkAcq(session['ht_token'], bulkscript, request.form['bulkhostset'], session['ht_ip'], '3000')

		acqs = restListBulkAcquisitions(session['ht_token'], session['ht_ip'], '3000')
		bulktable = formatBulkTable(acqs)
                return render_template('ht_bulk.html', session=session, bulktable=bulktable)
        else:
                return redirect("/login", code=302)

@app.route('/bulkdetails')
def bulkdetails():
        if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
                # acqs = restListBulkAcquisitions(session['ht_token'], session['ht_ip'], '3000')
                # bulktable = formatBulkTable(acqs)
		if request.args.get('id'):
			# bulktable = request.args.get('id')

			hosts = restListBulkDetails(session['ht_token'], request.args.get('id'), session['ht_ip'], '3000')
			bulktable = formatBulkHostsTable(hosts)

	                return render_template('ht_bulk_dd.html', session=session, bulktable=bulktable)
        else:
                return redirect("/login", code=302)


@app.route('/bulkdownload')
def bulkdownload():
        if 'ht_user' in session and restIsSessionValid(session['ht_token'], session['ht_ip'], '3000'):
                if request.args.get('id'):
			urlhead, fname = os.path.split(request.args.get('id'))
			acq = restDownloadBulkAcq(session['ht_token'], request.args.get('id'), session['ht_ip'], '3000')
			return send_file(io.BytesIO(acq), attachment_filename=fname, as_attachment=True)
        else:
                return redirect("/login", code=302)


#######################
#### Authentication ###
#######################

@app.route('/login', methods=['GET', 'POST'])
def login():
	#print request.method
	#print request.form['cname']
	#print "kaka2"
	if (request.method == 'POST'):
		if 'ht_user' in request.form:
			print "we have an login attempt..."
			(profileid, myip) = request.form['ht_ip'].split("__")
			
			(resp, message) = restValidateAuth(myip, '3000', request.form['ht_user'], request.form['ht_pass'])
			if resp:
				# Set session variables
				session['ht_user'] = request.form['ht_user']
				session['ht_ip'] = myip
				session['ht_token'] = message
				session['ht_profileid'] = profileid
				return redirect("/", code=302)
			else:
				# return redirect("/login?fail=1", code=302)
				# print message
				return render_template('ht_login.html', fail=message)
			
		elif 'cname' in request.form:
			message = "New profile created"
			
			sqlAddProfileItem(c, conn, request.form['cname'], request.form['chostname'])
			
			options = ""
			for profile in sqlGetProfiles(c):
				options += "<option value='" + str(profile[0]) + "__" + profile[2] + "'>" + profile[1] + " - " + profile[2]

			return render_template('ht_login.html', fail=message, controllers=options)

#		sqlAddProfileItem(c, conn, request.form['cname'], request.form['chostname'])

#                options = ""
 #               for profile in sqlGetProfiles(c):
  #                      options += "<option value='" + profile[2] + "'>" + profile[1] + " - " + profile[2]

#		return render_template('ht_login.html') 
	else:
		# return app.send_static_file('ht_login.html')
		print "GET REQUEST"
		sqlCreateTables(c)
		options = ""
		for profile in sqlGetProfiles(c):
			options += "<option value='" + str(profile[0]) + "__" + profile[2] + "'>" + profile[1] + " - " + profile[2]

		return render_template('ht_login.html', controllers=options)


@app.route('/logout')
def logout():
	session.pop('ht_user', None)
	return redirect("/", code=302)

app.secret_key = 'A0Zr98j/3yX23R~XH1212jmN]Llw/,?RT'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

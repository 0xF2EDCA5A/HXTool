#!/usr/bin/env python
# -*- coding: utf-8 -*-

from werkzeug.datastructures import CallbackDict
from flask.sessions import SessionInterface, SessionMixin
import os
import hmac
import hashlib

from hx_lib import *


class hxtool_session(CallbackDict, SessionMixin):
	def __init__(self, app_secret, logger):
		def on_update(self):	
			if self.accessed == False:
				self.modified = True
			
		self.logger = logger
		self.secret = app_secret
		self.id = None
		self.new = True
		self.accessed = False
		self.modified = False
		CallbackDict.__init__(self, on_update=on_update)
		
	def create(self):
		self.id = str(hmac.new(self.secret, os.urandom(32), digestmod=hashlib.sha256).hexdigest())	
		
	def load(self, id, session_record):	
		if session_record:
			self.logger.debug("Loading saved session data.")
			# Set accessed to True for set/update so we don't loop into on_update()
			self.accessed = True
			# Explicitly set modified to False
			self.modified = False
			self.id = id
			self.update(session_record['session_data'])
			self.accessed = False
	
# expiration_delta is in minutes		
class hxtool_session_interface(SessionInterface):
	def __init__(self, hxtool_db_instance, logger, expiration_delta=30):
		self._ht_db = hxtool_db_instance
		self.logger = logger
		self.session_cache = {}
		self.expiration_delta = expiration_delta
	
	def get_expiration_time(app, session):
		return datetime.datetime.now() + datetime.timedelta(minutes=self.expiration_delta)
		
	def open_session(self, app, request):
		session = hxtool_session(app.secret_key, self.logger)
		
		session_id = request.cookies.get(app.session_cookie_name)
		if session_id:
			cached_session = self.session_cache.get(session_id)
			if not cached_session:					
				session_record = self._ht_db.sessionGet(session_id)
				if session_record:
					session.load(session_id, session_record)
					self.logger.debug("We have an existing database session with id: {0}".format(session.id))
			else:
				session = cached_session
				self.logger.debug("We have an existing cached session with id: {0}".format(session.id))
	
		
		return session
		
	def save_session(self, app, session, response):
		cookie_domain = self.get_cookie_domain(app)
		if not session:
			if not session.new:
				self.logger.debug("Deleting session with id: {0}".format(session.id))
				self._ht_db.sessionDelete(session.id)
				if id in self.session_cache:
					del self.session_cache[session.id]
			if session.modified:
				response.delete_cookie(app.session_cookie_name, domain=cookie_domain)
			return
		
		if not self.should_set_cookie(app, session):
			return
		
		if session.new:
			session.create()
			self._ht_db.sessionCreate(session.id)
			self.logger.debug("Created a new session with id: {0}".format(session.id))
			session.new = False
			
		self.logger.debug("Saving session with id: {0}".format(session.id))
		self._ht_db.sessionUpdate(session.id, session)
		session.modified = False
		
		self.session_cache[session.id] = session
		
		cookie_path = self.get_cookie_path(app)
		http_only = self.get_cookie_httponly(app)
		secure = self.get_cookie_secure(app)	
		response.set_cookie(app.session_cookie_name, session.id, expires=self.get_expiration_time(app, session), path=cookie_path, httponly=http_only, secure=secure, domain=cookie_domain)	

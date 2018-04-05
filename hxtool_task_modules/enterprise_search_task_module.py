#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hxtool_global
from .task_module import *
from hx_lib import *

class enterprise_search_task_module(task_module):
	def __init__(self, profile_id):
			super(enterprise_search_task_module, self).__init__(profile_id)

	def run(self, script, hostset, skip_base64 = False):
		ret = False
		if script:
			hx_api_object = self.get_task_api_object()	
			if hx_api_object and hx_api_object.restIsSessionValid():
				(ret, response_code, response_data) = hx_api_object.restSubmitSweep(script, hostset, skip_base64 = skip_base64)
			else:
				self.logger.warn("No task API session for profile: {}".format(self.profile_id))	
		return ret
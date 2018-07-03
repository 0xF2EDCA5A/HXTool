#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hxtool_global
from .task_module import *
from hx_lib import *

class enterprise_search_task_module(task_module):
	def __init__(self, parent_task):
		super(type(self), self).__init__(parent_task)
	
	@staticmethod
	def input_args():
		return [
			{
				'name' : 'script',
				'type' : str,
				'required' : True,
				'description' : "The OpenIOC 1.1 formatted script to utilize."
			},
			{
				'name' : 'hostset_id',
				'type' : int,
				'required' : True,
				'description' : "The ID of the host set to execute the script against."
			},
			{
				'name' : 'skip_base64',
				'type' : bool,
				'required' : False,
				'description' : "Specifies whether the contents of the script argument are already base64 encoded. Defaults to False"
			}
		]
		
	@staticmethod
	def output_args():
		return []
	
	def run(self, script = None, hostset_id = None, skip_base64 = False):
		ret = False
		if script:
			hx_api_object = self.get_task_api_object()	
			if hx_api_object and hx_api_object.restIsSessionValid():
				(ret, response_code, response_data) = hx_api_object.restSubmitSweep(script, hostset_id, skip_base64 = skip_base64)
				if ret:
					self.logger.info("Enterprise Search successfully submitted.")
				else:
					self.logger.error("Enterprise Search submission failed. Response code: {}, response data: {}".format(response_code, response_data))
			else:
				self.logger.warn("No task API session for profile: {}".format(self.parent_task.profile_id))	
		return(ret, None)
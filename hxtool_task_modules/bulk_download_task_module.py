#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hxtool_global
from .task_module import *
from hxtool_util import *

class bulk_download_task_module(task_module):
	def __init__(self, parent_task):
		super(type(self), self).__init__(parent_task)
	
	@staticmethod
	def input_args():
		return [
			{ 
				'name' : 'bulk_acquisition_id',
				'type' : int,
				'required' : True,
				'description' : "The ID of the bulk acquisition job on the HX controller."
			}, 
			{
				'name' : 'host_id',
				'type' : str,
				'required' : True,
				'description' : "The host/agent ID of the bulk acquisition to download."
			},
			{
				'name' : 'host_name',
				'type' : str,
				'required' : True,
				'description' : "The host name of the agent."
			}
		]
	
	@staticmethod
	def output_args():
		return [
			{ 
				'name' : 'bulk_download_path',
				'type' : str,
				'required' : True,
				'description' : "The fully qualified path to the bulk acquisition package."
			}
		]	
		
	def run(self, bulk_acquisition_id = None, host_id = None, host_name = None):
		ret = False
		result = {}
		try:
			if hxtool_global.hxtool_db.bulkDownloadGet(self.parent_task.profile_id, bulk_acquisition_id)['stopped'] == False:			
				hx_api_object = self.get_task_api_object()	
				if hx_api_object and hx_api_object.restIsSessionValid():
					(ret, response_code, response_data) = hx_api_object.restGetBulkHost(bulk_acquisition_id, host_id)
					if ret and response_data and (response_data['data']['state'] == "COMPLETE" and response_data['data']['result']):
						self.logger.debug("Processing bulk download for host: {0}".format(host_name))
						download_directory = make_download_directory(hx_api_object.hx_host, bulk_acquisition_id)
						full_path = os.path.join(download_directory, get_download_filename(host_name, host_id))
						(ret, response_code, response_data) = hx_api_object.restDownloadFile(response_data['data']['result']['url'], full_path)
						if ret:
							hxtool_global.hxtool_db.bulkDownloadUpdateHost(self.parent_task.profile_id, bulk_acquisition_id, host_id)
							self.logger.debug("Bulk download for host {} successfully downloaded to {}".format(host_name, full_path))
							result['bulk_download_path'] = full_path
					elif ret and response_data and response_data['data']['state'] == 'FAILED':
						ret = False
					elif ret and response_data and (response_data['data']['state'] in {'CANCELLED', 'ABORTED'} or 
													(response_code == 404 and response_data['details'][0]['code'] == 1005)):
						self.logger.debug("Controller returned code: {}, data: {}".format(response_code, response_data))
						self.parent_task.stop()
						ret = False
					else:
						self.logger.debug("Deferring bulk download task for: {}".format(host_name))
						self.parent_task.defer()
				else:
					self.logger.warn("No task API session for profile: {}".format(self.parent_task.profile_id))
			else:
				self.logger.info("Bulk download {} is stopped.".format(bulk_acquisition_id))
				self.parent_task.stop()
		except Exception as e:
			self.logger.error(e)
		finally:	
			return(ret, result)		

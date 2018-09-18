#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import os
import json

import hxtool_global
from .task_module import *
from hx_audit import *

class streaming_task_module(task_module):
	def __init__(self, parent_task):
		super(type(self), self).__init__(parent_task)
	
	@staticmethod
	def input_args():
		return [
			{
				'name' : 'host_name',
				'type' : str,
				'required' : True,
				'user_supplied' : False,
				'description' : "The host name belonging to the bulk acquisition package."
			},
			{
				'name' : 'bulk_download_path',
				'type' : str,
				'required' : True,
				'user_supplied' : False,
				'description' : "The fully qualified path to the bulk acquisition package."
			},
			{
				'name' : 'batch_mode',
				'type' : bool,
				'required' : False,
				'user_supplied' : True,
				'description' : "Flag whether to batch each audit as single JSON object versus sending each record as a separate object. Defaults to False"
			},
			{
				'name' : 'delete_bulk_download',
				'type' : bool,
				'required' : False,
				'user_supplied' : True,
				'description' : "Flag whether to delete the bulk acquisition package locally once complete. Defaults to False"
			},
			{
				'name' : 'stream_protocol',
				'type' : str,
				'required' : False,
				'user_supplied' : True,
				'description' : "The protocol to use when streaming. Defaults to TCP"
			},
			{
				'name' : 'stream_host',
				'type' : str,
				'required' : True,
				'user_supplied' : True,
				'description' : "The FQDN or IP address of the host to stream to."
			},
			{
				'name' : 'stream_port',
				'type' : int,
				'required' : True,
				'user_supplied' : True,
				'description' : "The port on which to stream to."
			}
				
		]
	
	@staticmethod
	def output_args():
		return []
	
	def run(self, host_name = None, bulk_download_path = None, batch_mode = False, delete_bulk_download = False, stream_host = None, stream_port = None, stream_protocol = 'tcp'):
		try:
			ret = False
			if bulk_download_path:
				audit_objects = []
				with AuditPackage(bulk_download_path) as audit_package:
					for audit in audit_package.audits:
						audit_object = audit_package.audit_to_dict(audit, host_name, batch_mode = batch_mode)
						if audit_object:
							audit_objects.append(audit_object)
				if len(audit_objects) > 0:
					socket_type = socket.SOCK_STREAM
					if stream_protocol == 'udp':
						socket_type = socket.SOCK_DGRAM
					for res in socket.getaddrinfo(stream_host, stream_port, socket.AF_UNSPEC, socket_type):
						address_family, socktype, proto, canonname, sockaddr = res

						stream_socket = socket.socket(address_family, socktype, proto)
						stream_socket.connect(sockaddr)

						## ELAZAR YOU NEED TO CHECK THIS CODE
						if batch_mode:
							stream_socket.sendall(json.dumps(audit_objects, sort_keys = False, indent=4).encode('utf-8'))
						else:
							for myaudit_object in audit_objects[0]:
								stream_socket.sendall(json.dumps(myaudit_object, sort_keys = False).encode('utf-8'))

						stream_socket.close()
									
						ret = True
				else:
					self.logger.warn("Streaming: No audit data for {} from bulk acquisition {}".format(host_name, bulk_acquisition_id))
												
				if ret and delete_bulk_download:
					os.remove(os.path.realpath(bulk_download_path))
				
			else:
				self.logger.error("bulk_download_path is empty!")
				
			return(ret, None)
		except Exception as e:
			self.logger.error(e)
			return(False, None)
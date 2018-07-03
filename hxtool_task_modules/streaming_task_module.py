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
				'description' : "The host name belonging to the bulk acquisition package."
			},
			{
				'name' : 'bulk_download_path',
				'type' : str,
				'required' : True,
				'description' : "The fully qualified path to the bulk acquisition package."
			},
			{
				'name' : 'delete_bulk_download',
				'type' : bool,
				'required' : False,
				'description' : "Flag whether to delete the bulk acquisition package locally once complete. Defaults to False"
			},
			{
				'name' : 'stream_protocol',
				'type' : str,
				'required' : False,
				'description' : "The protocol to use when streaming. Defaults to TCP"
			},
			{
				'name' : 'stream_host',
				'type' : str,
				'required' : True,
				'description' : "The FQDN or IP address of the host to stream to."
			},
			{
				'name' : 'stream_port',
				'type' : int,
				'required' : True,
				'description' : "The port on which to stream to."
			}
				
		]
	
	@staticmethod
	def output_args():
		return []
	
	def run(self, host_name = None, bulk_download_path = None, delete_bulk_download = False, stream_host = None, stream_port = None, stream_protocol = 'tcp'):
		try:
			ret = False
			if bulk_download_path:
				audit_objects = []
				with AuditPackage(bulk_download_path) as audit_package:
					for audit in audit_package.audits:
						audit_object = audit_package.audit_to_dict(audit)
						if audit_object:
							audit_objects.append(audit_object)
				if len(audit_objects) > 0:
					socket_type = socket.SOCK_STREAM
					if stream_protocol == 'udp':
						socket_type = socket.SOCK_DGRAM
					address_family, socktype, proto, canonname, sockaddr = socket.getaddrinfo(stream_host, stream_port, socket.AF_UNSPEC, socket_type)
					stream_socket = socket.socket(address_family, socktype, proto)
					socket.connect(sockaddr)
					socket.sendall(json.dumps(audit_objects, sort_keys = False, indent = 4))
					socket.close()
								
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
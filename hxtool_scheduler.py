#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import threading
import datetime
import random

try:
	import Queue as queue
except ImportError:
	import queue

import hxtool_global
from hx_lib import HXAPI
import hxtool_task_modules
from hxtool_util import *

TASK_STATE_SCHEDULED = 0
TASK_STATE_QUEUED = 1
TASK_STATE_RUNNING = 2
TASK_STATE_COMPLETE = 3
TASK_STATE_STOPPED = 4
TASK_STATE_FAILED = 5

task_state_description = {
	TASK_STATE_SCHEDULED: "Scheduled",
	TASK_STATE_QUEUED 	: "Queued",
	TASK_STATE_RUNNING	: "Running",
	TASK_STATE_COMPLETE : "Complete",
	TASK_STATE_STOPPED	: "Stopped",
	TASK_STATE_FAILED	: "Failed"
}


# Special task indicator that we need to exit now
SIGINT_TASK_ID = -1
		
# Note: scheduler resolution is a little less than a second
class hxtool_scheduler:
	def __init__(self, task_thread_count = 4, logger = logging.getLogger(__name__)):
		self.logger = logger
		self._lock = threading.Lock()
		self.task_queue = {}
		self.history_queue = {}
		self.run_queue = queue.Queue()
		self._poll_thread = threading.Thread(target = self._scan_task_queue, name = "PollThread")
		self._stop_event = threading.Event()
		self.task_thread_count = task_thread_count
		self.task_threads = []
		self.logger.info("Task scheduler initialized.")

	def _scan_task_queue(self):
		while not self._stop_event.is_set():
			with self._lock:
				for task_id, task in self.task_queue:
					if task.should_run():
						self.run_queue.put((task_id, task.name, task.run))
						task.set_state(TASK_STATE_QUEUED)
			self._stop_event.wait(.01)
		
	def _await_task(self):
		while not self._stop_event.is_set():
			(task_id, task_name, task_run) = self.run_queue.get()
			# Special task indicator that we need to exit now
			if task_id == SIGINT_TASK_ID:
				self.logger.debug("Got SIGINT_TASK_ID, exiting.")
				self.run_queue.task_done()
				break
			self.logger.info("Executing task with id: %s, name: %s.", task_id, task_name)
			ret = task_run()
			self.run_queue.task_done()
	
	def start(self):
		self._poll_thread.start()
		for i in range(0, self.task_thread_count):
			t = threading.Thread(target = self._await_task, name = "TaskThread - {}".format(i))
			t.start()
			self.task_threads.append(t)
		self.logger.info("Task scheduler started.")
		
	def stop(self):
		self.logger.debug('stop() enter.')		
		for i in range(0, len(self.task_threads)):
			self.run_queue.put((SIGINT_TASK_ID, None, None))
		self.run_queue.join()
		self._stop_event.set()
		del self.task_threads[:]
		self.logger.debug('stop() exit.')
	
	def signal_child_tasks(self, task_id):
		with self._lock:
			for k, v in self.task_queue:
				if v.parent_id == task_id:
					v.parent_complete = True
	
	def add(self, task, store = True):
		with self._lock:
			self.task_queue[task.task_id] = task
			task.set_state(TASK_STATE_SCHEDULED)
		
		task.store()
		
	def add_list(self, tasks):
		if isinstance(tasks, list):
			for t in tasks:
				self.add(t)
		
	def remove(self, task_id):
		if task_id:
			with self.lock:
				del self.task_queue[task_id]
	
	def get(self, task_id):
		if task_id:
			with self.lock:
				return self.task_queue.get(task_id)
		
	def tasks(self):
		return self.task_queue.values()
		
	def status(self):
		return self._poll_thread.is_alive()
			
class hxtool_scheduler_task:
	def __init__(self, profile_id, name, task_id = None, interval = None, start_time = datetime.datetime.utcnow(), end_time = None, enabled = True, immutable = False, stop_on_fail = True, parent_id = None, wait_for_parent = True, defer_interval = 30, logger = logging.getLogger(__name__)):
		self.logger = hxtool_global.hxtool_scheduler.logger
		self._lock = threading.Lock()
		self.profile_id = profile_id
		self.task_id = task_id
		if not self.task_id:
			self.task_id = str(secure_uuid4())
		self.parent_id = parent_id
		self.wait_for_parent = wait_for_parent
		self.parent_complete = False
		self.name = name
		self.enabled = enabled
		self.immutable = immutable
		self.state = None
		self.last_run_state = None
		self.interval = interval
		self.start_time = start_time
		self.end_time = end_time
		self.last_run = None
		self.next_run = start_time
		self.stop_on_fail = stop_on_fail
		self.steps = []
		self.stored_result = None
		self.defer_interval = defer_interval
		
		self._stored = False
		self._stop_signal = False
		self._defer_signal = False
		

	def add_step(self, module, func = "run", args = (), kwargs = {}):
		# This is an HXTool task module, we need to init it.
		if hasattr(module, 'hxtool_task_module'):
			module = module(self)
		with self._lock:
			self.steps.append((module, func, args, kwargs))
		
	def _calculate_next_run(self):
		self.next_run = None
		if type(self.interval) is datetime.timedelta:
			self.next_run = (self.last_run + self.interval)
		elif self._defer_signal:
			# Add some random seconds to the interval to keep the task threads from deadlocking
			self.next_run = (self.last_run + datetime.timedelta(seconds = (self.defer_interval + random.randint(1, 15))))
	
	# Use this to set state, its thread-safe
	def set_state(self, state):
		with self._lock:
			self.state = state
	
	def run(self):
		self._stop_signal = False
		self._defer_signal = False
		ret = False
		
		if self.enabled:
			
			with self._lock:
				
				self.state = TASK_STATE_RUNNING
				
				# Reset microseconds to keep from drifting too badly
				self.last_run = datetime.datetime.utcnow().replace(microsecond=1)
				
				for module, func, args, kwargs in self.steps:
					self.logger.debug("Have module: {}, function: {}".format(module.__module__, func))
					if hasattr(module, 'hxtool_task_module'):
						# Add the stored result args to kwargs - taking care not stomp over existing args
						if not set(module.run_args()) == set(kwargs.keys()) and isinstance(self.stored_result, dict) and bool(set(module.run_args()).intersection(self.stored_result.keys())):
							kwargs.update(self.stored_result)
					
						if not set(module.run_args()) == set(kwargs.keys()):
							self.logger.error("Module {} requires arguments that were not found! Bailing!".format(module.__module__))
							ret = False
							self.state = TASK_STATE_FAILED
							break
				
					result = getattr(module, func)(*args, **kwargs)
					
					if isinstance(result, tuple) and len(result) > 1:
						ret = result[0]
						# Store the result - make sure it is of type dict
						if isinstance(result[1], dict):
							self.stored_result = result[1]
						elif result[1] != None:
							self.logger.error("Task module {} returned a value that was not a dictionary or None. Discarding the result.".format(module.__module__))
					else:
						ret = result
					
					
					if self._defer_signal:
						break
					elif self._stop_signal:
						self.state = TASK_STATE_STOPPED
						break
					elif not ret and self.stop_on_fail:
						self.state = TASK_STATE_FAILED
						break
			
				self._calculate_next_run()
				
				if self.next_run:
					self.last_run_state = self.state
					self.state = TASK_STATE_SCHEDULED
				elif self.state < TASK_STATE_STOPPED:
					self.state = TASK_STATE_COMPLETE
										
		else:
			self.set_state(TASK_STATE_STOPPED)
		
		if self._stored and not self.immutable:				
			if self.state != TASK_STATE_SCHEDULED:
				hxtool_global.hxtool_db.taskDelete(self.profile_id, self.task_id)
				self._stored = False
			else:
				hxtool_global.hxtool_db.taskUpdate(self.profile_id, self.task_id, self.serialize())
		
		if self.state < TASK_STATE_STOPPED:
			hxtool_global.hxtool_scheduler.signal_child_tasks(self.task_id)
		
		return ret

	def stop(self):
		self._stop_signal = True
	
	def defer(self):
		self._defer_signal = True
		
	def should_run(self):
		return (self.enabled and  
				self.state == TASK_STATE_SCHEDULED and
				(self.parent_id and self.wait_for_parent and self.parent_complete) and	
				len(self.steps) > 0 and 
				((datetime.datetime.utcnow() - self.next_run).seconds == 0 or 
				self.start_time == self.next_run))
				
	
	def set_stored(self, stored = True):
		with self._lock:
			self._stored = stored
			
	def store(self):
		if not (self._stored and self.immutable):
			hxtool_global.hxtool_db.taskCreate(self.profile_id, self.task_id, self.serialize())
			self.set_stored()
		
	def serialize(self):
		return {
			'profile_id' : self.profile_id,
			'task_id' : self.task_id,
			'name' : self.name,
			'interval' : self.interval.seconds if type(self.interval) is datetime.timedelta else None,
			'start_time' : str(self.start_time),
			'end_time' : str(self.end_time) if self.end_time else None,
			'enabled' : self.enabled,
			'immutable' : self.immutable,
			'stop_on_fail' : self.stop_on_fail,
			'parent_id' : self.parent_id,
			'parent_complete' : self.parent_complete,
			'wait_for_parent' : self.wait_for_parent,
			'defer_interval' : self.defer_interval,
			'state' : self.state,
			'last_run_state' : self.last_run_state,
			'stored_result' : self.stored_result,
			'steps' : [{ 
						'module' : m.__module__,
						'function' : f,
						'args' : a,
						'kwargs' : ka
						}
						for m, f, a, ka in self.steps
			]
		}
	
	@staticmethod	
	def deserialize(d):
		task = hxtool_scheduler_task(d['profile_id'],
									d['name'],
									task_id = d['task_id'],
									parent_id = d.get('parent_id', None)
									wait_for_parent = d.get('wait_for_parent', True)
									interval = datetime.timedelta(seconds = d['interval']) if d['interval'] else None,
									start_time = HXAPI.dt_from_str(d['start_time']),
									end_time = HXAPI.dt_from_str(d['end_time']) if d['end_time'] else None,
									enabled = d['enabled'],
									immutable = d['immutable'],
									stop_on_fail = d['stop_on_fail'],
									defer_interval = d['defer_interval'])
		task.parent_complete = d.get('parent_complete', False)
		task.last_run_state = d.get('last_run_state', None)							
		task.state = d.get('state')
		for s in d['steps']:
			# I hate this
			step_module = eval(s['module'])
			task.add_step(step_module, s['function'], s['args'], s['kwargs'])
		return task
									
									
		
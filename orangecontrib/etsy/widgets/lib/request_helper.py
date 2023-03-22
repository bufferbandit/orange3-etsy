import asyncio
import inspect
import traceback
from concurrent.futures import ThreadPoolExecutor
from pprint import pprint

from PyQt5.QtWidgets import QMessageBox
from etsyv3.etsy_api import BadRequest, Unauthorised, NotFound, InternalError, Forbidden, Conflict
from orangewidget.widget import Msg


# from rich import traceback


class RequestHelper:
	def __init__(self):
		self.override_string_add_attribute(str, "value", property(lambda self: self))


	def merge_dicts(self, dicts):
		merged = {}
		for _dict in dicts:
			for _key, _value in _dict.items():
				offset, limit = _key
				for key, value in _value.items():
					if key == "results":
						# self.logger.debug("Num results: ", len(value))
						pass
					# this could be done with checking for __add__ imo, but that doesnt seem to work
					if isinstance(value, (int, float, list, tuple)):
						empty_default_object = __builtins__[type(value).__name__]()
						merged[key] = merged.get(key, empty_default_object) + value
					else:
						self.logger.debug("Merged for " + key)
						merged[key] = value
		return merged

	def handle_etsy_api_client_exception(self, exception):
		ERROR_MESSAGES = {
			BadRequest: ("400 Bad request. ", "400"),
			Unauthorised: ("401 Unauthorised. ", "401"),
			Forbidden: ("403 Forbidden. ", "403"),
			Conflict: ("409 Conflict. ", "409"),
			NotFound: ("404 Not found. ", "404"),
			InternalError: ("500 Internal server error. ", "500")
		}
		try:
			error_msg_prefix,status_code  = ERROR_MESSAGES[type(exception)]
			error_msg = error_msg_prefix
			self.change_http_status_label(error_msg, color="red")
			# self.transform_err = Msg(error_msg)
			self.error(error_msg)
			error_msg = f"{error_msg_prefix}{exception.__class__.__name__}: {exception.args[0]}"
			self.change_app_status_label(error_msg[:120] + "...", "red")
			QMessageBox.critical(self, "Error", error_msg[:1500] + "...", QMessageBox.Ok)
			self.logger.debug(self.get_traceback())
		except KeyError as ke: # Error is not in the dict
			raise exception

	def send_request(self):
		try:
			# TODO: Look into a way to make this a more
			#  time based semaphore (the api has a rate limit of 10 reqs/sec)
			pool = ThreadPoolExecutor(max_workers=self.CLIENT_MAX_THREADS)
			# self.logger.debug(self.paginateLimitValue, self.etsy_request_offsets_and_limits)
			tasks = []
			# For some reason the offset and limit are swapped around
			#  (which is not the way it's comming out of the function)
			#  really strange bug, and potentially very dangerous.
			# for limit, offset in self.etsy_request_offsets_and_limits:
			def wrapper(offset, limit, *args, **kwargs):
				# try:
				paramters = inspect.signature(self.etsy_client_send_request).parameters
				if "limit" in paramters: kwargs["limit"] = limit
				if "offset" in paramters: kwargs["offset"] = offset
				return {
					(offset, limit):
						self.etsy_client_send_request(*args, **kwargs)
				}
				# except Exception as e:

			for offset, limit in self.etsy_request_offsets_and_limits:
				task = pool.submit(
						wrapper,
						limit=limit,
						offset=offset,
						*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
						**self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS,

				)
				tasks.append(task)
			results = [task.result() for task in tasks]
			sorted_dicts = sorted(results, key=lambda x: sum(list(x.keys())[0]))
			# self.logger.debug([d.keys() for d in sorted_dicts])
			merged_dicts = self.merge_dicts(sorted_dicts)
			self.ETSY_API_RESPONSE = merged_dicts
			self.change_http_status_label("200 OK", color="green")
			self.populate_data()
		except Exception as e:
			self.handle_etsy_api_client_exception(e)






	"""
	There's this anoying thing the etsy client library does in which it uses
	enums instead of strings for certain fields. Problem is that this would make
	the whole api reference lookup pointless in a way. The easiest fix/bypass
	to me seems to just override the builtin string type and add the "value" attribute 
	it requires and trick the library.
	"""
	def override_string_add_attribute(self, obj, name, value):
		import ctypes as c
		class PyObject_HEAD(c.Structure):
			_fields_ = [
				("HEAD", c.c_ubyte * (object.__basicsize__ -
				                      c.sizeof(c.c_void_p))),
				("ob_type", c.c_void_p)
			]
		_get_dict = c.pythonapi._PyObject_GetDictPtr
		_get_dict.restype = c.POINTER(c.py_object)
		_get_dict.argtypes = [c.py_object]
		_get_dict(obj).contents.value[name] = value


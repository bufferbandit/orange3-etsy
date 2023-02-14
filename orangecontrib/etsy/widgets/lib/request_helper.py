import asyncio
import inspect
import traceback
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
						# print("Num results: ", len(value))
						pass
					# this could be done with checking for __add__ imo, but that doesnt seem to work
					if isinstance(value, (int, float, list, tuple)):
						empty_default_object = __builtins__[type(value).__name__]()
						merged[key] = merged.get(key, empty_default_object) + value
					else:
						print("Merged for " + key)
						merged[key] = value
		return merged
	async def send_request(self):
		try:
			# print(self.paginateLimitValue, self.etsy_request_offsets_and_limits)
			tasks = []
			for offset, limit in self.etsy_request_offsets_and_limits:
			# For some reason the offset and limit are swapped around
			#  (which is not the way it's comming out of the function)
			#  really strange bug, and potentially very dangerous.
			# for limit, offset in self.etsy_request_offsets_and_limits:
				async def wrapper(offset, limit, *args, **kwargs):
					paramters = inspect.signature(self.etsy_client_send_request).parameters
					if "limit" in paramters:kwargs["limit"] = limit
					if "offset" in paramters:kwargs["offset"] = offset
					return {
						(offset, limit) :
								self.etsy_client_send_request(*args, **kwargs)
					}
				task = asyncio.create_task(
					wrapper(
						limit=limit,
						offset=offset,
						*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
						**self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS,
					)
				)
				tasks.append(task)
			results = await asyncio.gather(*tasks)
			sorted_dicts = sorted(results, key=lambda x: sum(list(x.keys())[0]))
			# print([d.keys() for d in sorted_dicts])
			merged_dicts = self.merge_dicts(sorted_dicts)
			self.ETSY_API_RESPONSE = merged_dicts
			self.change_http_status_label("200 OK", color="green")
			self.populate_data()
		except BadRequest as e:
			error_msg = "400 Bad request. "
			QMessageBox.critical(self, "400", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except Unauthorised as e:
			error_msg = "401 Unauthorised. "
			QMessageBox.critical(self, "401", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except Forbidden as e:
			error_msg = "403 Forbidden. "
			QMessageBox.critical(self, "403", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except Conflict as e:
			error_msg = "409 Conflict. "
			QMessageBox.critical(self, "409", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except NotFound as e:
			error_msg = "404 Not found. "
			QMessageBox.critical(self, "404", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except InternalError as e:
			error_msg = "500 Internal server error. "
			QMessageBox.critical(self, "500", error_msg, QMessageBox.Ok)
			self.change_http_status_label(error_msg + str(e), color="red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
		except Exception as e:
			# Re-raising it does not seem to work
			self.change_http_status_label("Unknown error while sending request: " + e.args[0], color="red")
			error_msg = f"Unknown error while sending request: {e.__class__.__name__}: {e.args[0]}"
			self.change_app_status_label(error_msg[:120]+"...", "red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
			QMessageBox.critical(self, "Error", error_msg[:1500]+"...", QMessageBox.Ok)
			print(self.get_traceback())






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

	# For some stupid reason asyncio functins dont seem to print the stacktrace to the console.
	# This function is a workaround for that.



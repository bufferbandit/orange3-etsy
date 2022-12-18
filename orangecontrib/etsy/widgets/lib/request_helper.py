import asyncio
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
				d = _value
				for key, value in d.items():
					# this could be done with checking for __add__ imo, but that doesnt seem to work
					if isinstance(value, (int, float, list, tuple)):
						empty_default_object = __builtins__[type(value).__name__]()
						merged[key] = merged.get(key, empty_default_object) + value
					else:
						print("Merged for " + key)
						merged[key] = value
		return merged
	async def send_request(self):
		print(self.etsy_request_offsets_and_limit)
		try:
			tasks = []
			for offset, limit in self.etsy_request_offsets_and_limits:
				async def wrapper(offset, limit, *args, **kwargs):
					return {(offset, limit) : self.etsy_client_send_request(*args, **kwargs)}
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
			merged_dicts = self.merge_dicts(*sorted_dicts)
			self.ETSY_API_RESPONSE = merged_dicts
			self.change_http_status_label("200 OK", color="green")
			self.populate_data()
		except BadRequest as e:
			self.change_http_status_label("400 Bad request", color="red")
		except Unauthorised as e:
			self.change_http_status_label("401 Unauthorised", color="red")
		except Forbidden as e:
			self.change_http_status_label("403 Forbidden", color="red")
		except Conflict as e:
			self.change_http_status_label("409 Conflict", color="red")
		except NotFound as e:
			self.change_http_status_label("404 Not found", color="red")
		except InternalError as e:
			self.change_http_status_label("500 Internal server error", color="red")
		except Exception as e:
			# Re-raising it does not seem to work
			self.change_http_status_label("Unknown error while sending request: " + e.args[0], color="red")
			error_msg = f"Unknown error while sending request: {e.__class__.__name__}: {e.args[0]}"
			self.change_app_status_label(error_msg[:120]+"...", "red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)



			print(self.get_traceback())


			QMessageBox.critical(self, "Error", error_msg[:1500]+"...", QMessageBox.Ok)




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
	def get_traceback(self):
		import traceback, sys
		exc = sys.exc_info()[0]
		if exc is not None:
			f = sys.exc_info()[-1].tb_frame.f_back
			stack = traceback.extract_stack(f)
		else:
			stack = traceback.extract_stack()[:-1]  # last one would be full_stack()
		trc = 'Traceback (most recent call last):\n'
		stackstr = trc + ''.join(traceback.format_list(stack))
		if exc is not None:
			stackstr += '  ' + traceback.format_exc().lstrip(trc)
		return stackstr


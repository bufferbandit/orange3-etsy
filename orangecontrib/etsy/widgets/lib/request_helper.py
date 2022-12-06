import traceback

from etsyv3.etsy_api import BadRequest, Unauthorised, NotFound, InternalError, Forbidden, Conflict
# from rich import traceback


class RequestHelper:
	def __init__(self):
		self.override_string_add_attribute(str, "value", property(lambda self: self))

	def dispatch_request(self):
		self.send_request()

	def send_request(self):
		self.change_app_status_label("Sending request")
		try:

			# Sequence requests

			# if self.ETSY_API_CLIENT_SEND_REQUEST_ARGS
			res = self.etsy_client_send_request(*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
			                                    **self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS)

			self.ETSY_API_RESPONSE = res
			self.change_http_status_label("200 OK", color="green")
			self.populateData()
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
			self.change_http_status_label("Unknown error while sending request: ", color="red")
			raise e


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


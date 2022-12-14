import traceback
from asyncio import Lock
from pprint import pprint

from etsyv3.etsy_api import BadRequest, Unauthorised, NotFound, InternalError, Forbidden, Conflict
# from rich import traceback


class RequestHelper:
	def __init__(self):
		self.override_string_add_attribute(str, "value", property(lambda self: self))

	def combine_dicts(self,*dicts, ints_whitelist=None, list_whitelist=None):
		combined = {}
		for dictionary in dicts:
			for key in dictionary:
				if key in combined:
					# If the key already exists in the combined dictionary, we need to
					# handle the value differently depending on the type
					if isinstance(combined[key], list) and isinstance(dictionary[key], list):
						if list_whitelist is None or key in list_whitelist:
							# If the key maps to a list in both dictionaries, we can simply
							# extend the list in the combined dictionary
							combined[key] = combined[key] + dictionary[key]
					elif isinstance(combined[key], int) and isinstance(dictionary[key], int):
						if ints_whitelist is None or key in ints_whitelist :
							# If the key maps to an int in both dictionaries, we can simply
							# add the ints together
							combined[key] += dictionary[key]
					else:
						# If the values for the key are not both lists or both ints, we
						# can't combine them so we'll just keep the original value in the
						# combined dictionary
						pass
				else:
					# If the key doesn't exist in the combined dictionary, we can simply
					# add it and its value to the combined dictionary
					combined[key] = dictionary[key]
		return combined

	def dispatch_request(self):
		self.send_request()

	def send_request(self):
		# add an asyncio Lock
		self.request_lock = Lock()
		self.change_app_status_label("Sending request")
		try:

			# Sequence requests

			# if self.ETSY_API_CLIENT_SEND_REQUEST_ARGS

			res = {}
			for offset, limit in self.etsy_request_offsets_and_limits:
				new_res = self.etsy_client_send_request(*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
				                                    **self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS,
				                                    offset=offset, limit=limit)
				res = self.combine_dicts(new_res, res) #, ints_whitelist=["count"], list_whitelist=["results"])

			pprint(res)

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


	# def combine_dicts(self, *dicts):
	# 	combined_dict = {}
	# 	for d in dicts:
	# 		combined_dict.update(d)
	# 	return combined_dict


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


import asyncio
import traceback
from asyncio import Lock
from pprint import pprint

from PyQt5.QtWidgets import QMessageBox
from etsyv3.etsy_api import BadRequest, Unauthorised, NotFound, InternalError, Forbidden, Conflict
from orangewidget.widget import Msg


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

	async def combine_results(self, response_offset_dict):
		combined_results = []

		for key in sorted(response_offset_dict.keys()):
			offset, limit = key
			response = response_offset_dict[key]
			combined_results.extend(response['results'])

		return combined_results

	async def combine_responses(self, response_offset_dict):
		combined_response = {}

		for key in response_offset_dict:
			offset, limit = key
			response = response_offset_dict[key]

			# Iterate over the key-value pairs in the response dictionary
			for k, v in response.items():
				if k not in combined_response:
					# Add the key-value pair to the combined_response dictionary if the key does not already exist
					combined_response[k] = v
				else:
					# If the key already exists in the combined_response dictionary, merge the value with the existing value
					existing_value = combined_response[k]
					if isinstance(existing_value, list):
						combined_response[k].extend(v)
					elif isinstance(existing_value, dict):
						combined_response[k].update(v)

		return combined_response



	async def send_request(self):
		# add an asyncio Lock
		self.request_lock = Lock()
		self.change_app_status_label("Sending request")
		try:
			async with asyncio.gather(*[
				self.etsy_client_send_request(
					*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
					**self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS,
					offset=offset,
					limit=limit
				) for offset, limit in self.etsy_request_offsets_and_limits
			]) as responses:
				response_offset_dict = {}
				for (offset, limit), response in zip(self.etsy_request_offsets_and_limits, responses):
					key = (offset, limit)
					response_offset_dict[key] = response

				combined_results = await self.combine_results(response_offset_dict)
				combined_response = await self.combine_responses(response_offset_dict)

			# print(combined_results)
			# print(combined_response)

			self.ETSY_API_RESPONSE = combined_response
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
			# Re-raising it does not seem to work
			self.change_http_status_label("Unknown error while sending request: " + e.args[0], color="red")
			error_msg = f"Unknown error while sending request: {e.__class__.__name__}: {e.args[0]}"
			self.change_app_status_label(error_msg, "red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
			QMessageBox.critical(self, "Error", error_msg, QMessageBox.Ok)

	# except Exception as e:
		# 	self.change_http_status_label("Unknown error while sending request: " +  e.args[0] , color="red")
		#
		# 	error_msg = f"Error: {exctype}: {value}"
		# 	self.change_app_status_label(error_msg, "red")
		# 	self.transform_err = Msg(error_msg)
		# 	self.error(error_msg)
		# 	QMessageBox.critical(self, "Error", error_msg, QMessageBox.Ok)
		# 	# raise


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


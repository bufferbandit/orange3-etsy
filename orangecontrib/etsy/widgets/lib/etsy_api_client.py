import etsyv3.etsy_api
import urllib.parse
import socketserver
import http.server
import webbrowser
import threading
import requests
import datetime
import inspect
import logging
import hashlib
import urllib
import pprint
import base64
import random
import typing
import signal
import string
import types
import sched
import time
import json
import os
import re



from shared_memory_dict.serializers import PickleSerializer
from shared_memory_dict import SharedMemoryDict


class SharedMemDict(SharedMemoryDict):
	# Check if object is the oldest object
	#  This might become useful when maybe in the future a model will be added (todo?)
	#  that just replicates the eldest and does not allow attrs to be set on the children
	@property
	def is_eldest(self):
		# print(self.get("registered_client_ids", []))
		return self.id == min(self.get("registered_client_ids", []))

	attr_blacklist = {"_serializer", "_memory_block", "id", "name"}

	def __init__(self, size=1024, prefix="SyncedObject__", serializer=PickleSerializer(), *args, **kwargs):
		# Set the name of the "channel" to the class name
		self.name = prefix + self.__class__.__name__
		super().__init__(name=self.name, size=size, serializer=serializer, *args, **kwargs)
		registered_client_ids = self.get("registered_client_ids", [])
		# Create an id that is current max id + 1
		self.id = 0 if not registered_client_ids else (max(registered_client_ids) + 1)
		# "register" the id (by just adding it to the list)
		registered_client_ids.append(self.id)
		super().__setitem__("registered_client_ids", registered_client_ids)


	# When calling "del" on the object, remove the id from the ids
	def __del__(self):
		registered_client_ids = self["registered_client_ids"]
		del self["registered_client_ids"]

		registered_client_ids.remove(self.id)
		self["registered_client_ids"] = registered_client_ids

		self.shm.close()
		self.shm.unlink()

		super().__del__()

	def item_set_trigger(self):
		pass







class EtsyOAuth2Client(etsyv3.etsy_api.EtsyAPI):
	def __init__(self, api_token, host="0.0.0.0", port=5000,
	             auto_close_browser=True, auto_refresh_token=False,
	             verbose=True, auto_start_auth=True, scopes=None,
	             access_token=None, refresh_token=None, expiry=None,
	             reference_file_path="./api_reference.json"):

		self.shared_mem_dict = SharedMemDict()

		self.api_reference_json_file = open(
			reference_file_path, encoding="utf-8")
		self.api_reference_json = json.load(self.api_reference_json_file)

		# Construct and initialize the variables needed for the OAuth flow
		if scopes is None:
			scopes = ["address_r", "address_w", "billing_r", "cart_r", "cart_w",
			          "email_r", "favorites_r", "favorites_w", "feedback_r",
			          "listings_d", "listings_r", "listings_w", "profile_r",
			          "profile_w", "recommend_r", "recommend_w", "shops_r",
			          "shops_w", "transactions_r", "transactions_w"]
		self.auto_close_browser = auto_close_browser
		if not (existing_token := self.shared_mem_dict.get("api_token")):
			self.api_token = self.shared_mem_dict["access_token"] = api_token
		else:
			self.api_token = existing_token

		self.host = host
		self.port = port
		self.scopes = scopes

		self.refresh_token_timer = None
		self.auto_refresh_token = auto_refresh_token

		# Generate attributes needed for the OAuth flow
		self.scopes_urlencoded = "%20".join(self.scopes)
		self.base_url = f"http://{self.host}:{self.port}"
		self.code_verifier = self.base64_url_encode(os.urandom(32))
		self.state = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(7 - 1))
		self.code_challenge = self.base64_url_encode(hashlib.sha256(self.code_verifier.encode("utf-8")).digest())
		self.redirect_uri = self.base_url + "/callback"

		self.auto_start_auth = auto_start_auth
		self.verbose = verbose

		if self.auto_start_auth:
			if self.verbose: print("Getting access token")
			self.get_access_token()

			if self.verbose: print("Getting refresh token")
			self.get_refresh_token()

		# Initialize with wrong data, call constructor later again to update
		if not self.auto_start_auth:
			self.access_token = "None.None.None"
			self.refresh_token = "None.None.None"
			# self.expiry = None
			self.expiry = datetime.datetime.utcnow() + datetime.timedelta(microseconds=1)

		# Initialize base class variables
		super().__init__(
			keystring=self.api_token,
			token=self.access_token,
			refresh_token=self.refresh_token,
			expiry=self.expiry,
			refresh_save=None)


	def reference_opperation_to_function(self, method_obj, func="None #", prefix="from_api_reference_", **kwargs):
		if isinstance(func, (types.FunctionType, types.MethodType)): func = func.__name__
		# function string
		function_str = "def {prefix}{operationId}({args_str}{self}):return {func}(**locals())"
		# generate the function arguments signature
		type_translation = {
			"integer": "int",
			"float": "float",
			"boolean": "bool",
			"string": "str",
			"array": "list",
			"epoch": "datetime.datetime",
		}
		# convert all parameters to a list
		arguments_list = [parameter["name"] + ":" + type_translation.get(parameter["schema"]["type"], "typing.Any") +
		                  ("=None" if not parameter["required"] else "") for parameter in
		                  method_obj.get("parameters", [])]
		# add function kwargs to the arguments list as well
		arguments_list.extend(
			[f"{key}='{value}'" if isinstance(value, str) else f"{key}={value}"
			 for key, value in kwargs.items()])

		# convert the list to a string separated by commas
		arguments_string = arguments_string if (arguments_string := ",".join(arguments_list)) != "," else ""
		# eval and fill in the blanks
		exec_str = function_str.format(
			operationId=method_obj["operationId"],
			args_str=arguments_string,
			prefix=prefix,
			func=func,
			self=",self=self" if locals().get("self", None) else ""
		)
		exec(exec_str)
		function_name = prefix + method_obj["operationId"]
		function = locals()[function_name]
		return function, function_name

	def get_api_routes(self):
		for path, path_obj in self.api_reference_json["paths"].items():
			for method, method_obj in path_obj.items():
				function, function_name = self.reference_opperation_to_function(
					prefix="", method_obj=method_obj, func="self.make_request", path=path, method=method)
				yield function_name, path, function, list(
					set(inspect.signature(function).parameters) - set(["path", "method", "self"])), method.upper()

	def make_request(*args, **kwargs):
		path = kwargs.get("path", None)
		method = kwargs.get("method", None)

		if path: del kwargs["path"]
		if method: del kwargs["method"]

		if (self := kwargs.get("self", None)):
			del kwargs["self"]

		method_obj = self.api_reference_json["paths"][path][method]
		query_kwargs = {}
		request_payload = None
		# uri = etsyv3.etsy_api.ETSY_API_BASEURL.rstrip("/") + path
		uri = etsyv3.etsy_api.ETSY_API_BASEURL.rsplit("/",3)[0] + path
		# Loop through the paramters from the object
		for parameter in method_obj.get("parameters", []):
			parameter_name = parameter["name"]
			# See if the parameter is in the provided parameters
			kwarg_val = kwargs.get(parameter_name, None)
			# If so see where it belongs
			if kwarg_val:
				if parameter["in"] == "path":
					uri = uri.replace("{" + parameter_name + "}", str(kwarg_val))
				elif parameter["in"] == "query" and str(kwarg_val) != "None":
					query_kwargs[parameter_name] = kwarg_val
				elif parameter["in"] == "header":
					# TODO: process the header parameters
					pass
			# Otherwise check if they are required
			elif parameter["schema"].get("required", None):
				raise Exception(f"{parameter['name']} is required but not provided")

		if method == "post" or method == "put":
			request_payload = {}
			for request_body in method_obj.get("requestBody", []):
				# TODO: process the request body
				pass

		res = self._issue_request(uri, method=getattr(etsyv3.etsy_api.Method, method.upper()), request_payload=None, **query_kwargs)
		return res

	# Disable builtin refresh token method by overriding it
	def refresh(self):pass

	@classmethod
	def base64_url_encode(self, inp):
		return base64.b64encode(inp) \
			.decode("utf-8") \
			.replace("+", "-") \
			.replace("/", "_") \
			.replace("=", "")

	@property
	def auto_refresh_token(self):
		return self._auto_refresh_token

	@auto_refresh_token.setter
	def auto_refresh_token(self, value):
		if not value and self.refresh_token_timer is not None:
			if self.verbose: print("Cancelling refresh token timer")
			self.refresh_token_timer.cancel()
		self.refresh_token_timer = None
		self._auto_refresh_token = value

	def open_oauth_request(self):
		auth_url = f"https://www.etsy.com/oauth/connect" \
		           f"?response_type=code" \
		           f"&redirect_uri={self.redirect_uri}" \
		           f"&scope={self.scopes_urlencoded}" \
		           f"&client_id={self.api_token}" \
		           f"&state={self.state}" \
		           f"&code_challenge={self.code_challenge}" \
		           f"&code_challenge_method=S256"

		if self.verbose: print("Opening browser to authenticate url: " + auth_url)
		webbrowser.open(auth_url)

	def receive_oauth_callback(self):
		parent_context = self
		tokens = {}

		class OAuthServerHandler(http.server.BaseHTTPRequestHandler):
			def log_message(self, format, *args): pass

			def do_GET(self):
				nonlocal tokens
				self.send_response(200)
				self.send_header("Content-type", "text/html")
				self.end_headers()

				query_parameters = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
				parent_context.code = query_parameters["code"][0]
				parent_context.state = query_parameters["state"][0]

				# These can't make use of the requests.session object because it's not initialized yet
				res = requests.post("https://api.etsy.com/v3/public/oauth/token",
				        headers={"Content-Type": "application/json"}, json={
						"grant_type": "authorization_code",
						"client_id": parent_context.api_token,
						"redirect_uri": parent_context.redirect_uri,
						"code": parent_context.code,
						"code_verifier": parent_context.code_verifier
					})
				tokens = res.json()
				message = "Successfully retrieved tokens" if res.status_code == 200 \
					else "Failed to retrieve tokens"
				if parent_context.verbose: print(message, res.status_code, tokens)
				self.wfile.write(bytes(
					f"<html>"
						f"<body " + ("onload=window.top.close()" if {parent_context.auto_close_browser} else "") + ">"
							f"<h1>{message}</h1>"
							f"<p>{res.status_code}</p>"
							f"<pre>{json.dumps(tokens, indent=4)}</pre>"
						f"</body>"
					f"</html>", "utf-8"))
				self.server.server_close()
				return

		try:
			http.server.HTTPServer((self.host, self.port), OAuthServerHandler).serve_forever()
		except OSError:
			pass  # For some strange reason something still tries to write to the socket after closing server
		return tokens

	# Add token as an alias for access_token (for parrent class)
	@property
	def token(self):
		return self.access_token

	@token.setter  # needed to use a getter
	def token(self, value):
		# self.access_token = value
		pass

	def get_access_token(self):
		if self.shared_mem_dict.is_eldest:
			self.open_oauth_request()
			tokens = self.receive_oauth_callback()
			self.access_token = self.shared_mem_dict["access_token"] = tokens["access_token"]
			self.refresh_token = self.shared_mem_dict["refresh_token"] = tokens["refresh_token"]
			self.expires_in = self.shared_mem_dict["expires_in"] = tokens["expires_in"]
			self.expiry = self.shared_mem_dict["expiry"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.expires_in)

			if self.verbose: print("Expiry: " + str(self.expiry))
		else:
			self.access_token = self.shared_mem_dict["access_token"]
			self.refresh_token = self.shared_mem_dict["refresh_token"]
			self.expires_in = self.shared_mem_dict["expires_in"]
			self.expiry = self.shared_mem_dict["expiry"]


	def stop_auto_refreshing_token(self):
		self.auto_refresh_token = False

	def start_auto_refreshing_token(self):
		if self.refresh_token_timer: self.refresh_token_timer.cancel()
		self.refresh_token_timer = threading.Timer(int(self.expires_in), function=self.get_refresh_token)
		self.refresh_token_timer.start()
		if self.verbose: print("New timer started with interval", self.refresh_token_timer.interval)

	def get_refresh_token(self):
		if self.shared_mem_dict.is_eldest:
			# These can't make use of the requests.session object because it's not initialized yet
			res = requests.post("https://api.etsy.com/v3/public/oauth/token",
			                    headers={"Content-Type": "application/json"}, json={
					"grant_type": "refresh_token",
					"client_id": self.api_token,
					"refresh_token": self.refresh_token
				})
			tokens = res.json()

			self.access_token = self.shared_mem_dict["access_token"] = tokens["access_token"]
			self.refresh_token = self.shared_mem_dict["refresh_token"] = tokens["refresh_token"]
			self.expires_in = self.shared_mem_dict["expires_in"] = tokens["expires_in"]
			self.expiry = self.shared_mem_dict["expiry"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.expires_in)

			if self.verbose: print("Succesfully refreshed token", self.access_token, self.refresh_token, self.expires_in)
			if self.auto_refresh_token:
				self.start_auto_refreshing_token()
		else:
			self.access_token = self.shared_mem_dict["access_token"]
			self.refresh_token = self.shared_mem_dict["refresh_token"]
			self.expires_in = self.shared_mem_dict["expires_in"]
			self.expiry = self.shared_mem_dict["expiry"]



if __name__ == "__main__":
	AUTO_CLOSE_BROWSER = True
	AUTO_REFRESH_TOKEN = True
	AUTO_START_AUTH = True
	VERBOSE = True
	HOST = "localhost"
	PORT = 5000
	API_TOKEN = input("ADD YOUR API TOKEN ")
	client = EtsyOAuth2Client(
		api_token=API_TOKEN, host=HOST, port=PORT,
		auto_close_browser=AUTO_CLOSE_BROWSER,
		auto_refresh_token=AUTO_REFRESH_TOKEN,
		verbose=VERBOSE, auto_start_auth=AUTO_START_AUTH,
		reference_file_path=os.path.join(
			os.path.dirname(__file__), "..", "data", "api_reference.json"))
	print(client.ping())
	client.stop_auto_refreshing_token()

	routes = list(client.get_api_routes())
	client.get_api_routes()
	pprint.pprint(routes)

	func = __from_api_reference_getShop

	print(inspect.signature(func))
	res = func(shop_id=None)
	print("Response: ", res)

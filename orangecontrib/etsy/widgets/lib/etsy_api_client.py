import etsyv3.etsy_api
import urllib.parse
import socketserver
import http.server
import webbrowser
import threading
import requests
import datetime
import logging
import hashlib
import urllib
import pprint
import base64
import random
import signal
import string
import sched
import time
import json
import os
import re

AUTO_CLOSE_BROWSER = True
AUTO_REFRESH_TOKEN = True
AUTO_START_AUTH = True
VERBOSE = False
HOST = "localhost"
PORT = 5000

API_TOKEN = "ADD YOUR API TOKEN"


class EtsyOAuth2Client(etsyv3.etsy_api.EtsyAPI):
	def __init__(self, api_token, host="0.0.0.0", port=5000,
	             auto_close_browser=True, auto_refresh_token=False,
	             verbose=True, auto_start_auth=True, scopes=None,
	             access_token=None, refresh_token=None, expiry=None):

		# Construct and initialize the variables needed for the OAuth flow
		if scopes is None:
			scopes = ["address_r", "address_w", "billing_r", "cart_r", "cart_w",
			          "email_r", "favorites_r", "favorites_w", "feedback_r",
			          "listings_d", "listings_r", "listings_w", "profile_r",
			          "profile_w", "recommend_r", "recommend_w", "shops_r",
			          "shops_w", "transactions_r", "transactions_w"]
		self.auto_close_browser = auto_close_browser
		self.api_token = api_token
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
			keystring=api_token,
			token=self.access_token,
			refresh_token=self.refresh_token,
			expiry=self.expiry,
			refresh_save=None)

	# def __late__init(self, access_token, refresh_token, expiry):
	# 	self.access_token = access_token
	# 	self.refresh_token = refresh_token
	# 	self.expiry = expiry
	# 	# Initialize base class variables
	# 	super().__init__(
	# 		keystring=self.api_token,
	# 		token=self.access_token,
	# 		refresh_token=self.refresh_token,
	# 		expiry=self.expiry,
	# 		refresh_save=None)

	def get_api_routes(self):
		if self.verbose: print("Getting API routes")
		import inspect, typing
		for mtd in inspect.getmembers(self, predicate=inspect.ismethod):
			method_name, method = mtd
			# If function contains URI it's probably an API route
			if {"ETSY_API_BASEURL", "_issue_request"}\
					.issubset(set(method.__code__.co_names)) and not method_name in ["refresh","_issue_request"]:
				sc = inspect.getsource(method)
				stripped = sc.replace("\n","").strip()
				if uri := re.compile(r"(uri\s=\s).\"(.*?)\"").findall(stripped):
					uri_val = uri[0][1].replace(
						"{ETSY_API_BASEURL}", etsyv3.etsy_api.ETSY_API_BASEURL[:-1])
					# Regex that checks what word is behind Method.
					verb_pattern = re.compile(r"(Method\.)(\w+)").findall(stripped)
					try:verb = verb_pattern[0][1] if verb_pattern else "GET"
					except IndexError:verb = "GET"
					yield method_name, uri_val, method, list(inspect.signature(method).parameters), verb

	# Disable builtin refresh token method
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
		try:http.server.HTTPServer((self.host, self.port), OAuthServerHandler).serve_forever()
		except OSError:pass # For some strange reason something still tries to write to the socket after closing server
		return tokens


	# Add token as an alias for access_token (for parrent class)
	@property
	def token(self):
		return self.access_token

	@token.setter # needed to use a getter
	def token(self, value):
		# self.access_token = value
		pass

	def get_access_token(self):
		self.open_oauth_request()
		tokens = self.receive_oauth_callback()
		self.access_token = tokens["access_token"]
		self.refresh_token = tokens["refresh_token"]
		self.expires_in = tokens["expires_in"]
		self.expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.expires_in)

		if self.verbose:print("Expiry: " + str(self.expiry))

	def stop_auto_refreshing_token(self):
		self.auto_refresh_token = False

	def start_auto_refreshing_token(self):
		if self.refresh_token_timer: self.refresh_token_timer.cancel()
		self.refresh_token_timer = threading.Timer(int(self.expires_in), function=self.get_refresh_token)
		self.refresh_token_timer.start()
		if self.verbose: print("New timer started with interval", self.refresh_token_timer.interval)

	def get_refresh_token(self):
		# These can't make use of the requests.session object because it's not initialized yet
		res = requests.post("https://api.etsy.com/v3/public/oauth/token",
		    headers={"Content-Type": "application/json"}, json={
				"grant_type": "refresh_token",
				"client_id": self.api_token,
				"refresh_token": self.refresh_token
			})
		tokens = res.json()

		self.access_token = tokens["access_token"]
		self.refresh_token = tokens["refresh_token"]
		self.expires_in = tokens["expires_in"]
		self.expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.expires_in)


		if self.verbose: print("Succesfully refreshed token", self.access_token, self.refresh_token, self.expires_in)
		if self.auto_refresh_token:
			self.start_auto_refreshing_token()


if __name__ == "__main__":
	client = EtsyOAuth2Client(
		api_token=API_TOKEN, host=HOST, port=PORT,
		auto_close_browser=AUTO_CLOSE_BROWSER,
		auto_refresh_token=AUTO_REFRESH_TOKEN,
		verbose=VERBOSE, auto_start_auth=AUTO_START_AUTH)
	print(client.ping())
	client.stop_auto_refreshing_token()

	routes = list(client.get_api_routes())
	pprint.pprint(routes)


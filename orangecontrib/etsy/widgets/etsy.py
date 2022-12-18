import asyncio
import copy
import json
import os
import re
import sys
import textwrap
import traceback
from collections import ChainMap
from functools import partial

import pandas as pd
import qasync
from AnyQt import QtGui
from AnyQt.QtCore import Qt, QSize
from AnyQt.QtWidgets import QTableView, QLineEdit

from Orange.data import (
	Table, )
from Orange.widgets import gui
from Orange.widgets.settings import (
	Setting, ContextSetting
)
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import OWWidget, Output, Msg

from AnyQt import QtWidgets
from PyQt5.QtCore import QEventLoop
from PyQt5.QtWidgets import QTreeView, QInputDialog, QMessageBox, QSlider, QDoubleSpinBox, QComboBox, QAbstractItemView, \
	QCheckBox, QSpinBox, QLabel, QSpacerItem
from superqt import QLabeledRangeSlider

# from qtrangeslider import QLabeledRangeSlider

from orangecontrib.etsy.widgets.lib.etsy_api_client import EtsyOAuth2Client
from orangecontrib.etsy.widgets.lib.qjsonmodel import QJsonModel
from orangecontrib.etsy.widgets.lib.searchbar_helpers import SearchBarComboBox
from orangecontrib.etsy.widgets.lib.table_helpers import (
	CreateTableContextHandler,
	EditableTableItemDelegate, EditableTableModel, PandasModel)
from orangecontrib.etsy.widgets.lib.tabletest import PandasModel
from orangecontrib.etsy.widgets.lib.widgets_helper import WidgetsHelper, ElementTreeWidget, SetupHelper
from orangecontrib.etsy.widgets.lib.request_helper import RequestHelper


class OrangeEtsyApiInterface(OWWidget, SetupHelper, WidgetsHelper, RequestHelper):
	name = "Etsy API"
	description = "Orange widget for using the Etsy API and its data."
	icon = "icons/etsy_icon_round.svg"
	priority = 100
	keywords = ["Etsy", "API", "data", "web", "table"]

	DEBUG = False

	class Outputs:
		data = Output("Etsy API data", Table)

	class Error(OWWidget.Error):
		transform_err = Msg("Data does not fit to domain")

	settingsHandler = CreateTableContextHandler()
	DEFAULT_DATA = [[None] * 7 for y in range(20)]

	# since data is a small (at most 20x20) table we can afford to store it
	# as a context
	context_data = ContextSetting(copy.deepcopy(DEFAULT_DATA), schema_only=True)
	etsy_api_function_params = []

	search_items = []

	#
	ETSY_API_TOKEN = Setting(None)
	ETSY_AUTO_CLOSE_BROWSER = Setting(True)
	ETSY_AUTO_REFRESH_TOKEN = Setting(True)
	ETSY_AUTO_START_AUTH = Setting(False)
	ETSY_VERBOSE = Setting(False)
	ETSY_HOST = Setting("localhost")
	ETSY_PORT = Setting(5000)
	ETSY_API_CLIENT = Setting(None)

	def default(self, *args, **kwargs):
		message = "This is the default function. Please select a function from the dropdown."
		self.change_app_status_label(message)
		print(message)

	etsy_client_send_request = default
	# etsy_client_send_request = lambda *args,**kwargs:QMessageBox.warning(None,"Title", "This is the default function. Please select a function from the dropdown.")

	ETSY_API_CLIENT_SEND_REQUEST_ARGS = []
	ETSY_API_CLIENT_SEND_REQUEST_KWARGS = {}

	ETSY_ROUTES = []

	SELECT_RESULTS_ONLY_OUTPUT = Setting(True)
	FLATTEN_TABLE = Setting(False)
	SEQUENCE_REQUESTS = Setting(False)


	ETSY_API_RESPONSE = {}

	ETSY_API_RESPONSE_DF = None
	ETSY_API_RESPONSE_DF_MODEL = None

	DISPLAY_FLATTENED_TABLE = Setting(True)
	REMOVE_ORIGINAL_COLUMN = Setting(False)

	selected_methods = {
		"GET": True,
		"POST": False,
		"PUT": False,
		"DELETE": False,
	}

	df = None
	df_flattened = None
	df_json = None

	paginateLimitValue = Setting(100)

	etsy_request_offsets_and_limits = [(0,100)]

	request_lock = None

	offset_element = None
	limit_element = None

	sliderPosition = None




	def __init__(self):
		super().__init__()
		self.ETSY_API_CLIENT = EtsyOAuth2Client(
			api_token=self.ETSY_API_TOKEN,
			auto_close_browser=self.ETSY_AUTO_CLOSE_BROWSER,
			auto_refresh_token=self.ETSY_AUTO_REFRESH_TOKEN,
			auto_start_auth=self.ETSY_AUTO_START_AUTH,
			verbose=self.ETSY_VERBOSE,
			host=self.ETSY_HOST,
			port=self.ETSY_PORT
		)
		asyncio.set_event_loop(qasync.QEventLoop(self))
		self.loop = asyncio.get_event_loop()
		WidgetsHelper.__init__(self)
		RequestHelper.__init__(self)
		self.setup_ui()
		self.setup_custom_exception_hook()




	def setup_custom_exception_hook(self):
		def exception_hook(exctype, value, traceback):
			error_msg = f"Error: {exctype}: {value}"
			self.change_app_status_label(error_msg, "red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
			QMessageBox.critical(self, "Error", error_msg, QMessageBox.Ok)
			sys.__excepthook__(exctype, value, traceback)

		sys.excepthook = exception_hook

	def populate_data(self):
		if not self.ETSY_API_RESPONSE:
			QMessageBox.warning(self, "Warning", "No data available. Please send a request first.")
			return
		# if True: # self.df is not None:
		# show the button again
		self.refresh_data_button.show()

		self.enable_qgroupbox_and_color_title(self.flattenOptionsControlBox)

		# Populate tree view
		self.tree_model = QJsonModel()
		self.treeWidget.setModel(self.tree_model)
		self.tree_model.load(self.ETSY_API_RESPONSE)

		# Populate table view
		# self.df_json = pd.json_normalize(self.ETSY_API_RESPONSE)
		self.df_json = pd.DataFrame(self.ETSY_API_RESPONSE["results"])
		self.df = self.df_json

		if self.FLATTEN_TABLE:
			self.df_flattened = self.binarize_columns(self.df, self.REMOVE_ORIGINAL_COLUMN)
			self.df = self.df_flattened

		# Set table data
		model = PandasModel(self.df if self.DISPLAY_FLATTENED_TABLE
		                    else self.df_flattened)
		self.tableWidget.setModel(model)

		# Set output data
		table = self.pandas_to_orange(self.df)
		self.Outputs.data.send(table)

	def populate_search_box(self):
		self.ETSY_ROUTES = list(self.ETSY_API_CLIENT.get_api_routes())
		# method_name, uri_val, method, params, verb
		self.ETSY_ROUTES_DICT_METHOD_NAME_KEY = {route[0]: route for route in self.ETSY_ROUTES}
		self.ETSY_ROUTES_DICT_URL_KEY = {route[1]: route for route in self.ETSY_ROUTES}
		if self.ETSY_ROUTES:
			self.change_app_status_label("API routes successfully retrieved")
		self.searchBox.clear()
		# self.populate_search_box()

		# self.searchBox.clear()
		for route in self.ETSY_ROUTES:
			method_name, url, verb = route[0], route[1], route[4]
			if verb in [k for k, v in self.selected_methods.items() if v]:
				self.searchBox.addItem(f"[{verb}] {method_name} -> {url}")

	def setup_ui(self):

		def setup_search_box():
			nonlocal self
			self.searchBox = SearchBarComboBox(self.mainArea)

			def searchBoxCallback(bar_text):
				nonlocal self
				# bar_text = self.searchBox.currentText()
				method_name_regex = re.compile(r'\[(GET|POST|PUT|DELETE)\] ([a-zA-Z0-9_]+) ->')
				method_name_match = method_name_regex.match(bar_text)

				if method_name_match:
					method_name = method_name_match.group(2)
					self.CURR_SELECTED_METHOD_NAME, self.CURR_SELECTED_URI_VAL, self.CURR_SELECTED_METHOD, \
					self.CURR_SELECTED_METHOD_ARGS, self.CURR_SELECTED_VERB = self.ETSY_ROUTES_DICT_METHOD_NAME_KEY[
						method_name]

					self.etsy_client_send_request = self.CURR_SELECTED_METHOD

					# clear layouts
					self.clear_element(self.required_parameters_box)
					self.clear_element(self.optional_parameters_box)
					self.setup_arg_elements()

			self.searchBox.currentTextChanged.connect(searchBoxCallback)
			self.searchBox.show()
			self.populate_search_box()
			self.searchBox.setEnabled(False)


		def setup_sidebar():
			nonlocal self

			def setup_control_box():
				nonlocal self
				# Controls box
				self.controlBox = gui.vBox(self.controlArea, "Control")
				# Set alignment top
				self.controlBox.layout().setAlignment(Qt.AlignTop)
				self.controlArea.layout().setAlignment(Qt.AlignTop)
				# self.controlBox.setMinimumWidth(300)
				self.controlBox.setMaximumWidth(350)



			def setup_info_box():
				nonlocal self

				#### ETSY CLIENT OPTIONS
				self.etsyOptionsControlBox = gui.vBox(self.controlBox, "Etsy")


				self.etsy_options_tree = ElementTreeWidget()
				self.etsy_options_tree.set_top_level_element(QLabel("Etsy client options"))

				#  the above widgets but then as pyqt elements
				self.check_ETSY_AUTO_CLOSE_BROWSER = QCheckBox("Auto close browser")
				self.check_ETSY_AUTO_CLOSE_BROWSER.setChecked(self.ETSY_AUTO_CLOSE_BROWSER)
				# self.check_ETSY_AUTO_CLOSE_BROWSER.stateChanged.connect(self.on_check_ETSY_AUTO_CLOSE_BROWSER_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_CLOSE_BROWSER)
				# couple the checkbox to the setting
				self.check_ETSY_AUTO_CLOSE_BROWSER.stateChanged.connect(
					lambda: setattr(self, "ETSY_AUTO_CLOSE_BROWSER", self.check_ETSY_AUTO_CLOSE_BROWSER.isChecked()))
				self.etsy_options_tree.add_element(self.check_ETSY_AUTO_CLOSE_BROWSER)

				self.check_ETSY_AUTO_REFRESH_TOKEN = QCheckBox("Auto refresh token")
				self.check_ETSY_AUTO_REFRESH_TOKEN.setChecked(self.ETSY_AUTO_REFRESH_TOKEN)
				# self.check_ETSY_AUTO_REFRESH_TOKEN.stateChanged.connect(self.on_check_ETSY_AUTO_REFRESH_TOKEN_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_REFRESH_TOKEN)
				# couple the checkbox to the setting
				self.check_ETSY_AUTO_REFRESH_TOKEN.stateChanged.connect(
					lambda: setattr(self, "ETSY_AUTO_REFRESH_TOKEN", self.check_ETSY_AUTO_REFRESH_TOKEN.isChecked()))
				self.etsy_options_tree.add_element(self.check_ETSY_AUTO_REFRESH_TOKEN)

				# self.check_ETSY_AUTO_START_AUTH = QCheckBox("Auto start auth")
				# self.check_ETSY_AUTO_START_AUTH.setChecked(self.ETSY_AUTO_START_AUTH)
				# # self.check_ETSY_AUTO_START_AUTH.stateChanged.connect(self.on_check_ETSY_AUTO_START_AUTH_stateChanged)
				# # self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_START_AUTH)
				# # couple the checkbox to the setting
				# self.check_ETSY_AUTO_START_AUTH.stateChanged.connect(
				# 	lambda: setattr(self, "ETSY_AUTO_START_AUTH", self.check_ETSY_AUTO_START_AUTH.isChecked()))
				# self.etsy_options_tree.add_element(self.check_ETSY_AUTO_START_AUTH)

				self.check_ETSY_VERBOSE = QCheckBox("Log to stdout")
				self.check_ETSY_VERBOSE.setChecked(self.ETSY_VERBOSE)
				# self.check_ETSY_VERBOSE.stateChanged.connect(self.on_check_ETSY_VERBOSE_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_VERBOSE)
				# couple the checkbox to the setting
				self.check_ETSY_VERBOSE.stateChanged.connect(
					lambda: setattr(self, "ETSY_VERBOSE", self.check_ETSY_VERBOSE.isChecked()))
				self.etsy_options_tree.add_element(self.check_ETSY_VERBOSE)

				self.check_ETSY_HOST = QLineEdit("Host")
				self.check_ETSY_HOST.setText(self.ETSY_HOST)
				# self.check_ETSY_HOST.textChanged.connect(self.on_check_ETSY_HOST_textChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_HOST)
				# couple the checkbox to the setting
				self.check_ETSY_HOST.textChanged.connect(
					lambda: setattr(self, "ETSY_HOST", self.check_ETSY_HOST.text()))
				self.etsy_options_tree.add_element(
					self.build_element_with_label("Host", self.check_ETSY_HOST))

				self.check_ETSY_PORT = QSpinBox()
				self.check_ETSY_PORT.setMinimum(1)
				self.check_ETSY_PORT.setMaximum(65535)
				self.check_ETSY_PORT.setValue(self.ETSY_PORT)
				# self.check_ETSY_PORT.valueChanged.connect(self.on_check_ETSY_PORT_valueChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_PORT)
				# couple the checkbox to the setting
				self.check_ETSY_PORT.valueChanged.connect(
					lambda: setattr(self, "ETSY_PORT", self.check_ETSY_PORT.value()))

				self.etsy_options_tree.add_element(
					self.build_element_with_label("Port", self.check_ETSY_PORT))

				self.etsyOptionsControlBox.layout().addWidget(self.etsy_options_tree)

				# self.etsyOptionsControlBox.setFlat(False)

				self.check_ETSY_HOST.setAlignment(Qt.AlignTop)

				#### HTTP OPTIONS

				self.httpVerbsTreeMenu = ElementTreeWidget()
				self.httpVerbsTreeMenu.set_top_level_element(QLabel("HTTP verbs"))
				# self.httpVerbsTreeMenu.setEnabled(False)
				self.disable_qgroupbox_and_grayout_title(self.httpVerbsTreeMenu)

				def build_method_button(method):
					cb = QCheckBox(method)
					cb.setChecked(self.selected_methods[method])

					def on_cb_state_changed(state):
						self.selected_methods.update({method: state == Qt.Checked})
						self.searchBox.clear()
						self.populate_search_box()

					cb.stateChanged.connect(on_cb_state_changed)
					return cb

				# loop through the methods and add them to the tree
				for method in self.selected_methods.keys():
					method_cb = build_method_button(method)
					self.httpVerbsTreeMenu.add_element(method_cb)

				self.controlBox.layout().addWidget(self.httpVerbsTreeMenu)


				#### PAGINATE
				self.paginateOptionsControlBox = gui.vBox(self.controlBox, "Paginate")

				self.paginateOptionsControlBox.setMinimumHeight(500)

				# create a tree thats called sequnce tree and contains sliders with an editable box to set the number of requests to paginate
				self.paginateTreeMenu = ElementTreeWidget()
				self.disable_qgroupbox_and_grayout_title(self.paginateTreeMenu)
				self.check_SEQUENCE_REQUESTS = QCheckBox("Paginate requests")
				self.check_SEQUENCE_REQUESTS.setChecked(self.SEQUENCE_REQUESTS)

				self.paginateTreeMenu.set_top_level_element(self.check_SEQUENCE_REQUESTS)

				# Add some explaination text
				text = "To surpass the limit of 100 records in a single request, " \
				       "we can paginate our requests to the API by making multiple " \
				       "requests and combining the results into a single result. " \
				       "This is useful if we want to retrieve a large number of records from the API. " \
				       "By using a slider or other input, we can set the number of requests to paginate. " \
				       "The total number of results available for this call may be greater than the " \
				       "number of results returned in a single request. For example, if we want to" \
				       "retrieve 1000 records, we can page through the results in blocks of 100 by " \
				       "specifying a limit of 100 and an offset of 0, with the offset being a multiple " \
				       "of 100 up to 900. This allows us to retrieve all 1000 records by making multiple " \
				       "requests to the API."

				text_label = QLabel(text)
				text_label.setWordWrap(True)
				# text_label.setContentsMargins(10, 10, 10, 20)
				text_label.setEnabled(False)
				self.paginateTreeMenu.add_element(text_label)
				# text_label.setStyleSheet("QLabel:hover {color: black;text-decoration: none;}")

				self.paginateSlider = QLabeledRangeSlider()
				self.paginateSlider.setOrientation(Qt.Horizontal)
				self.paginateSlider.setRange(1, 1000)
				self.paginateSlider.setSliderPosition([1, self.paginateLimitValue])
				self.paginateSlider.setTickInterval(100)
				self.paginateSlider.setEnabled(False)

				# add a tooltip that explains the slider and shows the current values
				self.paginateSlider.setToolTip("To retrieve more than 100 records, paginate requests "
				                               "and combine results. Use slider to set number of requests. "
				                               "Example: to retrieve 1000 records, use limit=100&offset=0 with "
				                               "offset as multiple of 100 up to 900.")  # + str(self.SEQUENCE_REQUESTS_NUMBER))

				# self.paginateSlider.setFixedHeight(100)
				# self.paginateSlider.setFixedWidth(400)

				#### FLATTEN

				self.flattenOptionsControlBox = gui.vBox(self.controlBox, "Flatten")
				self.flattenOptionsControlBox.setEnabled(False)
				self.disable_qgroupbox_and_grayout_title(self.flattenOptionsControlBox)

				self.flattenTableTreeMenu = ElementTreeWidget()

				self.check_FLATTEN_TABLE = QCheckBox("Flatten table")
				self.check_FLATTEN_TABLE.setChecked(self.FLATTEN_TABLE)

				def flatten_table_callback(element):
					self.FLATTEN_TABLE = element.isChecked()
					if element.checkState() != Qt.PartiallyChecked:
						self.populate_data()

				self.check_FLATTEN_TABLE.stateChanged.connect(
					partial(flatten_table_callback, element=self.check_FLATTEN_TABLE))

				self.flattenTableTreeMenu.set_top_level_element(self.check_FLATTEN_TABLE)


				self.check_DISPLAY_FLATTENED_TABLE = QCheckBox("Display flattened table")
				self.check_DISPLAY_FLATTENED_TABLE.setChecked(self.DISPLAY_FLATTENED_TABLE)
				def check_DISPLAY_FLATTENED_TABLE_callback(element,):
					self.DISPLAY_FLATTENED_TABLE = self.check_DISPLAY_FLATTENED_TABLE.isChecked()
					self.populate_data()
				# self.check_DISPLAY_FLATTENED_TABLE.stateChanged.connect(self.populate_data)
				self.check_DISPLAY_FLATTENED_TABLE.stateChanged.connect(check_DISPLAY_FLATTENED_TABLE_callback)
				self.flattenTableTreeMenu.add_element(self.check_DISPLAY_FLATTENED_TABLE)

				self.check_REMOVE_ORIGINAL_COLUMN = QCheckBox("Remove original column")
				self.check_REMOVE_ORIGINAL_COLUMN.setChecked(self.REMOVE_ORIGINAL_COLUMN)
				def check_REMOVE_ORIGINAL_COLUMN_callback(element):
					self.REMOVE_ORIGINAL_COLUMN = self.check_REMOVE_ORIGINAL_COLUMN.isChecked()
					self.populate_data()
				# self.check_REMOVE_ORIGINAL_COLUMN.stateChanged.connect(self.populate_data)
				self.check_REMOVE_ORIGINAL_COLUMN.stateChanged.connect(check_REMOVE_ORIGINAL_COLUMN_callback)
				self.flattenTableTreeMenu.add_element(self.check_REMOVE_ORIGINAL_COLUMN)

				# self.flatten_table_tree = self.build_elements_tree(QCheckBox("Flatten table"), flatten_buttons)
				self.flattenOptionsControlBox.layout().addWidget(self.flattenTableTreeMenu)


				def dummy_request_function(offset,limit):
					base_url = "https://www.etsy.com/api/results"
					url = f"{base_url}?offset={offset}&limit={limit}"
					print(url)
					return {"results": [offset]}

				def test_pagination(_range, request_function, limit=100): # 25
					offsets_and_limits = []
					num_results = _range[1] - _range[0] + 1  # calculate the total number of results in the range
					num_pages = num_results // limit + 1  # calculate the total number of pages based on the pagination limit of 100 results per page
					for i in range(num_pages):
						offset = _range[0] + i * limit  # calculate the offset for the current page of results
						# if it's the last one and there's less then the limit number of results left, set the limit to the number of results left
						if i == num_pages - 1 and num_results % limit != 0:
							limit = num_results % limit
						offsets_and_limits.append((offset, limit))  # add the offset and limit to the list of offsets and limits
					return offsets_and_limits

				def on_slider_valueChanged(value):
					self.etsy_request_offsets_and_limits = test_pagination(_range=value,
					                request_function=dummy_request_function,
					                limit=self.paginateLimitValue)

				self.paginateSlider.valueChanged.connect(on_slider_valueChanged)

				paginateLimit = QSpinBox()
				paginateLimit.setRange(1, self.paginateLimitValue)
				paginateLimit.setValue(self.paginateLimitValue)

				self.paginateLimitLabelBox, self.paginateLimitLabel, self.paginateLimitSpinner \
					= self.build_element_with_label_layout(
					"Limit",
					paginateLimit,
					ret_all_elements=True
				)
				self.paginateLimitLabel.setEnabled(False)
				def paginateLimitSpinnerCallback(value):
					if self.sliderPosition:
						_min = self.sliderPosition.sliderPosition()[0]
						_max = (self.sliderPosition.sliderPosition()[0]) - 1 # + self.paginateLimitValue) - 1
					else:
						_min = 1
						_max = self.paginateLimitValue
					self.paginateSlider.setSliderPosition([_min,_max])
					setattr(self, "paginateLimitValue", value)

				self.paginateLimitSpinner.valueChanged.connect(paginateLimitSpinnerCallback)
				self.paginateLimitSpinner.setEnabled(False)

				self.paginateTreeMenu.add_element(QLabel(""))

				self.paginateTreeMenu.add_element(self.layout_to_element(self.paginateLimitLabelBox))

				self.paginateTreeMenu.add_element(QLabel(""))

				self.paginateTreeMenu.add_element(self.paginateSlider)
				self.paginateOptionsControlBox.layout().addWidget(self.paginateTreeMenu)

				def check_SEQUENCE_REQUESTS_callback(data):
					self.toggle_elements_enabled(
						[text_label, self.paginateSlider, self.paginateLimitSpinner, self.paginateLimitLabel])
					if self.check_SEQUENCE_REQUESTS.isChecked():
						if self.offset_element:
							self.offset_element.setEnabled(False)
						if self.limit_element:
							self.limit_element.setEnabled(False)
					else:
						if self.offset_element:
							self.offset_element.setEnabled(True)
						if self.limit_element:
							self.limit_element.setEnabled(True)


				self.check_SEQUENCE_REQUESTS.stateChanged.connect(check_SEQUENCE_REQUESTS_callback)


				self.refresh_data_button = gui.button(
					self.controlBox, self, "Reload existing data",
					callback=self.populate_data)
				self.refresh_data_button.hide()

				self.controlBox.resize(250, 250)

			def setup_settings_box():
				nonlocal self
				self.controlBox.layout().addSpacing(40)
				# Settings box
				self.required_parameters_box = gui.widgetBox(self.controlBox, "Required parameters")
				self.optional_parameters_box = gui.widgetBox(self.controlBox, "Optional parameters")
				if not self.etsy_api_function_params:
					# gui.widgetLabel(self.settings_box1, "No route selected. Please select a function.")
					self.required_parameters_box.layout().addSpacing(40)

					gui.widgetLabel(self.optional_parameters_box, "No route selected. Please select a function.")
					self.optional_parameters_box.layout().addSpacing(40)

				# Set the style of the box to the color gray only
				# "QGroupBox { border: 1px solid gray; border-radius: 9px; margin-top: 0.5em; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }"
				self.disable_qgroupbox_and_grayout_title(self.required_parameters_box)
				self.disable_qgroupbox_and_grayout_title(self.optional_parameters_box)

				self.required_parameters_box.setEnabled(False)
				self.optional_parameters_box.setEnabled(False)

			def setup_buttons_area():
				nonlocal self

				def showSetApiDialog():
					nonlocal self
					text, ok = QInputDialog.getText(self, "Set Etsy API token", "API Token: ", QLineEdit.Password)
					if ok:
						if text:
							self.ETSY_API_TOKEN = text
							self.onAuthenticated()
						else:
							QtWidgets.QMessageBox.warning(self, "Error", "API token cannot be empty")

				def debugFunc():
					nonlocal self
					self.ETSY_API_RESPONSE = json.loads(
						open(os.path.expanduser("~/debug_response.json"), encoding="utf8").read(), strict=False)
					self.change_http_status_label("-100 DEBUGGING", color="orange")
					self.populate_data()

				self.debugFunc = debugFunc

				if self.DEBUG:
					self.debugButton = gui.button(self.buttonsArea, self, "DBG data", callback=self.debugFunc)

				self.setTokenButton = gui.button(self.buttonsArea, self, "Authenticate", callback=showSetApiDialog)
				self.sendRequestButton = gui.button(self.buttonsArea, self, "Please authenticate")
				self.sendRequestButton.setEnabled(False)

			setup_control_box()
			setup_info_box()
			setup_settings_box()
			setup_buttons_area()




		def setup_content():
			nonlocal self
			self.mainAreaBox = gui.vBox(self.mainArea, True)

			def setup_table():
				nonlocal self
				# self.tableWidget = DataFrameWidget(self.tableTab)
				self.tableWidget = QTableView(self.tableTab)
				self.tableWidget.setItemDelegate(EditableTableItemDelegate())
				self.tableWidget.setEditTriggers(self.tableWidget.CurrentChanged)

				self.tableWidget.resizeColumnsToContents()
				self.tableWidget.resizeRowsToContents()
				self.tableWidget.horizontalHeader().setStretchLastSection(True)
				self.tableWidget.verticalHeader().setStretchLastSection(True)
				self.tableWidget.setEditTriggers(QTableView.NoEditTriggers)

				self.tableWidget.setSizePolicy(3, 3)

				font = QtGui.QFont()
				font.setPointSize(10)
				self.tableWidget.setFont(font)
				# set alternating row colors
				self.tableWidget.setAlternatingRowColors(True)

				# self.tableWidget.setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding)

				# Table model
				self.tableModel = EditableTableModel()
				self.tableWidget.setModel(self.tableModel)
				# self.tableModel.dataChanged.connect(self.data_changed)
				self.tableModel.set_table(self.context_data)

			def setup_tree():
				nonlocal self
				self.treeWidget = QTreeView(self.treeTab)
				self.treeWidget.expandAll()
				self.treeWidget.resizeColumnToContents(0)

			def setup_tabs():
				nonlocal self

				def setup_table_tab():
					nonlocal self
					self.tableTab = QtWidgets.QTabWidget()
					self.tableTabBox = gui.vBox(self.tableTab, True)
					self.tabWidget.addTab(self.tableTab, "Results table tab")

				def setup_tree_tab():
					nonlocal self
					self.treeTab = QtWidgets.QTabWidget()
					self.treeTabBox = gui.vBox(self.treeTab, True)
					self.tabWidget.addTab(self.treeTab, "Tree tab")

				self.tabWidget = QtWidgets.QTabWidget()
				self.tabWidget.setObjectName("tabWidget")

				setup_table_tab()
				setup_tree_tab()

				setup_table()
				setup_tree()

			setup_tabs()
			self.mainAreaBox.layout().addWidget(self.searchBox)
			self.mainAreaBox.layout().addWidget(self.tabWidget)

		def setup_statusbar():
			nonlocal self

			def setup_http_status(status, color="green"):
				nonlocal self
				# Content box
				self.content_box = gui.vBox(self.mainArea, True, margin=0)
				self.statusbarStatusLabel = gui.widgetLabel(self.statusBar(), label="HTTP Status: " + status)
				if color: self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			def setup_res_size_label(size, color="black"):
				nonlocal self
				self.statusbarResLabel = gui.widgetLabel(self.statusBar(), label="Response size: " + size)
				self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			def setup_app_status_label(status, color="black"):
				nonlocal self
				self.statusbarStatusLabel = gui.widgetLabel(self.statusBar(), label="Application Status: " + status)
				self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			def change_res_size_label(text, color="black"):
				nonlocal self
				self.statusbarResLabel.setText("Application Status: " + text)
				self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			def change_app_status_label(text, color="black"):
				nonlocal self
				self.statusbarStatusLabel.setText("Application Status: " + text)
				self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			def change_http_status_label(text, color="black"):
				nonlocal self
				self.statusbarStatusLabel.setText("Application Status: " + text)
				self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

			self.change_res_size_label = change_res_size_label
			self.change_app_status_label = change_app_status_label
			self.change_http_status_label = change_http_status_label

			setup_http_status("No requests", "black")
			setup_app_status_label("Ready")

		setup_statusbar()
		setup_sidebar()
		setup_search_box()
		setup_content()

	def onAuthenticated(self):
		self.change_app_status_label("API successfully set")
		self.setTokenButton.setText("Re-authenticate")
		self.sendRequestButton.setEnabled(True)
		self.sendRequestButton.setText("Send request")

		self.enable_qgroupbox_and_color_title(self.httpVerbsTreeMenu)
		self.enable_qgroupbox_and_color_title(self.paginateTreeMenu)

		# self.sendRequestButton.clicked.connect(lambda:
		# 	asyncio.run(asyncio.create_task(self.send_request())))

		self.sendRequestButton.clicked.connect(lambda:\
			self.loop.run_until_complete(self.send_request()))

		# self.sendRequestButton.clicked.connect(lambda:
		# 	asyncio.run(asyncio.create_task(self.send_request())))

		# self.sendRequestButton.clicked.connect(lambda: \
		# 	asyncio.create_task(self.send_request()))

		self.flattenOptionsControlBox.setEnabled(False)

		# self.ETSY_API_CLIENT = EtsyOAuth2Client(
		# Re-initialize the client with the new token
		self.ETSY_API_CLIENT.__init__(
			api_token=self.ETSY_API_TOKEN,
			auto_close_browser=self.ETSY_AUTO_CLOSE_BROWSER,
			auto_refresh_token=self.ETSY_AUTO_REFRESH_TOKEN,
			auto_start_auth=True,
			verbose=self.ETSY_VERBOSE,
			host=self.ETSY_HOST,
			port=self.ETSY_PORT
		)

		self.enable_qgroupbox_and_color_title(self.required_parameters_box)
		self.enable_qgroupbox_and_color_title(self.optional_parameters_box)

		self.searchBox.setEnabled(True)

	def exit(self):
		print("Called exit override")

	def resizeEvent(self, event):
		w = self.tableTab.width()
		h = self.tableTab.height()
		self.tableWidget.resize(w, h)
		self.treeWidget.resize(w, h)

	# self.tableWidget.resizeColumnsToContents()
	# self.tableWidget.resizeRowsToContents()

	@staticmethod
	def sizeHint():
		return QSize(800, 500)




if __name__ == "__main__":
	WidgetPreview(OrangeEtsyApiInterface).run()

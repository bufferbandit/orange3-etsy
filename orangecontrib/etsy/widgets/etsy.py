import copy
import json
import os
import re
import sys
import traceback
from functools import partial

import pandas as pd
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
from PyQt5.QtWidgets import QTreeView, QInputDialog, QMessageBox, QSlider, QDoubleSpinBox, QComboBox, QAbstractItemView, \
	QCheckBox, QSpinBox, QLabel

from orangecontrib.etsy.widgets.lib.etsy_api_client import EtsyOAuth2Client
from orangecontrib.etsy.widgets.lib.qjsonmodel import QJsonModel
from orangecontrib.etsy.widgets.lib.searchbar_helpers import SearchBarComboBox
from orangecontrib.etsy.widgets.lib.table_helpers import (
	CreateTableContextHandler,
	EditableTableItemDelegate, EditableTableModel, PandasModel)
from orangecontrib.etsy.widgets.lib.tabletest import PandasModel
from orangecontrib.etsy.widgets.lib.widgets_helper import WidgetsHelper, ElementTreeWidget
from orangecontrib.etsy.widgets.lib.request_helper import RequestHelper


class OrangeEtsyApiInterface(OWWidget, WidgetsHelper, RequestHelper):
	name = "Etsy API"
	description = "Orange widget for using the Etsy API and its data."
	icon = "icons/etsy_icon_round.svg"
	priority = 100
	keywords = ["Etsy", "API", "data", "web", "table"]

	DEBUG = 1

	class Outputs:
		data = Output("Etsy API data", Table)

	class Error(OWWidget.Error):
		transform_err = Msg("Data does not fit to domain")

	settingsHandler = CreateTableContextHandler()
	DEFAULT_DATA = [[None] * 6 for y in range(20)]

	# since data is a small (at most 20x20) table we can afford to store it
	# as a context
	context_data = ContextSetting(copy.deepcopy(DEFAULT_DATA), schema_only=True)
	etsy_api_function_params = []

	search_items = []

	#
	ETSY_API_TOKEN = Setting(None)
	ETSY_AUTO_CLOSE_BROWSER = Setting(True)
	ETSY_AUTO_REFRESH_TOKEN = Setting(True)
	ETSY_AUTO_START_AUTH = Setting(True)
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

	def __init__(self):
		super().__init__()
		WidgetsHelper.__init__(self)
		RequestHelper.__init__(self)
		self.setup_ui()
		self.setup_custom_exception_hook()

	def setup_custom_exception_hook(self):
		def exception_hook(exctype, value, traceback):
			error_msg = "Error: " + str(value)
			self.change_app_status_label(error_msg, "red")
			self.transform_err = Msg(error_msg)
			self.error(error_msg)
			QMessageBox.critical(self, "Error", str(value), QMessageBox.Ok)
			sys.__excepthook__(exctype, value, traceback)

		sys.excepthook = exception_hook

	def populateData(self):
		# if True: # self.df is not None:
		# show the button again
		self.refresh_data_button.show()

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

	def setup_ui(self):
		def setup_sidebar():
			nonlocal self

			def setup_control_box():
				nonlocal self
				# Controls box
				self.controlBox = gui.vBox(self.controlArea, "Control")
				# Set alignment top
				self.controlBox.layout().setAlignment(Qt.AlignTop)
				self.controlArea.layout().setAlignment(Qt.AlignTop)
				self.controlBox.setMinimumWidth(250)

			def setup_info_box():
				nonlocal self

				http_tree_menu = ElementTreeWidget()
				http_tree_menu.set_top_level_element(QLabel("HTTP verbs"))



				def build_method_button(method):
					cb = QCheckBox(method)
					cb.setChecked(self.selected_methods[method])
					cb.stateChanged.connect(lambda state: self.selected_methods.update({method: state == Qt.Checked}))
					return cb

				# loop through the methods and add them to the tree
				for method in self.selected_methods.keys():
					method_cb = build_method_button(method)
					http_tree_menu.add_element(method_cb)

				self.controlBox.layout().addWidget(http_tree_menu)


				self.etsyOptionsControlBox = gui.vBox(self.controlBox, "Etsy")

				# self.check_ETSY_AUTO_CLOSE_BROWSER = gui.checkBox(
				#         self.etsyOptionsControlBox, self,
				#         value="ETSY_AUTO_CLOSE_BROWSER",
				#         label="(Etsy) Auto close browser")
				#
				# self.check_ETSY_AUTO_REFRESH_TOKEN = gui.checkBox(
				#         self.etsyOptionsControlBox, self,
				#         value="ETSY_AUTO_REFRESH_TOKEN",
				#         label="(Etsy) Auto refresh token")
				#
				# self.check_ETSY_AUTO_START_AUTH = gui.checkBox(
				#         self.etsyOptionsControlBox, self,
				#         value="ETSY_AUTO_START_AUTH",
				#         label="(Etsy) Auto start auth")
				#
				# self.check_ETSY_VERBOSE = gui.checkBox(
				#         self.etsyOptionsControlBox, self,
				#         value="ETSY_VERBOSE",
				#         label="(Etsy) Log to stdout")
				#
				# self.check_ETSY_HOST = gui.lineEdit(
				#     self.etsyOptionsControlBox, self,
				#     value="ETSY_HOST",
				#     label="(Etsy) Host")
				#
				# # self.check_ETSY_HOST.setMaximumWidth(100)
				#
				# self.check_ETSY_PORT = gui.spin(
				#     self.etsyOptionsControlBox, self,
				#     minv=1, maxv=65535,
				#     value="ETSY_PORT",
				#     label="(Etsy) Port")

				etsy_options_tree = ElementTreeWidget()
				etsy_options_tree.set_top_level_element(QLabel("Etsy client options"))

				#  the above widgets but then as pyqt elements
				self.check_ETSY_AUTO_CLOSE_BROWSER = QCheckBox("Auto close browser")
				self.check_ETSY_AUTO_CLOSE_BROWSER.setChecked(self.ETSY_AUTO_CLOSE_BROWSER)
				# self.check_ETSY_AUTO_CLOSE_BROWSER.stateChanged.connect(self.on_check_ETSY_AUTO_CLOSE_BROWSER_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_CLOSE_BROWSER)
				# couple the checkbox to the setting
				self.check_ETSY_AUTO_CLOSE_BROWSER.stateChanged.connect(
					lambda: setattr(self, "ETSY_AUTO_CLOSE_BROWSER", self.check_ETSY_AUTO_CLOSE_BROWSER.isChecked()))
				etsy_options_tree.add_element(self.check_ETSY_AUTO_CLOSE_BROWSER)

				self.check_ETSY_AUTO_REFRESH_TOKEN = QCheckBox("Auto refresh token")
				self.check_ETSY_AUTO_REFRESH_TOKEN.setChecked(self.ETSY_AUTO_REFRESH_TOKEN)
				# self.check_ETSY_AUTO_REFRESH_TOKEN.stateChanged.connect(self.on_check_ETSY_AUTO_REFRESH_TOKEN_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_REFRESH_TOKEN)
				# couple the checkbox to the setting
				self.check_ETSY_AUTO_REFRESH_TOKEN.stateChanged.connect(
					lambda: setattr(self, "ETSY_AUTO_REFRESH_TOKEN", self.check_ETSY_AUTO_REFRESH_TOKEN.isChecked()))
				etsy_options_tree.add_element(self.check_ETSY_AUTO_REFRESH_TOKEN)

				self.check_ETSY_AUTO_START_AUTH = QCheckBox("Auto start auth")
				self.check_ETSY_AUTO_START_AUTH.setChecked(self.ETSY_AUTO_START_AUTH)
				# self.check_ETSY_AUTO_START_AUTH.stateChanged.connect(self.on_check_ETSY_AUTO_START_AUTH_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_AUTO_START_AUTH)
				# couple the checkbox to the setting
				self.check_ETSY_AUTO_START_AUTH.stateChanged.connect(
					lambda: setattr(self, "ETSY_AUTO_START_AUTH", self.check_ETSY_AUTO_START_AUTH.isChecked()))
				etsy_options_tree.add_element(self.check_ETSY_AUTO_START_AUTH)

				self.check_ETSY_VERBOSE = QCheckBox("Log to stdout")
				self.check_ETSY_VERBOSE.setChecked(self.ETSY_VERBOSE)
				# self.check_ETSY_VERBOSE.stateChanged.connect(self.on_check_ETSY_VERBOSE_stateChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_VERBOSE)
				# couple the checkbox to the setting
				self.check_ETSY_VERBOSE.stateChanged.connect(
					lambda: setattr(self, "ETSY_VERBOSE", self.check_ETSY_VERBOSE.isChecked()))
				etsy_options_tree.add_element(self.check_ETSY_VERBOSE)

				self.check_ETSY_HOST = QLineEdit("Host")
				self.check_ETSY_HOST.setText(self.ETSY_HOST)
				# self.check_ETSY_HOST.textChanged.connect(self.on_check_ETSY_HOST_textChanged)
				# self.etsyOptionsControlBox.layout().addWidget(self.check_ETSY_HOST)
				# couple the checkbox to the setting
				self.check_ETSY_HOST.textChanged.connect(
					lambda: setattr(self, "ETSY_HOST", self.check_ETSY_HOST.text()))
				etsy_options_tree.add_element(
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

				etsy_options_tree.add_element(
					self.build_element_with_label("Port", self.check_ETSY_PORT))

				self.etsyOptionsControlBox.layout().addWidget(etsy_options_tree)

				# self.etsyOptionsControlBox.setFlat(False)

				self.check_ETSY_HOST.setAlignment(Qt.AlignTop)

				self.flattenOptionsControlBox = gui.vBox(self.controlBox, "Flatten")

				self.flatten_table_tree = ElementTreeWidget()

				self.check_FLATTEN_TABLE = QCheckBox("Flatten table")
				self.check_FLATTEN_TABLE.setChecked(self.FLATTEN_TABLE)

				def flatten_table_callback(element):
					if element.checkState() != Qt.PartiallyChecked:
						self.populateData()

				self.check_FLATTEN_TABLE.stateChanged.connect(
					partial(flatten_table_callback, element=self.check_FLATTEN_TABLE))

				self.flatten_table_tree.set_top_level_element(self.check_FLATTEN_TABLE)

				self.check_DISPLAY_FLATTENED_TABLE = QCheckBox("Display flattened table")
				self.check_DISPLAY_FLATTENED_TABLE.setChecked(self.DISPLAY_FLATTENED_TABLE)
				self.check_DISPLAY_FLATTENED_TABLE.stateChanged.connect(self.populateData)
				self.flatten_table_tree.add_element(self.check_DISPLAY_FLATTENED_TABLE)

				self.check_REMOVE_ORIGINAL_COLUMN = QCheckBox("Remove original column")
				self.check_REMOVE_ORIGINAL_COLUMN.setChecked(self.REMOVE_ORIGINAL_COLUMN)
				self.check_REMOVE_ORIGINAL_COLUMN.stateChanged.connect(self.populateData)
				self.flatten_table_tree.add_element(self.check_REMOVE_ORIGINAL_COLUMN)

				# self.flatten_table_tree = self.build_elements_tree(QCheckBox("Flatten table"), flatten_buttons)

				self.flattenOptionsControlBox.layout().addWidget(self.flatten_table_tree)

				# # Flatten table checkbox
				# self.check_FLATTEN_TABLE = gui.checkBox(
				#         self.flattenOptionsControlBox, self, callback=self.flatten_table_callback,
				#         value="FLATTEN_TABLE",
				#         label="Flatten table")
				#
				# # Display flattened table checkbox
				# self.check_DISPLAY_FLATTENED_TABLE = gui.checkBox(
				#     self.flattenOptionsControlBox, self, callback=self.populateData,
				#     value="DISPLAY_FLATTENED_TABLE",
				#     label="(FLATTEN) Display flattened table")
				#
				# # REMOVE_ORIGINAL_COLUMN
				# self.check_REMOVE_ORIGINAL_COLUMN = gui.checkBox(
				#     self.flattenOptionsControlBox, self, callback=self.populateData,
				#     value="REMOVE_ORIGINAL_COLUMN",
				#     label="(FLATTEN) Remove original columns")

				# If flatten table is checked
				# if not self.check_FLATTEN_TABLE.isChecked():
				#     # Show the display flattened table checkbox
				#     self.check_DISPLAY_FLATTENED_TABLE.hide()
				#     self.check_REMOVE_ORIGINAL_COLUMN.hide()

				self.refresh_data_button = gui.button(
					self.controlBox, self, "Reload existing data",
					callback=self.populateData)
				self.refresh_data_button.hide()

				self.controlBox.resize(250, 250)

			def setup_settings_box():
				nonlocal self
				self.controlBox.layout().addSpacing(40)
				# Settings box
				self.settings_box1 = gui.widgetBox(self.controlBox, "Required parameters)")
				self.settings_box2 = gui.widgetBox(self.controlBox, "Optional parameters")
				if not self.etsy_api_function_params:
					gui.widgetLabel(self.settings_box1, "No route selected. Please select a function.")
					self.settings_box1.layout().addSpacing(40)

					gui.widgetLabel(self.settings_box2, "No route selected. Please select a function.")
					self.settings_box2.layout().addSpacing(40)

				# self.settings_box1.hide()
				# self.settings_box2.hide()

			def setup_buttons_area():
				nonlocal self

				def showSetApiDialog():
					nonlocal self
					text, ok = QInputDialog.getText(self, "Set Etsy API token", "API Token: ", QLineEdit.Password)
					if ok:
						if text:
							self.ETSY_API_TOKEN = text
							self.change_app_status_label("API successfully set")
							self.setTokenButton.setText("Re-authenticate")
							self.sendRequestButton.setEnabled(True)
							self.sendRequestButton.setText("Send request")

							self.sendRequestButton.clicked.connect(self.dispatch_request)

							self.ETSY_API_CLIENT = EtsyOAuth2Client(
								api_token=self.ETSY_API_TOKEN,
								auto_close_browser=self.ETSY_AUTO_CLOSE_BROWSER,
								auto_refresh_token=self.ETSY_AUTO_REFRESH_TOKEN,
								auto_start_auth=self.ETSY_AUTO_START_AUTH,
								verbose=self.ETSY_VERBOSE,
								host=self.ETSY_HOST,
								port=self.ETSY_PORT
							)
							self.ETSY_ROUTES = list(self.ETSY_API_CLIENT.get_api_routes())
							# method_name, uri_val, method, params, verb
							self.ETSY_ROUTES_DICT_METHOD_NAME_KEY = {route[0]: route for route in self.ETSY_ROUTES}
							self.ETSY_ROUTES_DICT_URL_KEY = {route[1]: route for route in self.ETSY_ROUTES}
							if self.ETSY_ROUTES:
								self.change_app_status_label("API routes successfully retrieved")
							self.searchBox.clear()
							for route in self.ETSY_ROUTES:
								method_name, url, verb = route[0], route[1], route[4]
								# Only using GET routes for now
								if 1:  # verb == "GET":
									self.searchBox.addItem(f"[{verb}] {method_name} -> {url}")
						else:
							QtWidgets.QMessageBox.warning(self, "Error", "API token cannot be empty")

				def debugFunc():
					nonlocal self
					self.ETSY_API_RESPONSE = json.loads(
						open(os.path.expanduser("~/debug_response.json"), encoding="utf8").read(), strict=False)
					self.change_http_status_label("-100 DEBUGGING", color="orange")
					self.populateData()

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

			def setup_search_box():
				nonlocal self
				self.searchBox = SearchBarComboBox(self.mainArea)

				def searchBoxCallback(index):
					nonlocal self
					bar_text = self.searchBox.currentText()
					method_name_regex = re.compile(r'\[(GET|POST|PUT|DELETE)\] ([a-zA-Z0-9_]+) ->')
					method_name_match = method_name_regex.match(bar_text)
					method_name = method_name_match.group(2)

					self.CURR_SELECTED_METHOD_NAME, self.CURR_SELECTED_URI_VAL, self.CURR_SELECTED_METHOD, \
					self.CURR_SELECTED_METHOD_ARGS, self.CURR_SELECTED_VERB = self.ETSY_ROUTES_DICT_METHOD_NAME_KEY[
						method_name]

					self.etsy_client_send_request = self.CURR_SELECTED_METHOD

					# clear layouts
					self.clear_element(self.settings_box1)
					self.clear_element(self.settings_box2)

					def setup_arg_elements():
						nonlocal self
						for arg_name in self.CURR_SELECTED_METHOD_ARGS:
							parameter = self.parameters[arg_name]

							parent = self.settings_box1 if parameter["required"] \
								else self.settings_box2

							def elementCallback(data, widget=None):
								nonlocal self
								widget_name = widget.objectName()
								self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS[widget_name] = data

							element, label = self.build_pyqt_element_from_parameter(arg_name, elementCallback)
							parent.layout().addWidget(label)
							parent.layout().addWidget(element)

					setup_arg_elements()

				self.searchBox.currentIndexChanged.connect(searchBoxCallback)
				self.searchBox.show()

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

			setup_search_box()
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

		setup_sidebar()
		setup_content()
		setup_statusbar()

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

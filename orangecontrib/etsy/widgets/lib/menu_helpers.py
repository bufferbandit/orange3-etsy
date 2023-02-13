from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import *



class TaxonomyMenu(QMenu):
	def __init__(self, *args, results, parrent_button=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.parrent_button = parrent_button
		self.resize( self.sizeHint().width(), 
		             self.sizeHint().height())
		
		self.traverse(results, self, self)
	
	def on_menu_item_clicked(self, *args, **kwargs):
		element = self.sender()
		title = f"{element.taxonomy_name} ({element.taxonomy_id})"
		self.setTitle(title)
		self.resize(
			self.sizeHint().width(),
			self.sizeHint().height())
		if self.parrent_button:
			self.parrent_button.taxonomy_id = element.taxonomy_id
			self.parrent_button.taxonomy_name = element.taxonomy_name
			self.parrent_button.taxonomy_level = element.taxonomy_level
			self.parrent_button.taxonomy_full_path_taxonomy_ids = element.taxonomy_full_path_taxonomy_ids
			# self.parrent_button.taxonomy_children = element.taxonomy_children
			self.parrent_button.setText(title)
			self.parrent_button.setObjectName("taxonomy_button_" + element.taxonomy_name)
			self.parrent_button.resize(
				self.parrent_button.sizeHint().width(),
				self.parrent_button.sizeHint().height())
		

	def traverse(self, results, parent_menu, original_menu):
		for child in results:
			taxonomy_id = child["id"]
			taxonomy_name = child["name"]
			taxonomy_level = child["level"]
			taxonomy_full_path_taxonomy_ids = child["full_path_taxonomy_ids"]
			taxonomy_children = child["children"]
			if taxonomy_children:
				title = f"{taxonomy_name} ({taxonomy_id}, ({taxonomy_full_path_taxonomy_ids})"
				# title = f"{taxonomy_id} {taxonomy_name}"
				sub_menu = parent_menu.addMenu(taxonomy_name)
				sub_menu.taxonomy_id = taxonomy_id
				sub_menu.taxonomy_name = taxonomy_name
				sub_menu.taxonomy_level = taxonomy_level
				sub_menu.taxonomy_full_path_taxonomy_ids = taxonomy_full_path_taxonomy_ids

				sub_menu.aboutToShow.connect(self.on_menu_item_clicked)
				self.traverse(taxonomy_children, sub_menu, original_menu)
			else:
				title = f"{taxonomy_name} ({taxonomy_id})"
				# title = f"{taxonomy_id} {taxonomy_name}"
				menu_node = parent_menu.addAction(taxonomy_name)
				menu_node.taxonomy_id = taxonomy_id
				menu_node.taxonomy_name = taxonomy_name
				menu_node.taxonomy_level = taxonomy_level
				menu_node.taxonomy_full_path_taxonomy_ids = taxonomy_full_path_taxonomy_ids
				
				menu_node.triggered.connect(self.on_menu_item_clicked)

class TaxonomyMenuButton(QPushButton):
	def __init__(self, *args, title, results, **kwargs):
			if(kwargs.get("results")): del kwargs["results"]

			self.taxonomy_id = None
			self.taxonomy_name = None
			self.taxonomy_level = None
			self.taxonomy_full_path_taxonomy_ids = None


			super().__init__(*args, **kwargs)
			self.menu = TaxonomyMenu(results=results,parrent_button=self)
			self.setMenu(self.menu)
			self.menu.setTitle(title)
			self.setText(title)
			self.resize(
				self.sizeHint().width(),
				self.sizeHint().height())
		
		


if __name__ == "__main__":
	class MainWindow(QMainWindow):
		def __init__(self):
			super().__init__()
			self.openMenuButton = TaxonomyMenuButton(self,
					title="Taxonomy", results=results)

			def rec(*args, **kwargs):
				sender = self.sender()
				print(args, kwargs)

			self.openMenuButton.objectNameChanged.connect(rec)


	import sys
	app = QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec_())
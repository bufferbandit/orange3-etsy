#!/usr/bin/env python

from os import path, walk
from setuptools import setup, find_packages

NAME = "Orange3-Etsy"

VERSION = "987.3215.6431"

DESCRIPTION = "Orange widget for using the Etsy API and its data."


KEYWORDS = (
    # [PyPi](https://pypi.python.org) packages with keyword "orange3 add-on"
    # can be installed using the Orange Add-on Manager
    'orange3 add-on',
)

PACKAGES = find_packages()

PACKAGE_DATA = {
    # 'orangecontrib.etsy': ['tutorials/*.ows'],
    'orangecontrib.etsy.widgets': ['icons/*'],
}

DATA_FILES = [
    # Data files that will be installed outside site-packages folder
]

INSTALL_REQUIRES = [
    'Orange3 >=3.31.1',
    'BeautifulSoup4',
    'requests',
    'numpy',
]

# EXTRAS_REQUIRE = {
#     'doc': ['sphinx', 'recommonmark', 'sphinx_rtd_theme'],
#     'test': ['coverage'],
# }

ENTRY_POINTS = {
    # Entry points that marks this package as an orange add-on. If set, addon will
    # be shown in the add-ons manager even if not published on PyPi.
    'orange3.addon': (
        'etsy = orangecontrib.etsy',
    ),
    # Entry point used to specify packages containing tutorials accessible
    # from welcome screen. Tutorials are saved Orange Workflows (.ows files).
    # 'orange.widgets.tutorials': (
    #     # Syntax: any_text = path.to.package.containing.tutorials
    #     'educationaltutorials = orangecontrib.etsy.tutorials',
    # ),

    # Entry point used to specify packages containing widgets.
    'orange.widgets': (
        # Syntax: category name = path.to.package.containing.widgets
        # Widget category specification can be seen in
        #    orangecontrib/example/widgets/__init__.py
        'Api = orangecontrib.etsy.widgets',
    ),

    # Register widget help
    "orange.canvas.help": (
        'html-index = orangecontrib.etsy.widgets:WIDGET_HELP_PATH',)
}

NAMESPACE_PACKAGES = ["orangecontrib"]

def include_documentation(local_dir, install_dir):
    global DATA_FILES

    doc_files = []
    for dirpath, _, files in walk(local_dir):
        doc_files.append((dirpath.replace(local_dir, install_dir),
                          [path.join(dirpath, f) for f in files]))
    DATA_FILES.extend(doc_files)


if __name__ == '__main__':
    include_documentation('doc/_build/html', 'help/orange3-etsy')
    setup(
        name=NAME,
        version=VERSION,
        description=DESCRIPTION,
        packages=PACKAGES,
        package_data=PACKAGE_DATA,
        data_files=DATA_FILES,
        entry_points=ENTRY_POINTS,
        keywords=KEYWORDS,
        namespace_packages=NAMESPACE_PACKAGES,
        include_package_data=True,
        zip_safe=False,
    )

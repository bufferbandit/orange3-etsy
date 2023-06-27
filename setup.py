#!/usr/bin/env python

from setuptools import setup, find_packages

NAME = "Orange3-Etsy"

VERSION = "1.30.0"

DESCRIPTION = "Orange widget for using the Etsy API and its data."

KEYWORDS = [
    # [PyPi](https://pypi.python.org) packages with keyword "orange3 add-on"
    # can be installed using the Orange Add-on Manager
    "orange3 add-on",
]

PACKAGES = find_packages()

PACKAGE_DATA = {
    "orangecontrib.etsy.widgets": ["icons/*"],
}

DATA_FILES = [
    # Data files that will be installed outside site-packages folder
]

INSTALL_REQUIRES = [
    # "Orange3 >=3.31.1",
    "BeautifulSoup4",
    "python-linq",
    "requests",
    "superqt",
    "qasync",
    "etsyv3",
    "numpy",
]

ENTRY_POINTS = {
    # Entry points that marks this package as an orange add-on. If set, addon will
    # be shown in the add-ons manager even if not published on PyPi.
    "orange3.addon": (
        "etsy = orangecontrib.etsy",
    ),
    # Entry point used to specify packages containing tutorials accessible
    # from welcome screen. Tutorials are saved Orange Workflows (.ows files).
    # "orange.widgets.tutorials": (
    #     # Syntax: any_text = path.to.package.containing.tutorials
    #     "educationaltutorials = orangecontrib.etsy.tutorials",
    # ),

    # Entry point used to specify packages containing widgets.
    "orange.widgets": (
        # Syntax: category name = path.to.package.containing.widgets
        # Widget category specification can be seen in
        #    orangecontrib/example/widgets/__init__.py
        "Api = orangecontrib.etsy.widgets",
    )
}

NAMESPACE_PACKAGES = ["orangecontrib"]

if __name__ == "__main__":
    setup(
        name=NAME,
        description=DESCRIPTION,
        version=VERSION,
        package_data=PACKAGE_DATA,
        install_requires=INSTALL_REQUIRES,
        packages=PACKAGES,
        data_files=DATA_FILES,
        entry_points=ENTRY_POINTS,
        keywords=KEYWORDS,
        namespace_packages=NAMESPACE_PACKAGES,
        include_package_data=True,
        zip_safe=False
    )

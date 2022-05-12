# -*- coding: utf-8 -*-
import os

from setuptools import find_packages, setup

from misago import __version__ as version

SETUP_DIR = os.path.dirname(__file__)

with open(os.path.join(SETUP_DIR, "README.md"), "r", encoding="utf-8") as f:
    README = f.read()

with open(os.path.join(SETUP_DIR, "requirements.txt"), "r", encoding="utf-8") as f:
    REQUIREMENTS = f.read()


# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="Misago",
    version=version,
    license="GPLv2",
    description=(
        "Misago is modern, fully featured forum application written in "
        "Python and ES6, powered by Django and React.js. It works out of "
        "the box and plays nicely with other projects like Django-CMS."
    ),
    long_description=README,
    long_description_content_type="text/markdown",
    url="http://www.misago-project.org/",
    author="Rafał Pitoń",
    author_email="kontakt@rpiton.com",
    install_requires=REQUIREMENTS,
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)

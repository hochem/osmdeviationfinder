#  -*- coding: utf-8 -*-
"""
    OSM Deviation Finder - Web Interface
    ~~~~~~~~~~~~~~~~~~~~

    Implementation of a web interface for the OSM Deviation Finder library.
    It uses the flask microframework by Armin Ronacher
    For more information see https://github.com/mitsuhiko/flask/

    To interact with the GeoServer REST API, the GeoServer configuration client library by boundlessgeo is used, see:
    https://github.com/boundlessgeo/gsconfig

     On the client side it uses jquery.js, leaflet.js, nprogress.js, DataTables and the UIKit framework,
     for further information see the README.md file.

    :copyright: (c) 2015 by Martin Hochenwarter
    :license:  MIT
"""

__author__ = 'martin'

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager

app = Flask(__name__,static_url_path='/static')
app.config.from_object(__name__)
app.config.update(dict(
    SQLALCHEMY_DATABASE_URI='postgresql://odf@localhost/odf',
    DEBUG=True,
    SECRET_KEY='development key',
    USERNAME='admin',
    PASSWORD='admin'
))

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
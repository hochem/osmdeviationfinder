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

from web import db
from web.models import User


def refresh():
    """Function to refresh database
    """
    db.drop_all()
    db.create_all()
    user = User('admin', 'admin', 'admin')
    user.role = 1
    db.session.add(user)
    user = User('Guest', 'none', 'none')
    db.session.add(user)
    db.session.commit()
    exit()
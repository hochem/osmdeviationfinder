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

import os
basedir = os.path.abspath(os.path.dirname(__file__))
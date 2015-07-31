#  -*- coding: utf-8 -*-
"""
    OSM Deviation Finder - Web Interface
    ~~~~~~~~~~~~~~~~~~~~

    Implementation of a web interface for the OSM Deviation Finder library.
    It uses the flask microframework by Armin Ronacher
    For more information see https://github.com/mitsuhiko/flask/

    To interact with the GeoServer REST API, the GeoServer configuration client library by boundlessgeo is used, see:
    https://github.com/boundlessgeo/gsconfig

     On the client side it uses jquery.js, leaflet.js, nprogress.js and the UIKit framework, for further information
     see the README.md file.

    :copyright: (c) 2015 by Martin Hochenwarter
    :license:  MIT
"""

__author__ = 'Martin Hochenwarter'
__version__ = '0.1'

from web import db
from models import DevMap
from flask import Blueprint, jsonify, make_response
from flask.ext.login import (current_user, login_required)
from functools import wraps, update_wrapper
from datetime import datetime
#: Blueprint for geojson requests used by leaflet.js to load map data
geojsonapi = Blueprint('geojsonapi', __name__, template_folder='templates')


def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Last-Modified'] = datetime.now()
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return update_wrapper(no_cache, view)


@geojsonapi.route('/listed/geojson', methods=['GET'])
@nocache
def listedbboxes():
    """Returns all bounding polygons of listed maps as geojson, if none are found an error is returend.
    This can used to display the boundings of listed maps in a leaflet.js map an the front- and browse-page
    """
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f.boundsyx)) As features '
                             'FROM (SELECT boundsyx, title, datasource, datalicense '
                             'FROM dev_map where listed=true) As f ) As fc;').fetchone()
    if data[0]['features'] is not None:
        return jsonify(data[0])
    else:
        message = {
            'status': 404,
            'message': 'Not Found',
        }
        resp = jsonify(message)
        resp.status_code = 404
        return resp


@geojsonapi.route('/manage/geojson', methods=['GET'])
@nocache
@login_required
def managebboxes():
    """Returns all bounding polygons of the deviation maps of the currently logged in user as geojson.
    If the user is admin, the bounding polygons of all deviationsmaps in the database are returend as geojson.
    If no deviation maps are found an error is returend.
    This can used to display the boundings of the deviation maps of the current user / all users (admin) in
    a leaflet.js map on the manage page.
    """
    if current_user.is_authenticated():
        if current_user.role == 1:  # Admin
            data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f.boundsyx)) As features '
                             'FROM (SELECT boundsyx FROM dev_map) As f) As fc;').fetchone()
        else:
            data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f.boundsyx)) As features '
                             'FROM (SELECT boundsyx FROM dev_map '
                             'WHERE dev_map.user_id = '+str(current_user.id)+') As f) As fc;').fetchone()

        if data[0]['features'] is not None:
            return jsonify(data[0])
        else:
            message = {
                'status': 404,
                'message': 'Not Found',
            }
            resp = jsonify(message)
            resp.status_code = 404
            return resp


@geojsonapi.route('/<uid>/geojson/boundsxy', methods=['GET'])
@nocache
def boundsxy(uid):
    """Returns the boundig polygon in XY format (used by overpass) of the current map with uid <uid> as geojson
    """
    uid = uid.encode('ISO-8859-1')
    dm = DevMap.query.filter_by(uid=uid).first()
    bounds = dm.boundsxy
    return jsonify(bounds)

@geojsonapi.route('/<uid>/geojson/boundsyx', methods=['GET'])
@nocache
def boundsyx(uid):
    """Returns the boundig polygon in YX format (used by leaflet) of the current map with uid <uid> as geojson
    """
    uid = uid.encode('ISO-8859-1')
    dm = DevMap.query.filter_by(uid=uid).first()
    bounds = dm.boundsyx
    return jsonify(bounds)

@geojsonapi.route('/<uid>/geojson/reference', methods=['GET'])
@nocache
def referencelines(uid):
    """Returns the original reference lines and their id as geojson.
    This can used to display the original reference lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id) As l)) As properties '
                             'FROM odf_'+uid+'_ref As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/osm', methods=['GET'])
@nocache
def osmlines(uid):
    """Returns the original osm lines and their id as geojson.
    This can used to display the original osm lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id) As l)) As properties '
                             'FROM odf_'+uid+'_osm As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/referencesplitted', methods=['GET'])
@nocache
def referencesplitted(uid):
    """Returns the harmoized reference lines and their id, parent_id and name as geojson.
    This can used to display the original reference lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id, old_id, name) As l)) As properties '
                             'FROM odf_'+uid+'_ref_splitted As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/osmsplitted', methods=['GET'])
@nocache
def osmsplitted(uid):
    """Returns the harmoized osm lines and their id, osm_id and name as geojson.
    This can used to display the harmoized osm lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id, osm_id, name) As l)) As properties '
                             'FROM odf_'+uid+'_osm_splitted As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/referencematched', methods=['GET'])
@nocache
def referencematched(uid):
    """Returns the harmoized and matched reference lines and their id, parentid and name as geojson.
    This can used to display the original reference lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id, old_id, name) As l)) As properties '
                             'FROM odf_'+uid+'_ref_splitted As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/osmmatched', methods=['GET'])
@nocache
def osmmatched(uid):
    """Returns the harmoized and matched osm lines and their id, osm_id and name as geojson.
    This can used to display the harmoized osm lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features '
                             'FROM (SELECT \'Feature\' As type, ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id, osm_id, name) As l)) As properties '
                             'FROM odf_'+uid+'_osm_splitted As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/deviationlines', methods=['GET'])
@nocache
def deviationlines(uid):
    """Returns the deviation lines generated as result and their deviation attribute as geojson.
    This can be used to display the original reference lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features FROM (SELECT \'Feature\' As type, '
                             'ST_AsGeoJSON(lg.geom)::json As geometry, row_to_json((SELECT l '
                             'FROM (SELECT fit) As l)) As properties '
                             'FROM odf_'+uid+'_posdevlines As lg) As f) As fc;').fetchone()
    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/referencejunctions', methods=['GET'])
@nocache
def referencejunctions(uid):
    """Returns the genereated reference junction points as geojson.
    This can be used to display the generated reference junction points in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    try:
        data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features FROM (SELECT \'Feature\' As type, '
                             'ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id) As l)) As properties '
                             'FROM odf_'+uid+'_ref_junctions As lg ) As f )  As fc;').fetchone()
    except Exception:
        message = {
            'status': 404,
            'message': 'Not Found',
        }
        resp = jsonify(message)
        resp.status_code = 404
        return resp

    return jsonify(data[0])


@geojsonapi.route('/<uid>/geojson/osmjunctions', methods=['GET'])
@nocache
def osmjunctions(uid):
    """Returns the generated osm junction points as geojson.
    This can be used to display the generated osm junction points in a leaflet.js map.
    """
    try:
        data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features FROM (SELECT \'Feature\' As type, '
                             'ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id) As l)) As properties '
                             'FROM odf_'+uid+'_osm_junctions As lg ) As f )  As fc;').fetchone()
    except Exception:
        message = {
            'status': 404,
            'message': 'Not Found',
        }
        resp = jsonify(message)
        resp.status_code = 404
        return resp

    if data[0]['features'] is not None:
        return jsonify(data[0])
    else:
        message = {
            'status': 404,
            'message': 'Not Found',
        }
        resp = jsonify(message)
        resp.status_code = 404
        return resp


@geojsonapi.route('/<uid>/geojson/junctiondeviationlines', methods=['GET'])
@nocache
def junctiondeviationlines(uid):
    """Returns the genereated junction deviation lines as geojson.
    This can be used to display junction deviation lines in a leaflet.js map.
    """
    uid = uid.encode('ISO-8859-1')
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT \'FeatureCollection\' As type, '
                             'array_to_json(array_agg(f)) As features FROM (SELECT \'Feature\' As type, '
                             'ST_AsGeoJSON(lg.geom)::json As geometry, '
                             'row_to_json((SELECT l FROM (SELECT id) As l)) As properties '
                             'FROM odf_'+uid+'_junction_devlines As lg ) As f )  As fc;').fetchone()
    return jsonify(data[0])
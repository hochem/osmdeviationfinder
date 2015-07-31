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

from web import db, app
from flask import Blueprint, jsonify
from flask.ext.login import (current_user, login_required)

#: Blueprint for json requests used by DataTables (json)
jsonapi = Blueprint('jsonapi', __name__, template_folder='templates')


@jsonapi.route('/listed/json', methods=['GET'])
def listed():
    """Returns all listed deviation maps and their attributes as json, if none are found an empty object is returned.
    It is used to display information about listed deviation maps in a DataTables table on the browse page
    """
    data = db.engine.execute('SELECT row_to_json(fc) FROM (SELECT array_to_json(array_agg(f)) As data '
                             'FROM (SELECT dm.title,'
                             'u.username, dm.uid, dm.datasource,  dm.datalicense, '
                             'concat(\'<a href="/\',dm.uid,\'">\',dm.title,\'</a>\') as link, '
                             'concat(\'<a href="/\',dm.uid,\'/wmsmap">WMS</a>\') as wmsurl '
                             'FROM dev_map dm, public.user u '
                             'where dm.listed=true and u.id = dm.user_id order by dm.id) As f ) As fc;').fetchone()
    if data[0]['data'] is not None:
        return jsonify(data[0])
    else:
        resp = jsonify({u'data': []})
        return resp


@jsonapi.route('/manage/json', methods=['GET'])
@login_required
def manage():
    """Returns all deviation map entries and attributes of the currently logged in user / all users (admin) as json.
    If the user is admin, all deviationsmap entries and attributes in the database are returend as json.
    If no deviation map entry is found, an empty data entry is returend.
    This can used to display deviation map entries of the current user / all users (admin) in
    a DataTables table on the manage page.
    """
    if current_user.is_authenticated():
        if current_user.role == 1:  # Admin
            data = db.engine.execute('SELECT row_to_json(fc) FROM (SELECT array_to_json(array_agg(f)) As data '
                             'FROM (SELECT dm.title,'
                             'u.username as owner, dm.uid, dm.datasource, '
                             'concat(\'<a href="/\',dm.uid,\'">\',dm.title,\'</a>\') as link, '
                             'concat(\'<a href="/\',dm.uid,\'/wmsmap">WMS</a>\') as wmsurl,'
                             'concat(\'<a href="/\',dm.uid,\'/osmdownload">OSM Download</a>|\''
                             ',\'<a href="/\',dm.uid,\'/harmonize">Harmonize</a>|\',\'<a href="/\',dm.uid,'
                             '\'/linematch">Linematch</a>\', \'|<a href="/\',dm.uid,\'/results">Results</a>\''
                             ', \'|<a href="/\',dm.uid,\'/delte">Delete</a>\') as editurls '
                             'FROM dev_map dm,public.user u '
                             'where u.id = dm.user_id) As f ) As fc;').fetchone()
        else:
            data = db.engine.execute('SELECT row_to_json(fc) FROM (SELECT array_to_json(array_agg(f)) As data '
                             'FROM (SELECT dm.title,'
                             'u.username as owner, dm.uid, dm.datasource, '
                             'concat(\'<a href="/\',dm.uid,\'">\',dm.title,\'</a>\') as link, '
                             'concat(\'<a href="/\',dm.uid,\'/wmsmap">WMS</a>\') as wmsurl, '
                             'concat(\'<a href="/\',dm.uid,\'/osmdownload">OSM Download</a>|\''
                             ',\'<a href="/\',dm.uid,\'/harmonize">Harmonize</a>|\',\'<a href="/\',dm.uid,'
                             '\'/linematch">Linematch</a>\', \'|<a href="/\',dm.uid,\'/results">Results</a>\''
                             ', \'|<a href="/\',dm.uid,\'/delte">Delete</a>\') as editurls '
                             'FROM dev_map dm, public.user u '
                             'where u.id = '+str(current_user.id)+
                             ' and dm.user_id='+str(current_user.id)+') As f ) As fc;').fetchone()
    if data[0]['data'] is not None:
        return jsonify(data[0])
    else:
        resp = jsonify({u'data': []})
        return resp
        return jsonify(data[0])


@jsonapi.route('/<uid>/json/linematchresults', methods=['GET'])
def linematchresults(uid):
    """Returns the linematch results generated by the linematching process for a deviation map as json.
    This can used to display the linematch results in a DataTables table in map view.
    """
    uid = uid.encode("ISO-8859-1")
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT array_to_json(array_agg(f)) As data '
                             'FROM (SELECT t1_id, t2_id, ref_id, osm_id, t1name, t2name, rel_name as t2name2, '
                             'round(lengthdiff::numeric ,1) as lengthdiff,'
                             ' round(100000*meanposdev::numeric ,2) as meanposdev,'
                             'levenshteindiff1, levenshteindiff2 FROM odf_'+uid+'_found) As f ) '
                             'As fc;').fetchone()
    if data[0]['data'] is not None:
        return jsonify(data[0])
    else:
        resp = jsonify({u'data': []})
        return resp
        return jsonify(data[0])


@jsonapi.route('/<uid>/json/unmatchedresults', methods=['GET'])
def unmatchedresults(uid):
    """Returns all reference and osm features that did not match.
    This can used to display the unmatched features in a DataTables table in map view.
    """
    uid = uid.encode("ISO-8859-1")
    data = db.engine.execute('SELECT row_to_json(fc) FROM ( SELECT array_to_json(array_agg(f)) As data '
                             'FROM (SELECT id as t1_id, null as t2_id, old_id as ref_id, '
                             'null as osm_id, name as t1name, '
                             'null as t2name, null as t2name2, null as lengthdiff, null as meanposdev, '
                             'null as levenshteindiff1, null as levenshteindiff2 FROM odf_'+uid+'_ref_splitted '
                             'where not exists(select 1 from odf_'+uid+'_found f where f.t1_id=id) union all '
                             'SELECT null as t1_id, id as t2_id, null as ref_id,  '
                             'osm_id as osm_id, null as t1name, '
                             'name as t2name, null as t2name2, null as lengthdiff, null as meanposdev, '
                             'null as levenshteindiff1, null as levenshteindiff2 FROM odf_'+uid+'_osm_splitted '
                             'where not exists(select 1 from odf_'+uid+'_found f where f.t2_id=id)) As f ) '
                             'As fc;').fetchone()
    if data[0]['data'] is not None:
        return jsonify(data[0])
    else:
        resp = jsonify({u'data': []})
        return resp
        return jsonify(data[0])
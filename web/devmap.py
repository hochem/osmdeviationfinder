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

__author__ = 'Martin Hochenwarter'
__version__ = '0.1'

import os
import shutil
import zipfile
import uuid
import socket
from osmdeviationfinder import OSMDeviationfinder, HarmonizeOptions, LinematchOptions, ResultOptions
from osgeo import ogr
from web import app, db
from models import User, DevMap
from flask import json, request, Blueprint, jsonify, redirect, url_for, render_template, Response, abort, make_response
from flask.ext.login import (current_user, login_required)
from werkzeug.utils import secure_filename
from geoserver.catalog import Catalog

#: Blueprint for deviation finder specific functions
devmap = Blueprint('devmap', __name__, template_folder='templates')

DEBUG = True
UPLOAD_FOLDER = 'web/uploads/'
ALLOWED_EXTENSIONS = set(['zip', 'rar', 'json', 'osm'])
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024  # 32MB Upload-Limit
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#: Database connection info
serverName = 'localhost'
database = 'odf'
port = '5432'
usr = 'martin'
pw = 'odf'
connectioninfo = "dbname='%s' host='%s' port='%s' user='%s' password='%s'" % (database, serverName, port, usr, pw)

#: GeoServer REST info
gs_url = 'http://localhost:8080/geoserver/'
gs_user = 'admin'
gs_password = 'geoserver'
gs_workspace = 'OSMDeviationMaps'
gs_store = 'osmdeviationmaps'


class Shapefile(object):
    def __init__(self, name, ref, directory):
        self.name = name
        self.ref = ref
        self.directory = directory

class ShapefileColumns(object):
    def __init__(self, name):
        self.name = name


@devmap.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """This function handles the uid generation and zipfile (containing the shapefile) upload.

    GET request: a redirect to the index site is made, where the user can upload a file.

    POST request: first the file extions is validated, then a unique identifier is genereated for the current
    upload. This uid is stored in the database and a directory is created using the uid,
    in which the zip file gets extracted. After that the import to database site gets send to the user.
    """
    if request.method == 'POST':
        reffile = request.files['files[]']
        if reffile and allowed_file(reffile.filename):
            uid = str(uuid.uuid4())[:8]  # str(uuid.uuid4()) #.hex
            user = None
            if current_user.is_authenticated():
                user = current_user
                #user = User.query.filter_by(username='Guest').first()
            else:
                user = User.query.filter_by(username='Guest').first()
            dm = DevMap(uid, user)
            db.session.add(dm)
            db.session.commit()
            filename = secure_filename(reffile.filename)
            mapdir = os.path.join(app.config['UPLOAD_FOLDER'], uid)
            os.makedirs(mapdir)
            reffile.save(os.path.join(mapdir, filename))
            archive = os.path.join(mapdir, filename)
            zfile = zipfile.ZipFile(archive)
            for name in zfile.namelist():
                zfile.extract(name, mapdir)
            os.remove(archive)
            return url_for('devmap.import_to_db', uid=uid)
    else:
        return render_template('upload.html')


@devmap.route('/<uid>/import', methods=['GET', 'POST'])
def import_to_db(uid):
    """Function to import features from a layer of a shapefile into the database and calculation of the concavehull of
    the features in the table to use as a bounding polygon for the OverpassAPI request.

    GET request: The import site is returned, containing a set of the uploaded shapefiles.
    The user can then choose the shapefile to import.

    POST request: The chosen layer will be imported into a new table using the the function layer_to_db
    from the OSMDeviationfinder class. This function will import the features and convert multigeometry features to
    single geometry features. After a successful import, the concavehull of the imported data is generated using the
    function get_concavehull of the OSMDeviationfinder class. The concavhull is saved for the current devmap in the
    xy (for the OverpassAPI) and yx (for leaflet.js) representation. After that, the osm data download site is returned.
    """
    error = None
    fdir = os.path.join(app.config['UPLOAD_FOLDER'], uid)

    fdata = dict()

    if request.method == 'POST':
        uid = uid.encode('ISO-8859-1')
        fdata['datasource'] = request.form['source']
        fdata['title'] = request.form['title']
        fdata['datalicense'] = request.form['license']
        fdata['shapefile'] = request.form['shapefile']
        fdata['wmsformat'] = request.form['wmsformat']
        fdata['wmsurl'] = request.form['wmsurl']
        fdata['wmslayer'] = request.form['wmslayer']

        if len(fdata['datasource']) < 4:
            error = 'Please define a data source with at least 4 characters.'
        if len(fdata['datalicense']) < 3:
            error = 'Please a license with at least 2 characters.'
        if len(fdata['title']) < 4:
            error = 'Please define a title with at least 4 characters.'
        if len(fdata['wmsurl']) > 1 or len(fdata['wmslayer']) > 1 or len(fdata['wmsformat']) > 1:
            if not (fdata['wmsurl']) > 12 and len(fdata['wmslayer']) > 3 and len(fdata['wmsformat']) > 12:
                error = 'All fields for a custom WMS Basemap have to be filled.'
            if not 'image' in fdata['wmsformat']:
                error = 'Please define a correct image format eg. image/jpeg'
        else:
            dm = DevMap.query.filter_by(title=fdata['title']).first()
            if dm and dm.uid != uid:
                error = 'The title "' + fdata['title'] + '" is already chosen. Please try another title.'
        if fdata['shapefile'] == 'No Shapefile found!':
            error = 'No shapefile was found.'
        if error is None:
            f = os.path.join(fdir, fdata['shapefile'])
            tablename = 'odf_'+uid+'_ref'
            shapefile = ogr.Open(f)
            devfinder = OSMDeviationfinder(connectioninfo)
            s = shapefile.GetLayerByIndex(0)
            devfinder.layer_to_db(s, tablename, True)
            concavehull = devfinder.get_concavehull(tablename)
            dm = DevMap.query.filter_by(uid=uid).first()
            if current_user.is_authenticated() and dm.owner == current_user or dm.owner == User.query.filter_by(
                    username='Guest').first():
                boundsyx = {'type': "Feature", 'properties':
                            {'uid': uid, 'title': fdata['title'], 'author': dm.owner.username, 'source': fdata['datasource']},
                            'geometry': {'type': "Polygon", 'coordinates': [concavehull[1]['coordinates'][0]]}}
                boundsxy = {'type': "Feature", 'properties':
                            {'uid': uid, 'title': fdata['title'], 'author': dm.owner.username, 'source': fdata['datasource']},
                            'geometry': {'type': "Polygon", 'coordinates': [concavehull[0]['coordinates'][0]]}}
                dm.boundsxy = boundsxy
                dm.boundsyx = boundsyx
                dm.datasource = fdata['datasource']
                dm.title = fdata['title']
                dm.datalicense = fdata['datalicense']
                dm.basemapwmsurl = fdata['wmsurl']
                dm.basemapwmslayer = fdata['wmslayer']
                dm.basemapwmsformat = fdata['wmsformat']
                db.session.add(dm)
                db.session.commit()
                return redirect(url_for('devmap.osm_download', uid=uid))
    shapefiles = []
    for f in os.listdir(fdir):
        if f.endswith(".shp") and not f.startswith('.'):
            s = Shapefile(f, None, fdir)
            shapefiles.append(s)
    return render_template('import.html', shapefiles=shapefiles, uid=uid, error=error, fdata=fdata)


@devmap.route('/<uid>/osmdownload/', methods=['GET', 'POST'])
def osm_download(uid):
    """Function to download osm data.

    GET request: The osmdownload site is returned, which shows the bounding polygon for the selected layer and a form to
    choose the osm highway-types which should not be downloaded.

    POST request: The selected options in the request form and the bounding polygon coordinates are transformed to
    overpass query language. This data is used to call the osm_from_overpass function from the OSMDeviationfinder class,
    which will make an OverpassAPI query and dowload the returned osm data and yield the progress of the download back,
    which will be streamed to the client.
    """
    uid = uid.encode('ISO-8859-1')
    if request.method == 'POST':
        fdir = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        f = os.path.join(fdir, str(uid)+'.osm')
        typesquery = ''
        for i in request.form:
            typesquery = typesquery + '["highway"!="' + i + '"]'
        dm = DevMap.query.filter_by(uid=uid).first()
        bbox = json.dumps(dm.boundsxy)
        bbox = bbox[bbox.find("[["):bbox.find("]]")+2].replace('[', '').replace(']', '').replace(',', '')
        devfinder = OSMDeviationfinder(connectioninfo)
        return Response(devfinder.osm_from_overpass(bbox, typesquery, f, uid),
                        mimetype='text/html')
    return render_template('osmdownload.html', uid=uid)


@devmap.route('/<uid>/harmonize/', methods=['GET', 'POST'])
def harmonize(uid):
    """This function is used to show and handle the harmonization options and process.

    GET request: Renders and returns a site showing harmonization options.

    POST request: Gets the harmonization options from the user and creates an object of the HarmonizeOptions class
    which holds the user's chosen and default options. The harmonize_datasets function from the OSMDeviationfinder class
    is called with the HarmonizeOptions object as parameter. The harmonize_datasets function uses 'yield' to return the
    progress, this is used to stream the progress to the client.
    """
    uid = uid.encode('ISO-8859-1')
    devfinder = OSMDeviationfinder(connectioninfo)
    dm = DevMap.query.filter_by(uid=uid).first()
    if request.method == 'POST':
        devfinder.db_source = ogr.Open(devfinder.dbconnectioninfo_ogr, 1)

        harmonization_options = HarmonizeOptions(uid)

        #: Keep column osm_id while processing
        harmonization_options.keepcolumns_t2 = {'osm_id': 'varchar'}

        if 'azimuthdifftolerance' in request.form:
            harmonization_options.azimuthdifftolerance = request.form['azimuthdifftolerance']
        if 'maxcheckpointanglediff' in request.form:
            harmonization_options.maxcheckpointanglediff = request.form['maxcheckpointanglediff']
        if 'searchradius' in request.form:
            harmonization_options.searchradius = request.form['searchradius']
        if 'presplitref' in request.form:
            harmonization_options.presplitref = True
        if 'presplitosm' in request.form:
            harmonization_options.presplitosm = True
        if 'harmonize' in request.form:
            harmonization_options.harmonize = True
        if 'cleanref' in request.form:
            harmonization_options.cleanref = True
        if 'cleanosm' in request.form:
            harmonization_options.cleanosm = True
        if 'cleandistance' in request.form:
            harmonization_options.cleanosmradius = request.form['cleandistance']
            harmonization_options.cleanrefradius = request.form['cleandistance']
        if 'streetnamecol' in request.form:
            harmonization_options.streetnamecol = request.form['streetnamecol']
        if harmonization_options.streetnamecol == 'NoNameCol':
            devfinder.create_nonamecolumn('odf_'+uid+'_ref')
        dm.basetable = harmonization_options.basetable
        dm.harmonize = harmonization_options.harmonize
        dm.reftable = harmonization_options.reftable
        dm.osmtable = harmonization_options.osmtable
        dm.streetnamecol = harmonization_options.streetnamecol
        dm.outsuffix = harmonization_options.outsuffix
        dm.keepcolumns_t1 = harmonization_options.keepcolumns_t1
        dm.keepcolumns_t2 = harmonization_options.keepcolumns_t2
        dm.cleanref = harmonization_options.cleanref
        dm.cleanosm = harmonization_options.cleanosm
        dm.cleanrefradius = harmonization_options.cleanrefradius
        dm.cleanosmradius = harmonization_options.cleanosmradius
        dm.presplitref = harmonization_options.presplitref
        dm.presplitosm = harmonization_options.presplitosm
        dm.searchradius = harmonization_options.searchradius
        dm.azimuthdifftolerance = harmonization_options.azimuthdifftolerance
        dm.maxcheckpointanglediff = harmonization_options.maxcheckpointanglediff
        dm.max_roads_countdiff = harmonization_options.max_roads_countdiff
        dm.max_azdiff = harmonization_options.max_azdiff
        dm.max_distancediff = harmonization_options.max_distancediff
        db.session.add(dm)
        db.session.commit()
        return Response(devfinder.harmonize_datasets(harmonization_options), mimetype='text/html')
    namecolumns = devfinder.get_textcolumns('odf_'+uid+'_ref')
    return render_template('harmonize.html', uid=uid, namecolumns=namecolumns, dm=dm)


@devmap.route('/<uid>/linematch/', methods=['GET', 'POST'])
def linematch(uid):
    """This function is used to show and handle the linematching options and process.

    GET request: Renders and returns a site showing linematching options.

    POST request: Gets the linematching options from the user and creates an object of the LinematchOptions class
    which holds the user's chosen and default options. The linematch_datasets function from the OSMDeviationfinder class
    is called with the LinematchOptions object as parameter. The linematch_datasets function uses 'yield' to return the
    progress, this is used to stream the progress to the client.
    """
    uid = uid.encode('ISO-8859-1')
    dm = DevMap.query.filter_by(uid=uid).first()
    if request.method == 'POST':
        devfinder = OSMDeviationfinder(connectioninfo)
        devfinder.db_source = ogr.Open(devfinder.dbconnectioninfo_ogr, 1)

        linematch_options = LinematchOptions(uid)

        linematch_options.keepcolumns_t2 = {'osm_id': 'varchar'}

        if 'searchradius' in request.form:
            linematch_options.searchradius = request.form['searchradius']
        if 'maxpotentialmatches' in request.form:
            linematch_options.maxpotentialmatches = request.form['maxpotentialmatches']
        if 'minmatchingfeatlen' in request.form:
            linematch_options.minmatchingfeatlen = request.form['minmatchingfeatlen']
        if 'maxlengthdiffratio' in request.form:
            linematch_options.maxlengthdiffratio = request.form['maxlengthdiffratio']
        if 'maxanglediff' in request.form:
            linematch_options.maxanglediff = request.form['maxanglediff']
        if 'posdiffsegmentlength' in request.form:
            linematch_options.posdiffsegmentlength = request.form['posdiffsegmentlength']
        if 'hausdorffsegmentlength' in request.form:
            linematch_options.hausdorffsegmentlength = request.form['hausdorffsegmentlength']
        if 'maxazimuthdiff' in request.form:
            linematch_options.maxazimuthdiff = request.form['maxazimuthdiff']
        if 'maxmeanposdifftolengthratio' in request.form:
            linematch_options.maxmeanposdifftolength = request.form['maxmeanposdifftolengthratio']
        if 'minmeanposdifftolengthratio' in request.form:
            linematch_options.minmeanposdifftolength = request.form['minmeanposdifftolengthratio']
        if 'exportdevvec' in request.form:
            linematch_options.deviationvectorlayer = True
        else:
            linematch_options.deviationvectorlayer = False
        dm.searchradius2 = linematch_options.searchradius
        dm.minmatchingfeatlen = linematch_options.minmatchingfeatlen
        dm.maxlengthdiffratio = linematch_options.maxlengthdiffratio
        dm.maxanglediff = linematch_options.maxanglediff
        dm.maxpotentialmatches = linematch_options.maxpotentialmatches
        dm.posdiffsegmentlength = linematch_options.posdiffsegmentlength
        dm.hausdorffsegmentlength = linematch_options.hausdorffsegmentlength
        dm.maxazimuthdiff = linematch_options.maxazimuthdiff
        dm.maxmeanposdevtolength = linematch_options.maxmeanposdevtolength
        dm.minmeanposdevtolength = linematch_options.minmeanposdevtolength
        dm.maxabsolutmeanposdev = linematch_options.maxabsolutmeanposdev
        dm.maxdeviation = linematch_options.maxdeviation
        db.session.add(dm)
        db.session.commit()
        return Response(devfinder.linematch_datasets(linematch_options), mimetype='text/html')

    return render_template('linematch.html', uid=uid, dm=dm)


@devmap.route('/<uid>/finished/', methods=['GET', 'POST'])
def finished(uid):
    uid = uid.encode('ISO-8859-1')
    if request.method == 'POST':
        dm = DevMap.query.filter_by(uid=uid).first()
        if dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            title = request.form['title']
            listedmap = False
            if 'listed' in request.form:
                listedmap = True
            dm.title = title
            dm.listed = listedmap
            db.session.add(dm)
            db.session.commit()
            return render_template('finished.html', uid=uid)
        else:
            return render_template('finished.html', uid=uid, error="No User", dm=dm)
    else:
        dm = DevMap.query.filter_by(uid=uid).first()
        if dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            return render_template('finished.html', uid=uid, dm=dm)
        else:
            return redirect(url_for('devmap.index'))


@devmap.route('/<uid>/results/', methods=['GET', 'POST'])
def results(uid):
    """This function is used to show and handle the result generation options and process.

    GET request: Renders and returns a site showing result generation options.

    POST request: Gets the result generation options from the user and creates an object of the ResultOptions class
    which holds the user's chosen and default options. The create_results function from the OSMDeviationfinder class
    is called with the ResultOptions object as parameter. The create_results function uses 'yield' to return the
    progress, this is used to stream the progress to the client.
    """
    uid = uid.encode('ISO-8859-1')
    if request.method == 'POST':
        devfinder = OSMDeviationfinder(connectioninfo)
        devfinder.db_source = ogr.Open(devfinder.dbconnectioninfo_ogr, 1)

        result_options = ResultOptions(uid)

        dm = DevMap.query.filter_by(uid=uid).first()
        if current_user.is_authenticated() and dm.owner == current_user \
           or dm.owner == User.query.filter_by(username='Guest').first():

            if 'maxdevgrid' in request.form:
                result_options.maxdevgrid = True
            if 'posdevlines' in request.form:
                result_options.posdevlines = True
            if 'posdevlinedist' in request.form:
                result_options.posdevlinedist = request.form['posdevlinedist']
            if 'absdevgrid' in request.form:
                result_options.absdevgrid = True
            if 'matchingrategrid' in request.form:
                result_options.matchingrategrid = True
            if 'gridcellsize' in request.form:
                result_options.gridcellsize = request.form['gridcellsize']
            if 'unmatchedref' in request.form:
                result_options.unmatchedref = True
            if 'unmatchedrefminlen' in request.form:
                result_options.unmatchedrefminlen = request.form['unmatchedrefminlen']
            if 'unmatchedosm' in request.form:
                result_options.unmatchedosm = True
            if 'unmatchedosmminlen' in request.form:
                result_options.unmatchedosmminlen = request.form['unmatchedosmminlen']
            if 'matchedref' in request.form:
                result_options.matchedref = True
            if 'matchedrefminlen' in request.form:
                result_options.matchedrefminlen = request.form['matchedrefminlen']
            if 'matchedosm' in request.form:
                result_options.matchedosm = True
            if 'matchedosmminlen' in request.form:
                result_options.matchedosmminlen = request.form['matchedosmminlen']
            if 'minlevenshtein' in request.form:
                result_options.minlevenshtein = True
            if 'minlev' in request.form:
                result_options.minlev = request.form['minlev']
            if 'maxlevenshtein' in request.form:
                result_options.maxlevenshtein = True
            if 'maxlev' in request.form:
                result_options.maxlev = request.form['maxlev']

            # Keep track of created results
            dm.posdevlines = result_options.posdevlines
            dm.maxdevgrid = result_options.maxdevgrid
            dm.absdevgrid = result_options.absdevgrid
            dm.matchingrategrid = result_options.matchingrategrid
            dm.gridcellsize = result_options.gridcellsize
            dm.unmatchedref = result_options.unmatchedref
            dm.unmatchedosm = result_options.unmatchedosm
            dm.matchedref = result_options.matchedref
            dm.matchedosm = result_options.matchedosm
            dm.minlevenshtein = result_options.minlevenshtein
            dm.maxlevenshtein = result_options.maxlevenshtein

            db.session.add(dm)
            db.session.commit()
        return Response(devfinder.create_results(result_options), mimetype='text/html')
    else:
        return render_template('results.html', uid=uid)


@devmap.route('/<uid>/export/', methods=['GET', 'POST'])
def export(uid):
    """This function is used to show and handle the export options and uses the GeoServer REST API to export results.
    This function uses the GeoServer configuration client library by boundlessgeo, see:
    https://github.com/boundlessgeo/gsconfig
    To export the results, the GeoServer application has to be running and should be correctly set up to have access
    to the database and the styles should already be imported, see geoserver styles folder.

    GET request: Renders and returns a site showing export options.

    POST request: Gets the export options from the user and exports the results if they are defined in the options.
    The export is made by using GeoServer configuration client library. After the export, the newly created layers
    should be visible in the GeoServer web interface and the WM(T)S links should also work. These links can then be
    used to display the WM(T)S layers in JOSM or a gis.

    Remarks: This function will be redesigned in future versions
    """
    uid = uid.encode('ISO-8859-1')
    if request.method == 'POST':
        dm = DevMap.query.filter_by(uid=uid).first()
        if dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            title = request.form['title']
            listedmap = False
            if 'listed' in request.form:
                listedmap = True

            dm.title = title
            dm.listed = listedmap
            cat = Catalog(gs_url+'rest')
            cat.username = gs_user
            cat.password = gs_password

            ws = None
            try:
                ws = cat.get_workspace(gs_workspace)
            except socket.error, e:
                db.session.add(dm)
                db.session.commit()
                return render_template('export.html', uid=uid, error=e, dm=dm)
            st = cat.get_store(gs_store, ws)

            if 'maxdevgrid' in request.form:
                feattype = 'odf_'+uid+'_maxdevgrid'
                if dm.wmsmaxdevgrid:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":maxdevgrid")
                cat.save(l)
                dm.wmsmaxdevgrid = True
            else:
                dm.wmsmaxdevgrid = True
            if 'posdevlines' in request.form:
                feattype = 'odf_'+uid+'_posdevlines'
                if dm.wmsposdevlines:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":posdevlines")
                cat.save(l)
                dm.wmsposdevlines = True
            else:
                dm.wmsposdevlines = False
            if 'absdevgrid' in request.form:
                feattype = 'odf_'+uid+'_absdevgrid'
                if dm.wmsabsdevgrid:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":absdevgrid")
                cat.save(l)
                dm.wmsabsdevgrid = True
            else:
                dm.wmsabsdevgrid = False
            if 'matchingrategrid' in request.form:
                feattype = 'odf_'+uid+'_matchingrategrid'
                if dm.wmsmatchingrategrid:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":matchingrategrid")
                cat.save(l)
                dm.wmsmatchingrategrid = True
            else:
                dm.wmsmatchingrategrid = False
            if 'unmatchedref' in request.form:
                feattype = 'odf_'+uid+'_unmatchedref'
                if dm.wmsunmatchedref:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":ReferenceLines")
                cat.save(l)
                dm.unmatchedref = True
            else:
                dm.unmatchedref = False
            if 'unmatchedosm' in request.form:
                feattype = 'odf_'+uid+'_unmatchedosm'
                if dm.unmatchedosm:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":OSMLines")
                cat.save(l)
                dm.wmsunmatchedosm = True
            else:
                dm.wmsunmatchedosm = False
            if 'matchedref' in request.form:
                feattype = 'odf_'+uid+'_matchedref'
                if dm.wmsmatchedref:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":ReferenceLines")
                cat.save(l)
                dm.wmsmatchedref = True
            else:
                dm.wmsmatchedref = False
            if 'matchedosm' in request.form:
                feattype = 'odf_'+uid+'_matchedosm'
                if dm.wmsmatchedosm:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":OSMLines")
                cat.save(l)
                dm.wmsmatchedosm = True
            else:
                dm.wmsmatchedosm = False
            if 'minlevenshtein' in request.form:
                feattype = 'odf_'+uid+'_minlevenshtein'
                if dm.wmsminlevenshtein:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":ReferenceLines")
                cat.save(l)
                dm.wmsminlevenshtein = True
            else:
                dm.wmsminlevenshtein = False
            if 'maxlevenshtein' in request.form:
                feattype = 'odf_'+uid+'_maxlevenshtein'
                if dm.wmsmaxlevenshtein:
                    l = cat.get_layer(feattype)
                    if l is not None:
                        cat.delete(l)
                    ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                    if ft is not None:
                        cat.delete(ft)
                ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                cat.save(ft)
                l = cat.get_layer(feattype)
                l._set_default_style(gs_workspace+":ReferenceLines")
                cat.save(l)
                dm.wmsmaxlevenshtein = True
            else:
                dm.wmsmaxlevenshtein = False

            db.session.add(dm)
            db.session.commit()
            return render_template('finished.html', uid=uid)
        else:
            return render_template('export.html', uid=uid, error="No User", dm=dm)
    else:
        dm = DevMap.query.filter_by(uid=uid).first()
        if dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            return render_template('export.html', uid=uid, dm=dm)
        else:
            return redirect(url_for('devmap.index'))


@devmap.route('/<uid>/wmsmap/', methods=['POST', 'GET'])
def wmsmap(uid):
    """A function to render and display a map using WM(T)S layers provided by GeoServer
    """
    dm = DevMap.query.filter_by(uid=uid).first()
    baseurl = gs_url+gs_workspace+'/wms'
    return render_template('wmsmap.html', dm=dm, uid=uid, baseurl=baseurl)


@devmap.route('/<uid>/delete/', methods=['GET', 'POST'])
def delete(uid):
    """A function to delete a deviation map, all its tables, files and GeoServer layers.

    GET request: Renders and returns a site showing delete options.

    POST request: Gets delete options chosen by user and uses them to delete the chosen parts of the deviation map.
    To delete GeoServer layers the GeoServer configuration client library is used.
    """
    uid = uid.encode('ISO-8859-1')
    if request.method == 'POST':
        dm = DevMap.query.filter_by(uid=uid).first()
        if current_user.is_authenticated() and dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            if (dm.wmsposdevlines or dm.wmsmaxdevgrid or dm.wmsabsdevgrid or dm.wmsmatchingrategrid or
                    dm.wmsunmatchedref or dm.wmsunmatchedosm or dm.wmsmatchedref or dm.wmsmatchedosm or
                    dm.wmsminlevenshtein or dm.wmsmaxlevenshtein):
                cat = Catalog(gs_url+'rest')
                cat.username = gs_user
                cat.password = gs_password
                ws = None
                try:
                    ws = cat.get_workspace(gs_workspace)
                except socket.error, e:
                    detail = 'GeoServer is not available. Make sure that it is running and the connection is ok.'
                    return render_template('error.html', err=e, detail=detail)

                st = cat.get_store(gs_store, ws)
                if 'deletemaxdevgrid' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_maxdevgrid'
                    if dm.wmsmaxdevgrid:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsmaxdevgrid = False
                if 'deleteposdevlines' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_posdevlines'
                    if dm.wmsposdevlines:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsposdevlines = False
                if 'deleteabsdevgrid' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_absdevgrid'
                    if dm.wmsabsdevgrid:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        ft = cat.publish_featuretype(feattype, st, "EPSG:4326")
                        if ft is not None:
                            cat.delete(ft)
                        dm.wmsabsdevgrid = False
                if 'deletematchingrategrid' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_matchingrategrid'
                    if dm.wmsmatchingrategrid:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsmatchingrategrid = False
                if 'deleteunmatchedref' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_unmatchedref'
                    if dm.wmsunmatchedref:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.deleteunmatchedref = False
                if 'deleteunmatchedosm' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_unmatchedosm'
                    if dm.wmsunmatchedosm:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsunmatchedosm = False
                if 'deletematchedref' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_matchedref'
                    if dm.wmsmatchedref:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsmatchedref = False
                if 'deletematchedosm' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_matchedosm'
                    if dm.wmsmatchedosm:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsmatchedosm = False
                if 'deleteminlevenshtein' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_minlevenshtein'
                    if dm.wmsminlevenshtein:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsminlevenshtein = False
                if 'deletemaxlevenshtein' in request.form or 'deleteall' in request.form:
                    feattype = 'odf_'+uid+'_maxlevenshtein'
                    if dm.wmsmaxlevenshtein:
                        l = cat.get_layer(feattype)
                        if l is not None:
                            cat.delete(l)
                        dm.wmsmaxlevenshtein = False

            if 'deleteall' in request.form:
                folder = secure_filename(uid)
                folder = os.path.join(app.config['UPLOAD_FOLDER'], folder)
                shutil.rmtree(folder, True)
                db.engine.execute('drop table if exists odf_' + uid + '_ref')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_presplitted')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_splitted')
                db.engine.execute('drop table if exists odf_' + uid + '_found')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_junctions')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_points')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_cutpoints')
                db.engine.execute('drop table if exists odf_' + uid + '_ref_cutcheckpoints')
                db.engine.execute('drop table if exists odf_' + uid + '_osm')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_presplitted')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_splitted')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_junctions')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_points')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_cutpoints')
                db.engine.execute('drop table if exists odf_' + uid + '_osm_cutcheckpoints')
                db.engine.execute('drop table if exists odf_' + uid + '_unmatchedref;')
                db.engine.execute('drop table if exists odf_' + uid + '_unmatchedosm;')
                db.engine.execute('drop table if exists odf_' + uid + '_minlevenshtein;')
                db.engine.execute('drop table if exists odf_' + uid + '_maxlevenshtein;')
                db.engine.execute('drop table if exists odf_' + uid + '_grid;')
                db.engine.execute('drop table if exists odf_' + uid + '_maxdevgrid;')
                db.engine.execute('drop table if exists odf_' + uid + '_matchingrategrid;')
                db.engine.execute('drop table if exists odf_' + uid + '_deviationlines')
                db.engine.execute('drop table if exists odf_' + uid + '_junction_deviationlines')

                if DEBUG:
                    db.engine.execute('drop table if exists odf_' + uid + '_osm_presplitted_cutcheckpoints')
                    db.engine.execute('drop table if exists odf_' + uid + '_osm_presplitted_cutpoints')
                    db.engine.execute('drop table if exists odf_' + uid + '_osm_presplitted_junctions')
                    db.engine.execute('drop table if exists odf_' + uid + '_osm_presplitted_points')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted_cutcheckpoints')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted_cutpoints')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted_junction_devvec')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted_junctions')
                    db.engine.execute('drop table if exists odf_' + uid + '_ref_corrected_presplitted_points')
                    db.engine.execute('drop table if exists odf_' + uid + '_result')

            if 'deleteall' not in request.form:
                db.session.add(dm)
                db.session.commit()
                return render_template('delete.html', uid=uid, dm=dm, error=None)
            else:
                db.session.delete(dm)
                db.session.commit()
                return redirect(url_for('basic.index'))
        else:
            return render_template('error.html', err='You are not allowed to delete this map!')
    else:
        dm = DevMap.query.filter_by(uid=uid).first()
        if current_user.is_authenticated() and dm.owner == current_user or dm.owner == User.query.filter_by(username='Guest').first():
            return render_template('delete.html', uid=uid, dm=dm, error=None)
        else:
            return render_template('error.html', err='You are not allowed to delete this map!')#return redirect(url_for('basic.index'))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS
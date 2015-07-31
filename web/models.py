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
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import JSON

ROLE_USER = 2
ROLE_ADMIN = 1


class User(db.Model):
    """A simple User class for user management
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    role = db.Column(db.SmallInteger, default=ROLE_USER)
    password = db.Column(db.String(160))
    created_at = db.Column(db.Date())
    last_login = db.Column(db.Date())
    lang_short = db.Column(db.String(10))

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)
        self.created_at = datetime.now()
        self.last_login = datetime.now()

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password , password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return unicode(self.id)

    def __repr__(self):
        return '<User ID: %r>' % self.id


class DevMap(db.Model):
    """The DevMap class holds all necessary attributes of a deviation map and is used to keep track of generated result
    and export tables.
    """
    id = db.Column(db.Integer, primary_key=True, unique=True)
    title = db.Column(db.String(140))
    datasource = db.Column(db.String(140))
    datalicense = db.Column(db.String(140))
    uid = db.Column(db.String(140))
    filedir = db.Column(db.String(512))
    created_at = db.Column(db.DateTime)
    last_change = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner = db.relationship('User', backref=db.backref('devmaps', lazy='dynamic'))
    basemapwmsurl = db.Column(db.String(256))
    basemapwmslayer = db.Column(db.String(256))
    basemapwmsformat = db.Column(db.String(256))
    listed = db.Column(db.Boolean, default=True)
    boundsyx = db.Column(JSON)
    boundsxy = db.Column(JSON)

    posdevlines = db.Column(db.Boolean, default=False)
    maxdevgrid = db.Column(db.Boolean, default=False)
    absdevgrid = db.Column(db.Boolean, default=False)
    matchingrategrid = db.Column(db.Boolean, default=False)
    unmatchedref = db.Column(db.Boolean, default=False)
    unmatchedosm = db.Column(db.Boolean, default=False)
    matchedref = db.Column(db.Boolean, default=False)
    matchedosm = db.Column(db.Boolean, default=False)
    minlevenshtein = db.Column(db.Boolean, default=False)
    maxlevenshtein = db.Column(db.Boolean, default=False)

    wmsposdevlines = db.Column(db.Boolean, default=False)
    wmsmaxdevgrid = db.Column(db.Boolean, default=False)
    wmsabsdevgrid = db.Column(db.Boolean, default=False)
    wmsmatchingrategrid = db.Column(db.Boolean, default=False)
    wmsunmatchedref = db.Column(db.Boolean, default=False)
    wmsunmatchedosm = db.Column(db.Boolean, default=False)
    wmsmatchedref = db.Column(db.Boolean, default=False)
    wmsmatchedosm = db.Column(db.Boolean, default=False)
    wmsminlevenshtein = db.Column(db.Boolean, default=False)
    wmsmaxlevenshtein = db.Column(db.Boolean, default=False)

    basetable = db.Column(db.String(16))
    harmonize = db.Column(db.Boolean, default=False)
    reftable = db.Column(db.String(16))
    osmtable = db.Column(db.String(16))
    streetnamecol = db.Column(db.String(16))
    outsuffix = db.Column(db.String(16))
    keepcolumns_t1 = db.Column(JSON)
    keepcolumns_t2 = db.Column(JSON)
    cleanref = db.Column(db.Boolean, default=False)
    cleanosm = db.Column(db.Boolean, default=False)
    cleanrefradius = db.Column(db.DECIMAL)
    cleanosmradius = db.Column(db.DECIMAL)
    presplitref = db.Column(db.Boolean ,default=False)
    presplitosm = db.Column(db.Boolean, default=False)
    searchradius = db.Column(db.DECIMAL)
    azimuthdifftolerance = db.Column(db.DECIMAL)
    maxcheckpointanglediff = db.Column(db.DECIMAL)
    max_roads_countdiff = db.Column(db.DECIMAL)
    max_azdiff = db.Column(db.DECIMAL)
    max_distancediff = db.Column(db.DECIMAL)

    searchradius2 = db.Column(db.DECIMAL)
    minmatchingfeatlen = db.Column(db.DECIMAL)
    maxlengthdiffratio = db.Column(db.DECIMAL)
    maxanglediff = db.Column(db.DECIMAL)
    maxpotentialmatches = db.Column(db.INTEGER)
    posdiffsegmentlength = db.Column(db.DECIMAL)
    hausdorffsegmentlength = db.Column(db.DECIMAL)
    maxazimuthdiff = db.Column(db.DECIMAL)
    maxmeanposdevtolength = db.Column(db.DECIMAL)
    minmeanposdevtolength = db.Column(db.DECIMAL)
    maxabsolutmeanposdev = db.Column(db.DECIMAL)
    maxdeviation = db.Column(db.DECIMAL)

    posdevlines = db.Column(db.Boolean, default=False)
    posdevlinedist = db.Column(db.DECIMAL)
    unmatchedref = db.Column(db.Boolean, default=False)
    unmatchedrefminlen = db.Column(db.DECIMAL)
    unmatchedosm = db.Column(db.Boolean, default=False)
    unmatchedosmminlen = db.Column(db.DECIMAL)
    matchedref =  db.Column(db.Boolean, default=False)
    matchedrefminlen = db.Column(db.DECIMAL)
    matchedosm = db.Column(db.Boolean, default=False)
    matchedosmminlen =db.Column(db.DECIMAL)
    minlevenshtein = db.Column(db.Boolean, default=False)
    minlev = db.Column(db.INTEGER)
    maxlevenshtein = db.Column(db.Boolean, default=False)
    maxlev = db.Column(db.INTEGER)
    maxdevgrid = db.Column(db.Boolean, default=False)
    absdevgrid = db.Column(db.Boolean, default=False)
    matchingrategrid = db.Column(db.Boolean, default=False)
    gridcellsize = db.Column(db.DECIMAL)



    def __init__(self, uid, owner):
        self.uid = uid
        self.owner = owner
        self.created_at = datetime.now()
        self.last_change = datetime.now()
        #: State is not yet implemeneted! It's used as a statemachine to keep track of deviation map creation
        self.state = 0  #: 0=created, 1=imported, 2=osmdownloaded, 3=splitted, 4=linematched, 5=results, 6=exported
        self.title = None
        self.source = None
        #self.shared = False
        self.listed = False
        #: boundsxy for overpassapi query
        self.boundsxy = None
        #: boundsyx for geojson, leaflet.js
        self.boundsyx = None
        self.filedir = None

        self.posdevlines = False
        self.maxdevgrid = False
        self.absdevgrid = False
        self.matchingrategrid = False
        self.unmatchedref = False
        self.unmatchedosm = False
        self.matchedref = False
        self.matchedosm = False
        self.minlevenshtein = False
        self.maxlevenshtein = False

        self.wmsposdevlines = False
        self.wmsmaxdevgrid = False
        self.wmsabsdevgrid = False
        self.wmsmatchingrategrid = False
        self.wmsunmatchedref = False
        self.wmsunmatchedosm = False
        self.wmsmatchedref = False
        self.wmsmatchedosm = False
        self.wmsminlevenshtein = False
        self.wmsmaxlevenshtein = False

        self.basetable = ""
        self.harmonize = False
        self.reftable = ""
        self.osmtable = ""
        self.streetnamecol = ""
        self.outsuffix = ""
        self.keepcolumns_t1 = None
        self.keepcolumns_t2 = None
        self.cleanref = True
        self.cleanosm = True
        self.cleanrefradius = 0.000002
        self.cleanosmradius = 0.000002
        self.presplitref = True
        self.presplitosm = True
        self.searchradius = 0.0005
        self.azimuthdifftolerance = 0.78
        self.maxcheckpointanglediff = 0.5
        self.max_roads_countdiff = 3
        self.max_azdiff = 0.0
        self.max_distancediff = 0.0

        self.searchradius2 = 0.0005
        self.maxlengthdiffratio = 2.0
        self.minmatchingfeatlen = 0.0001
        self.maxanglediff = 0.32
        self.maxpotentialmatches = 10
        self.posdiffsegmentlength = 0.001
        self.hausdorffsegmentlength = 0.005
        self.maxazimuthdiff = 1.0472
        self.maxmeanposdevtolength = 0.6
        self.minmeanposdevtolength = 0.0001
        self.maxabsolutmeanposdev = 0.0005
        self.maxdeviation = 0.5

        self.posdevlines = False
        self.posdevlinedist = 0.0
        self.unmatchedref = False
        self.unmatchedrefminlen = 0.0
        self.unmatchedosm = False
        self.unmatchedosmminlen = 0.0
        self.matchedref = False
        self.matchedrefminlen = 0.0
        self.matchedosm = False
        self.matchedosmminlen = 0.0
        self.minlevenshtein = False
        self.minlev = 0
        self.maxlevenshtein = False
        self.maxlev = 0
        self.maxdevgrid = False
        self.absdevgrid = False
        self.matchingrategrid = False
        self.gridcellsize = 0.0


    def __repr__(self):
        return '<Map UID: %r>' % self.uid
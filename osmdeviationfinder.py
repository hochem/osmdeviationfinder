#  -*- coding: utf-8 -*-
"""
    OSM Deviation Finder
    ~~~~~~~~~~~~~~~~~~~~

    A simple library for linematching and deviation determination
    between a reference dataset and openstreetmap data.
    It's basically a collection of sql/postgis queries.
    Because of the webinterface it currently uses 'yield' to stream status messages back to the client.

    :copyright: (c) 2015 by Martin Hochenwarter
    :license:  MIT
"""

__author__ = 'Martin Hochenwarter'
__version__ = '0.1'

import psycopg2
import urllib2
import os.path
from osgeo import ogr

#: If DEBUG is set to True, intermediate tables will not be temporary!
DEBUG = True
ogr.UseExceptions()

#: Define constants
pi = str(3.14159265358979)
two_pi = str(2*3.14159265358979)
table_prefix = 'odf_'
ref_suffix = '_ref'
osm_suffix = '_osm'
splitted_suffix = '_splitted'
linematched_suffix = '_result'


class HarmonizeOptions(object):
    """A class to hold all necessary options for the harmonization process.
    :param map_id: id of the current deviation map eg: 1a2b3c4d
    :param keepcolumns_t1: a dictionary containing columnns of table1 that should be included in the harmonized features
    :param keepcolumns_t2: a dictionary containing columnns of table2 that should be included in the harmonized features
    :param cleanref: defines if reference-table should be cleaned using a simple cleaning method
    :param cleanrefradius: the threshold for ref-features, in which end- and startpoints are corrected
    :param cleanosm: defines if osm-table should be cleaned using a simple cleaning method
    :param cleanosmradius: the threshold for osm-features, in which end- and startpoints are corrected
    :param presplitref: defines if the reference data should be presplitted
    :param presplitosm: defines if the osm data should be presplitted
    :param searchradius: the circular area, which is used to identify potential intersections for the splitting process
    :param azimuthdifftolerance: the max. allowed difference between the azimuth values of two lines
    (independent of line orientation!)
    :param maxcheckpointanglediff: the max. allowed difference between all azimuth angles between a potential cutpoint
    and a checkpoint belonging to it
    :param max_roads_countdiff: the max. allowed difference in the number of intersecting roads between two junctions
    which are beeing matched
    :param max_azdiff: the max. allowed difference between the mean value of all azimuth angles between two
    matched junctions
    :param max_distancediff: the max. allowed distance between two matched junctions
    """
    def __init__(self, map_id, streetnamecol='name', harmonize=False, keepcolumns_t1={}, keepcolumns_t2={}, cleanref=False,
                 cleanrefradius=0.0000001, cleanosm=False, cleanosmradius=0.0000001, presplitref=False, presplitosm=False,
                 searchradius=0.0005, azimuthdifftolerance=0.785398163, maxcheckpointanglediff=0.5,
                 max_roads_countdiff=3.0, max_azdiff=3.15, max_distancediff=0.0002):
        self.basetable = table_prefix + map_id
        self.harmonize = harmonize
        self.reftable = self.basetable + ref_suffix
        self.osmtable = self.basetable + osm_suffix
        self.outsuffix = splitted_suffix
        self.streetnamecol = streetnamecol
        self.keepcolumns_t1 = keepcolumns_t1
        self.keepcolumns_t2 = keepcolumns_t2
        self.cleanref = cleanref
        self.cleanrefradius = cleanrefradius
        self.cleanosm = cleanosm
        self.cleanosmradius = cleanosmradius
        self.presplitref = presplitref
        self.presplitosm = presplitosm
        self.searchradius = searchradius
        self.azimuthdifftolerance = azimuthdifftolerance
        self.maxcheckpointanglediff = maxcheckpointanglediff
        self.max_roads_countdiff = max_roads_countdiff
        self.max_azdiff = max_azdiff
        self.max_distancediff = max_distancediff


class LinematchOptions(object):
    """A class to hold all necessary options for the linematching process.
    :param map_id: id of the current deviation map eg: 1a2b3c4d
    :param keepcolumns_t1: a dictionary containing columnns of table1 that should be included in the linematch result
    :param keepcolumns_t2: a dictionary containing columnns of table2 that should be included in the linematch result
    :param searchradius: the max. distance, which is used to identify potential for the splitting process
    :param maxlengthdiffratio: the max. allowed ratio between the lengths of two features which are matched
    :param minmatchingfeatlen: the min length of a feature to be included in matching process
    :param maxanglediff: the max. allowed difference of azimuth angles (orientation independent) of two features
    :param maxpotentialmatches: the max. number of potential matching features for one ref-feature
    :param posdiffsegmentlength: the distance between generated positional deviation lines from one potential machting
    partner to the ref-feature; a smaller number gives a better mean positional deviation value, but takes longer
    to calculate, a bigger number is faster, but more inexact
    :param hausdorffsegmentlength: the same as posdiffsegmentlength but for the hausdorff-distance
    :param maxazimuthdiff: the max. allowed difference of azimuth angles (orientation independent) of two features
    :param maxmeanposdevtolength: the max. allowed ratio between the mean positional difference to mean length ratio
    between two potential matching partners which are beeing matched
    :param minmeanposdevtolength: a tolerance value for very small feature-segments
    :param maxabsolutmeanposdev: the max. allowed absolute mean positional difference between two potential matching
    partners which are beeing matched
    :param maxdeviation: the max. allowed deviation (sum of meanposdev, azimuthdiff, lengthdiff,... divided by the
    number of factors) for the matching process
    """
    def __init__(self, map_id, keepcolumns_t1={}, keepcolumns_t2={}, searchradius=0.0005, maxlengthdiffratio=2.0,
                 minmatchingfeatlen=0.0001, maxanglediff=0.32, maxpotentialmatches=10,
                 posdiffsegmentlength=0.001, hausdorffsegmentlength=0.005, maxazimuthdiff=1.0472,
                 maxmeanposdevtolength=0.6, minmeanposdevtolength=0.0001, maxabsolutmeanposdev=0.0005,
                 maxdeviation=0.5):
        self.basetable = table_prefix + map_id
        self.reftable = self.basetable + ref_suffix + splitted_suffix
        self.osmtable = self.basetable +osm_suffix + splitted_suffix
        self.outsuffix = linematched_suffix
        self.keepcolumns_t1 = keepcolumns_t1
        self.keepcolumns_t2 = keepcolumns_t2
        self.searchradius = searchradius
        self.minmatchingfeatlen = minmatchingfeatlen
        self.maxlengthdiffratio = maxlengthdiffratio
        self.maxanglediff = maxanglediff
        self.maxpotentialmatches = maxpotentialmatches
        self.posdiffsegmentlength = posdiffsegmentlength
        self.hausdorffsegmentlength = hausdorffsegmentlength
        self.maxazimuthdiff = maxazimuthdiff
        self.maxmeanposdevtolength = maxmeanposdevtolength
        self.minmeanposdevtolength = minmeanposdevtolength
        self.maxabsolutmeanposdev = maxabsolutmeanposdev
        self.maxdeviation = maxdeviation

class ResultOptions(object):
    """A class to hold all necessary options for the result generation process.
    The only necessary parameter is map_id, all other parameters will be filled with standard values.

    :param map_id: id of the current deviation map eg: 1a2b3c4d
    :param keepcolumns_t1: a dictionary containing columnns of table1 that should be included in the result table
    :param keepcolumns_t2: a dictionary containing columnns of table2 that should be included in the result table
    :param posdevlines: if True, positional deviation lines between two matched features will be genereated
    :param posdevlinedist: defines the distance between / interval of the generated pos. dev. lines
    :param matchedref: if True, all matched reference-features with a length above matchedrefminlen will be extracted
    :param matchedrefminlen: defines the min. length a matched reference-features must have to get extracted
    :param matchedosm: if True, all matched osm-features with a length above matchedosmminlen will be extracted
    :param matchedosmminlen: defines the min. length a matched osm-features must have to get extracted
    :param unmatchedref:  if True, all UNmatched ref-features with a length above unmatchedrefminlen will be extracted
    :param unmatchedrefminlen: defines the min. length an UNmatched ref-features must have to get extracted
    :param unmatchedosm: if True, all UNmatched osm-features with a length above unmatchedosmminlen will be extracted
    :param unmatchedosmminlen: defines the min. length an UNmatched osm-features must have to get extracted
    :param minlevenshtein: if True, all matched ref-features with a levenshteindistance below minlev will be extracted
    :param minlev: defines the max. levenshteindistance a matched ref-feature must have to get extracted
    :param maxlevenshtein: if True, all matched ref-features with a levenshteindistance above maxlev will be extracted
    :param maxlev: defines the min. levenshteindistance a matched ref-feature must have to get extracted
    :param maxdevgrid: if True, a grid with max. deviation (based on posdefline-lengths) per tile will be generated
    :param absdevgrid: if True, a grid with abs. deviation (sum of all posdefline-lengths) per tile will be generated
    :param matchingrategrid: if True, a grid with the ratio of matched to unmatched ref-features per tile will be
    generated
    :param gridcellsize: defines the cellsize in degree for grid generation
    """
    def __init__(self, map_id, keepcolumns_t1={}, keepcolumns_t2={}, posdevlines=False,
                 posdevlinedist=0.0001, matchedref=False, matchedrefminlen=0.00001,
                 matchedosm=False, matchedosmminlen=0.00001, unmatchedref=False, unmatchedrefminlen=0.00001,
                 unmatchedosm=False, unmatchedosmminlen=0.00001, minlevenshtein=False,
                 minlev=3, maxlevenshtein=False, maxlev=3,maxdevgrid=False, absdevgrid=False,
                 matchingrategrid=False, gridcellsize=0.01):

        self.basetable = table_prefix + map_id
        self.reftable = self.basetable + ref_suffix # + linematched_suffix
        self.osmtable = self.basetable + osm_suffix # + linematched_suffix
        self.keepcolumns_t1 = keepcolumns_t1
        self.keepcolumns_t2 = keepcolumns_t2
        self.posdevlines = posdevlines
        self.posdevlinedist = posdevlinedist
        self.unmatchedref = unmatchedref
        self.unmatchedrefminlen = unmatchedrefminlen
        self.unmatchedosm = unmatchedosm
        self.unmatchedosmminlen = unmatchedosmminlen
        self.matchedref = matchedref
        self.matchedrefminlen = matchedrefminlen
        self.matchedosm = matchedosm
        self.matchedosmminlen = matchedosmminlen
        self.minlevenshtein = minlevenshtein
        self.minlev = minlev
        self.maxlevenshtein = maxlevenshtein
        self.maxlev = maxlev
        self.maxdevgrid = maxdevgrid
        self.absdevgrid = absdevgrid
        self.matchingrategrid = matchingrategrid
        self.gridcellsize = gridcellsize


class OSMDeviationfinder(object):
    """The osmdeviationfinder object implements all necessary methods for geodata import,
    osm-data download, geometry cleaning, data harmonization, linematching and result generation.
    It is the central object to interface with the implemented methods and data in the database.

    Please keep in mind that nearly all of the implemented methods use the 'yield' keyword to stream
    statusinformation and progress over the webinterface to the client.

    Usually you create a :class:`OSMDeviationfinder` instance like this::
        from osmdeviationfinder import OSMDeviationfinder
        dbconnectioninfo='dbname=dbname host=host port=5432 user=username password=password'
        odf = OSMDeviationfinder(dbconnectioninfo)

    :param dbconnectioninfo: the connection string for the database eg:
        'dbname=dbname host=host port=5432 user=username password=password'
    """
    def __init__(self, dbconnectioninfo):
        #: The dbconnectioninfo is used for psycopg and a prefixed version for ogr
        self.dbconnectioninfo_psycopg = dbconnectioninfo
        self.dbconnectioninfo_ogr = 'PG:'+dbconnectioninfo

        #: Variables to hold objects for the geodata import
        self.osm_source = None
        self.ref_file = None
        self.ref_data = None
        self.osm_data = None
        self.connection = None
        self.cursor = None

    def layer_to_db(self, source_layer, db_table, overwrite=True):
        """A simple method to import geodata from an open ogr-layer into a postgresql/postgis database.
        Multigeometry features will be split up and imported as multiple simplegeometry features.
        Split-up features will get the same attributes as their origin-feature, but a new ID.
        After a succesfull import, the table will be indexed with GIST(geom).
        To keep the parameters used in the queries short, the geometry-column is named 'geom' and
        the OGC_FID column is named 'id'!

        :param source_layer: the ogr-layer from which the features will be imported
        :param db_table: the name of the table which will hold the imported geodata
        :param overwrite: if True, existing data will be overwritten by the import process
        """
        server_ds = ogr.Open(self.dbconnectioninfo_ogr)

        if server_ds.GetDriver().GetName() == 'PostgreSQL':
            ogr.RegisterAll()
            options = ['GEOMETRY_NAME=geom', 'FID=id']
            if overwrite:
                options.append('OVERWRITE=YES')

            db_layer = server_ds.CreateLayer(db_table, source_layer.GetSpatialRef(), ogr.wkbUnknown, options)

            #: Recreates fields from source_layer in table
            for fidx in xrange(source_layer.GetLayerDefn().GetFieldCount()):
                fd = source_layer.GetLayerDefn().GetFieldDefn(fidx)
                if fd.GetWidth() > 0:
                    fd.SetWidth(fd.GetWidth()+2) #FIXME: The used ref-data has malformed field definitions?
                    fd.SetPrecision(fd.GetPrecision()-3)
                db_layer.CreateField(fd)

            #: Iterate over source_layer features, split up multigeomtries and save them to db_table
            source_layer.ResetReading()
            db_layer.StartTransaction()
            f_count = 0
            new_fid = 0
            while True:
                new_feature = source_layer.GetNextFeature()
                if new_feature is None:
                    break
                if new_feature.GetGeometryRef().GetGeometryCount() > 0:
                    for geomidx in range(0, new_feature.GetGeometryRef().GetGeometryCount()):
                        geom = new_feature.GetGeometryRef().GetGeometryRef(geomidx)
                        feat_part = new_feature.Clone()
                        feat_part.SetFID(new_fid)
                        new_fid += 1
                        feat_part.SetGeometry(geom)
                        db_layer.CreateFeature(feat_part)
                else:
                    new_feature.SetFID(new_fid)
                    new_fid += 1
                    db_layer.CreateFeature(new_feature)
                if f_count % 128 == 0:
                    if db_layer.CommitTransaction() is not 0:
                        print 'Error commiting Features'
                        break
                    db_layer.StartTransaction()
                f_count += 1
            db_layer.CommitTransaction()
        else:
            print 'Error loading PostgreSQL Driver'
        self.create_spatial_index(db_table)

    def open_reference_shapfile(self, filename):
        """Simple helper method to open and validate .shp files

        :param filname: the filename of the shape file to open
        """
        self.ref_file = ogr.Open(filename)
        self.validate_shape_data(self.ref_file)
        self.ref_data = self.ref_file.GetLayer()

    def osm_from_overpass(self, bounds, types=None, save_dir='osm.osm', map_id=None):
        """Downloads openstreetmap road data for the given bounding-polygon and osm highway-types.
        This method uses yield to stream the progress of the download to the webinterface!

        :param bounds: the bounding polygon used as parameter for the overpass-api
        :param types: a string with a list of osm highway-types which should not be loaded
        :param save_dir: the directory used to save the downloaded osm_data
        :param map_id: if given, this id will be used to import the osm-data into, if not given,
            the data will just be downloaded and not imported
        """
        if types is None:
            types = ('["highway"!="cycleway"]'
                     '["highway"!="bridleway"]'
                     '["highway"!="steps"]'
                     '["highway"!="footway"]'
                     '["highway"!="pedestrian"]'
                     '["highway"!="path"]')

        #: Check if file already exists, if so, and map_id is given, import the file
        if os.path.isfile(save_dir):
            if DEBUG:
                yield 'OSM Data already loaded for this map!'
            self.osm_source = ogr.Open(save_dir)
            self.osm_data = self.osm_source.GetLayer(1)
            if map_id:
                self.osm_source = ogr.Open(save_dir)
                self.osm_data = self.osm_source.GetLayer(1)
                self.layer_to_db(self.osm_data, table_prefix+map_id+osm_suffix, True)
                self.osm_data = self.osm_source.GetLayer(2) #: Import Relations
                self.layer_to_db(self.osm_data, table_prefix+map_id+osm_suffix+'_rel', True)
            else:
                self.osm_source = ogr.Open(save_dir)
                self.osm_data = self.osm_source.GetLayer(1)
            return

        if DEBUG:
            print bounds

        #: Make request-url for the given parameters
        #if 'POLYGON(' in bounds:
        #    print 'meh'
        #    bounds = bounds.replace('(', '').replace(')', '').replace('\'', '').replace(',', ' ')
        #    bounds = bounds.replace('POLYGON', '')
        #    req_url = 'http://overpass-api.de/api/interpreter?data='+urllib2.quote(('(way["highway"]'+types +
        #                                                                            '(poly:"'+bounds+'");'
        #                                                                            'node(w)->.x;rel(bw););out body;'))
        #elif '(' not in bounds and '[' not in bounds:
        #    req_url = 'http://overpass-api.de/api/interpreter?data='+urllib2.quote(('(way["highway"]'+types +
        #                                                                            '(poly:"'+bounds+'");'
        #                                                                            'node(w)->.x;rel(bw););out body;'))
        #else:
        #    yield 'Error: Unknown Bounds Format!'
        #    print 'Error: Unknown Bounds Format!'
        #    return

        req_url = 'http://overpass-api.de/api/interpreter?data='+urllib2.quote(('(way["highway"]'+types +
                                                                                    '(poly:"'+bounds+'");'
                                                                                    'node(w)->.x;rel(bw););out body;'))

        if DEBUG:
            print req_url

        headers = {'User-Agent:': 'Mozilla/5.0'}
        req = urllib2.Request(req_url, None, headers)
        chunk_size = 8192

        #: Try downloading the request in chunks and yield progress of download
        try:
            response = urllib2.urlopen(req, timeout=61)
            osmfile = file(save_dir, 'wb', 0)
            bytes_so_far = 0
            while 1:
                chunk = response.read(chunk_size)
                osmfile.write(chunk)
                bytes_so_far += len(chunk)
                if not chunk:
                    break
                    myfile.flush()
                    osmfile.close()
                if bytes_so_far % (32 * 8192) == 0:
                    b = str(bytes_so_far / 1024)
                    yield (b)
        except urllib2.URLError, e:
            yield 'An error occured: %s' % e.strerror

        #: If map_id is given, import the downloaded osm-data to database
        if map_id:
            self.osm_source = ogr.Open(save_dir)
            self.osm_data = self.osm_source.GetLayer(1)
            self.layer_to_db(self.osm_data, table_prefix+map_id+osm_suffix, True)
            self.osm_data = self.osm_source.GetLayer(2) #: Import relations
            self.layer_to_db(self.osm_data, table_prefix+map_id+osm_suffix+'_rel', True)
        else:
            self.osm_source = ogr.Open(save_dir)
            self.osm_data = self.osm_source.GetLayer(1)

    def download_changeset(self):
        """Not implemented yet, maybe in future version.
        Function to keep a deviation map up to date, without having to download the whole area for each update
        """
        #TODO: http://www.openstreetmap.org/history?list=1&bbox=9.201049804%2C46.3165841818%2C17.49023%2C49.0774642631
        # http://www.openstreetmap.org/api/0.6/changeset/22072721/download
        # http://svn.openstreetmap.org/applications/utils/python_lib/OsmApi/OsmApi.py
        pass

    @staticmethod
    def validate_shape_data(self, shape_data):
        """Simple helper method to validate shape data
        """
        if not shape_data:
            raise ShapeDataError('The shapefile is invalid')
        elif shape_data.GetLayerCount() != 1:
            raise ShapeDataError('The shapefile must have exactly one layer')
        else:
            if DEBUG:
                print 'Shape OK'

    def clean_dataset(self, table, threshold, namecol='name', keepcolumns={}):
        """Simple method to clean/correct the geometries of a postgis table.
        Open start- and endpoint of a linefeature, which is within the threshold distance to a line or a junction of
        the same dataset will be joined with the line or junction. If a linefeature crosses another linefeature of the
        dataset within the threshold distance, the protruding part of the line is cut off and the end/startpoint will
        equal the intersection point.

        The linesplitting implementation is based on:
        https://github.com/pgRouting/pgrouting/blob/master/src/common/sql/pgrouting_node_network.sql
        (Author: Nicolas Ribot, 2013)

        :param table: name of the table, which will be cleaned
        :param threshold: threshold distanced used for the cleaning process
        """
        #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor #connection.cursor()

        table = str(table)
        threshold = str(threshold)

        #: Build strings for columns to that should be included in the cleaned table
        kc_str1 = ''
        kc_str2 = ''
        kc_str3 = ''
        for k in keepcolumns:
            kc_str1 += ', ' + k + ' ' + keepcolumns.get(k)
            kc_str2 += ', ' + k
            kc_str3 += ', l.' + k


        #: Recreate table and index if already existing
        query = ('DROP table if exists '+table+'_corrected;')
        cursor.execute(query)

        query = ('DROP index if exists '+table+'_id_idx;')
        cursor.execute(query)

        query = ('CREATE index '+table+'_id_idx on '+table+' using btree(id);')
        cursor.execute(query)

        query = ('CREATE TABLE '+table+'_corrected (id bigserial PRIMARY KEY, old_id integer, sub_id integer, '
                 'name varchar'+kc_str1+');')
        cursor.execute(query)

        query = ('SELECT addGeometryColumn(\''+table+'_corrected\',\'geom\',(SELECT ST_SRID(geom) as srid '
                 'FROM '+table+' WHERE geom IS NOT NULL LIMIT 1), (SELECT geometrytype(geom) '
                 'FROM '+table+' limit 1), 2);')
        cursor.execute(query)

        query = ('CREATE INDEX '+table+'_corrected_geom_idx ON '+table+'_corrected USING GIST (geom);')
        cursor.execute(query)

        #: Create table with intersections of features to generate a list participating lines
        # and later a list of junctions
        query = ('CREATE temp table intergeom_'+table+' on commit DROP as '
                 '(SELECT ST_Intersection(a.geom, b.geom) as g, ST_Startpoint(a.geom) as sp, ST_Endpoint(a.geom) as ep,'
                 ' a.id as l1id, b.id as l2id, a.geom as line, Count(Distinct a.id) as roads_count '
                 'FROM '+table+' as a, '+table+' as b '
                 'WHERE a.id <> b.id and ST_Intersects(a.geom, b.geom) '
                 'GROUP BY g, l1id, l2id, line, sp, ep);')
        cursor.execute(query)

        #: Extract a list of IDs of participating lines and the intersection as fraction of line1 and create index
        query = ('CREATE temp table interloc_'+table+' on commit DROP as '
                 '(SELECT * FROM ((SELECT l1id, l2id, st_linelocatepoint(intergp.line, intergp.g) as locus '
                 'FROM (SELECT l1id, l2id, (st_dump(g)).geom as g, line '
                 'FROM intergeom_'+table +
                 ' WHERE st_geometrytype(g)=\'ST_Point\' or st_geometrytype(g)=\'ST_MultiPoint\') as intergp)) as subq '
                 'WHERE locus<>0 and locus<>1);')
        cursor.execute(query)

        query = ('CREATE index interloc_'+table+'_id_idx on interloc_'+table+'(l1id);')
        cursor.execute(query)

        #: Insert all splitted parts of the intersecting features into the corrected table
        query = ('INSERT into '+table+'_corrected (old_id, sub_id, geom, name '+kc_str2+') (with cut_locations as '
                 '(SELECT l1id as lid, locus FROM interloc_'+table+' UNION ALL SELECT i.l1id as lid, 0 as locus '
                 'FROM interloc_'+table+' i left join '+table+' b on (i.l1id = b.id) UNION ALL '
                 'SELECT i.l1id as lid, 1 as locus FROM interloc_'+table+' i '
                 'left join '+table+' b on (i.l1id = b.id) order by lid, locus ), loc_with_idx as '
                 '(SELECT lid, locus, row_number() over (partition by lid order by locus) as idx FROM cut_locations) '
                 'SELECT l.id, loc1.idx as sub_id, st_linesubstring(l.geom, loc1.locus, loc2.locus) as geom, '
                 'l.'+namecol+' as name '+kc_str3+' FROM loc_with_idx loc1 join loc_with_idx loc2 using (lid) '
                 'join '+table+' l on (l.id = loc1.lid) where loc2.idx = loc1.idx+1 '
                 'and geometryType(st_linesubstring(l.geom, loc1.locus, loc2.locus)) = \'LINESTRING\');')
        cursor.execute(query)

        #: Insert all non-intersecting line features to the corrected features table
        query = ('INSERT into '+table+'_corrected (old_id, sub_id, geom, name '+kc_str2+')'
                 '(with used as (SELECT distinct old_id FROM '+table+'_corrected) '
                 'SELECT id, 1 as sub_id, geom, '+namecol+' '+kc_str2+' FROM '+table +
                 ' WHERE id not in (SELECT * FROM used));')
        cursor.execute(query)

        #: Delete all features with a length below threshold (protruding parts) from table
        query = ('DELETE FROM '+table+'_corrected USING '
                 '(SELECT id FROM '+table+'_corrected WHERE st_length(geom)<'+threshold+') AS deletelist '
                 'WHERE '+table+'_corrected.id = deletelist.id;')
        cursor.execute(query)

        #: Generate a table of junctions with unique junction geometry and number of participating lines
        query = ('CREATE temp table '+table+'points on commit DROP as '
                 '(SELECT distinct (st_dump(points.geom)).geom, count(points.id) as pcount '
                 'FROM (SELECT st_startpoint(t.geom) as geom, t.id FROM '+table+' t union all '
                 'SELECT st_endpoint(t.geom) as geom, t.id FROM '+table+' t ) AS points '
                 'WHERE st_geometrytype(points.geom)=\'ST_Point\' or st_geometrytype(points.geom)=\'ST_MultiPoint\' '
                 'GROUP BY points.geom);')
        cursor.execute(query)

        query = ('CREATE INDEX '+table+'_points_geom_idx ON '+table+'points USING GIST (geom);')
        cursor.execute(query)

        #: Update the startpoint of a line feature in the corrected table to the geometry of a junction,
        # if it is within the threshold to that junction and not already intersecting
        query = ('UPDATE '+table+'_corrected SET geom = subq.geom FROM '
                 '(SELECT st_setpoint(ref1.geom, 0, p.geom) as geom, ref1.id FROM '+table+'_corrected ref1, '+table+'points p '
                 'WHERE ST_DWithin(st_startpoint(ref1.geom), p.geom,'+threshold+') '
                 'AND NOT st_equals(st_startpoint(ref1.geom), p.geom) and p.pcount>1) as subq '
                 'WHERE '+table+'_corrected.id = subq.id;')
        cursor.execute(query)

        #: Update the endpoint of a line feature in the corrected table to the geometry of a junction,
        # if it is within the threshold to that junction and not already intersecting
        query = ('UPDATE '+table+'_corrected SET geom = subq.geom FROM '
                 '(SELECT st_setpoint(ref1.geom, ST_NPoints(ref1.geom)-1, p.geom) as geom, ref1.id '
                 'FROM '+table+'_corrected ref1, '+table+'points p '
                 'WHERE ST_DWithin(st_endpoint(ref1.geom), p.geom,'+threshold+') '
                 'AND NOT st_equals(st_endpoint(ref1.geom), p.geom) and p.pcount>1) as subq '
                 'WHERE '+table+'_corrected.id = subq.id;')
        cursor.execute(query)

        #: Update the startpoint of a line feature in the corrected table to the closest point on a line,
        # if it is within the threshold to that line and not already intersecting
        query = ('UPDATE '+table+'_corrected SET geom = subq.geom FROM '
                 '(SELECT st_setpoint(ref1.geom, 0, st_closestpoint(ST_AsMultiPoint(ref2.geom), st_startpoint(ref1.geom))) as geom, ref1.id '
                 'FROM '+table+'_corrected ref1, '+table+'_corrected ref2 '
                 'WHERE ref1.id <> ref2.id and ST_DWithin(st_startpoint(ref1.geom), ref2.geom,'+threshold+') '
                 'AND NOT st_contains(ref2.geom,st_startpoint(ref1.geom)) '
                 'and ST_Distance(st_startpoint(ref1.geom), st_closestpoint(ST_AsMultiPoint(ref2.geom),st_startpoint(ref1.geom)))<'+threshold+') as subq '
                 'WHERE '+table+'_corrected.id = subq.id;')
        cursor.execute(query)

        #: Update the endpoint of a line feature in the corrected table to the closest point on a line,
        # if it is within the threshold to that line and not already intersecting
        query = ('UPDATE '+table+'_corrected SET geom = subq.geom FROM '
                 '(SELECT st_setpoint(ref1.geom, ST_NPoints(ref1.geom)-1, st_closestpoint(ST_AsMultiPoint(ref2.geom), st_endpoint(ref1.geom))) as geom, ref1.id '
                 'FROM '+table+'_corrected ref1, '+table+'_corrected ref2 '
                 'WHERE ref1.id <> ref2.id and ST_DWithin(st_endpoint(ref1.geom), ref2.geom,'+threshold+') '
                 'and not st_contains(ref2.geom,st_endpoint(ref1.geom)) '
                 'and ST_Distance(st_endpoint(ref1.geom), st_closestpoint(ST_AsMultiPoint(ref2.geom),st_endpoint(ref1.geom)))<'+threshold+') as subq '
                 'WHERE '+table+'_corrected.id = subq.id;')
        cursor.execute(query)
        #connection.commit()
        #connection.close()

    def presplit_dataset(self, table, outtable, keepcolumns={}, streetname_column='name'):
        """Split line features of the given table on intersections.
        :param table: the table that should be splitted
        """
        #: Build strings for columns that should be included in presplitted table
        kc_str1 = ''
        kc_str2 = ''
        kc_str3 = ''
        for k in keepcolumns:
            kc_str1 += ', ' + k + ' ' + keepcolumns.get(k)
            kc_str2 += ', ' + k
            kc_str3 += ', l.' + k

        #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor #connection.cursor()
        query = ('DROP TABLE IF EXISTS '+outtable+';')
        cursor.execute(query)

        query = ('DROP INDEX IF EXISTS '+table+'_id_idx;')
        cursor.execute(query)

        query = ('CREATE INDEX '+table+'_id_idx on '+table+' USING btree(id);')
        cursor.execute(query)

        query = ('CREATE TABLE '+outtable+
                 ' (id bigserial PRIMARY KEY, old_id integer, sub_id integer, '
                 ' name varchar, direction numeric '+kc_str1+');')
        cursor.execute(query)

        query = ('SELECT addGeometryColumn(\''+outtable+'\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid FROM '+table+' WHERE geom IS NOT NULL LIMIT 1), '
                 '(SELECT geometrytype(geom) FROM '+table+' limit 1), 2);')
        cursor.execute(query)

        query = ('CREATE INDEX '+outtable+'_geom_idx ON '+outtable+'  USING GIST (geom);')
        cursor.execute(query)


        #: Create table with intersections of features to generate a list participating lines
        query = ('CREATE TEMP TABLE intergeom_'+table+' ON COMMIT DROP AS '
                 '(SELECT ST_Intersection(t1.geom, t2.geom) AS g, '
                 'ST_Startpoint(t1.geom) AS sp, '
                 'ST_Endpoint(t1.geom) AS ep, t1.id AS l1id, t2.id AS l2id, t1.geom AS line, '
                 'Count(Distinct t1.id) AS roads_count '
                 'FROM '+table+' AS t1, '+table+' AS t2 '
                 'WHERE t1.id <> t2.id and ST_Intersects(t1.geom, t2.geom) '
                 'GROUP BY g, l1id, l2id, line, sp, ep);')
        cursor.execute(query)

        #: Extract a list of IDs of participating lines and the intersection as fraction of line1 and create index
        query = ('CREATE TEMP TABLE interloc_'+table+' ON COMMIT DROP AS '
                 '(SELECT * '
                 'FROM ((SELECT l1id, l2id, st_linelocatepoint(foo.line, foo.g) AS locus '
                 'FROM (SELECT l1id, l2id, (st_dump(g)).geom AS g, line '
                 'FROM intergeom_'+table+
                 ' WHERE st_geometrytype(g)=\'ST_Point\' or st_geometrytype(g)=\'ST_MultiPoint\') AS foo)) AS bar '
                 'WHERE locus<>0 and locus<>1);')
        cursor.execute(query)

        query = ('CREATE INDEX interloc_'+table+'_id_idx on interloc_'+table+'(l1id);')
        cursor.execute(query)

        #: Insert all splitted parts of the intersecting features into the corrected table
        query = ('INSERT INTO '+outtable+' '
                 '(old_id, sub_id, geom, name, direction '+kc_str2+') '
                 '(WITH cut_locations AS '
                 '(SELECT l1id AS lid, locus FROM interloc_'+table+' UNION ALL '
                 'SELECT i.l1id AS lid, 0 AS locus '
                 'FROM interloc_'+table+' i left join '+table+' b on (i.l1id = b.id) UNION ALL '
                 'SELECT i.l1id AS lid, 1 AS locus '
                 'FROM interloc_'+table+' i left join '+table+' b on (i.l1id = b.id) '
                 'order BY lid, locus), '
                 'loc_WITH_idx AS ('
                 'SELECT lid, locus, row_number() over (partition BY lid order BY locus) AS idx '
                 'FROM cut_locations) '
                 'SELECT l.id, loc1.idx AS sub_id, '
                 'st_linesubstring(l.geom, loc1.locus, loc2.locus) AS geom, l.'+streetname_column+' AS name, '
                 'ST_AZIMUTH(st_startpoint(st_linesubstring(l.geom, loc1.locus, loc2.locus)),'
                 'st_endpoint(st_linesubstring(l.geom, loc1.locus, loc2.locus))) AS direction '+kc_str3+' '
                 'FROM loc_WITH_idx loc1 join loc_WITH_idx loc2 '
                 'USING (lid) join '+table+' l on (l.id = loc1.lid) '
                 'WHERE loc2.idx = loc1.idx+1 '
                 'and geometryType(st_linesubstring(l.geom, loc1.locus, loc2.locus)) = \'LINESTRING\');')
        cursor.execute(query)

        #: Insert all other, non-intersecting line features to the corrected features table
        query = ('INSERT INTO '+outtable+' '
                 '(old_id,sub_id, geom, name, direction '+kc_str2+') '
                 '(WITH used AS (SELECT distinct old_id FROM '+outtable+') '
                 'SELECT id, 1 AS sub_id, geom, '+streetname_column+', '
                 'ST_AZIMUTH(st_startpoint(geom),'
                 'st_endpoint(geom)) AS direction '+kc_str2+' '
                 'FROM '+table+' '
                 'WHERE id not in (SELECT * FROM used));')
        cursor.execute(query)

    def generate_junctions(self, table):
        """Generates a table with junctionpoints and a table of intersectionpoints which build a junction and calculates
        the number of participating lines for the junctionpoints and the azimuth angles for the intersectionpoints.

        :param table: the table with line features used to generate the tables for junction and intersection points
        """

        #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor #connection.cursor()

        # Index droppen und neu erstellen für ref-Daten
        query = ('DROP INDEX IF EXISTS '+table+'_id_idx;')
        cursor.execute(query)
        query = ('CREATE INDEX '+table+'_id_idx on '+table+' USING btree(id);')
        cursor.execute(query)

        query = 'DROP TABLE IF EXISTS '+table+'_points;'
        cursor.execute(query)

        query = 'DROP TABLE IF EXISTS '+table+'_junctions;'
        cursor.execute(query)

        query = 'DROP INDEX IF EXISTS '+table+'_points_geom_idx;'
        cursor.execute(query)

        #: Recreate tables if they already exist
        if DEBUG:
            query = ('CREATE TABLE '+table+'_points '
                     '(id bigserial PRIMARY KEY, matched boolean, parentline_id integer, junction_id integer, '
                     'azimuth numeric);')
            cursor.execute(query)
        else:
            query = ('CREATE TEMP TABLE '+table+'_points'
                     '(id bigserial PRIMARY KEY, matched boolean, parentline_id integer, junction_id integer, '
                     'azimuth numeric) ON COMMIT DROP;')
            cursor.execute(query)

        query = ('SELECT addGeometryColumn (\''+table+'_points\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid '
                 'FROM '+table+' '
                 'WHERE geom IS NOT NULL LIMIT 1),\'POINT\',2);')
        cursor.execute(query)

        if DEBUG:
            query = ('CREATE TABLE '+table+'_junctions '
                     '(id bigserial PRIMARY KEY, roads_count integer, found_partner integer);')
            cursor.execute(query)
        else:
            query = ('CREATE TEMP TABLE '+table+'_junctions '
                     '(id bigserial PRIMARY KEY, roads_count integer, found_partner integer) ON COMMIT DROP;')
            cursor.execute(query)

        query = ('SELECT addGeometryColumn (\''+table+'_junctions\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid FROM '+table+' '
                 'WHERE geom IS NOT NULL LIMIT 1),\'POINT\',2);')
        cursor.execute(query)

        #: Create table with intersections of features to generate a list of intersection points
        query = ('CREATE TEMP TABLE intergeom'+table+' ON COMMIT DROP AS '
                 '(SELECT ST_Intersection(t1.geom, t2.geom) AS g,'
                 'ST_Startpoint(t1.geom) AS sp,'
                 'ST_Endpoint(t1.geom) AS ep, '
                 't1.id AS l1id, t2.id AS l2id,'
                 't1.geom AS line,'
                 'Count(Distinct t1.id) AS roads_count '
                 'FROM '+table+' AS t1, '+table+' AS t2 '
                 'WHERE t1.id <> t2.id and ST_Intersects(t1.geom, t2.geom) '
                 'GROUP BY g, l1id, l2id, line, sp, ep);')
        cursor.execute(query)

        ##: Insert startpoints from non-intersecting linefeatures into table _points
        #query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
        #         '(SELECT ST_PointN(geom, 1) as geom, t.id as parentline_id, false as matched '
        #         'FROM '+table+' t)')
        #cursor.execute(query)
        #
        ##: Insert endpoints from non-intersecting linefeatures into table _points
        #query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
        #         '(SELECT ST_PointN(geom, ST_NumPoints(geom)) as geom, t.id as parentline_id, false as matched '
        #         'FROM '+table+' t)')
        #cursor.execute(query)

        #: Create table _points with distinct start-, end- and intersection points from previous table
        query = ('INSERT INTO '+table+'_points '
                 '(geom, parentline_id, matched) '
                 '(SELECT distinct (st_dump(points.geom)).geom, points.l1id, false AS matched '
                 'FROM (SELECT it.g AS geom, l1id, ep '
                 'FROM intergeom'+table+' it union all '
                 'SELECT it.sp AS geom, l1id, ep FROM intergeom'+table+' it union all '
                 'SELECT it.ep AS geom, l1id, ep FROM intergeom'+table+' it) AS points '
                 'WHERE st_geometrytype(points.geom)=\'ST_Point\' or st_geometrytype(points.geom)=\'ST_MultiPoint\');')
        cursor.execute(query)

        #: Also insert startpoints from non-intersecting linefeatures into table _points
        #query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
        #         '(SELECT ST_PointN(geom, 1) as geom, t.id as parentline_id, false as matched '
        #         'FROM '+table+' t WHERE not exists (SELECT 1 FROM '+table+'_points pts '
        #         'WHERE st_dwithin(geom, pts.geom,0.000000000001)))')
        #cursor.execute(query)

        #: Also insert endpoints from non-intersecting linefeatures into table _points
        #query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
        #         '(SELECT ST_PointN(geom, ST_NumPoints(geom)) as geom, t.id as parentline_id, false as matched '
        #         'FROM '+table+' t WHERE not exists (SELECT 1 FROM '+table+'_points pts '
        #         'WHERE st_dwithin(geom, pts.geom,0.000000000001)))')
        #cursor.execute(query)

        query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
                 '(SELECT st_endpoint(t.geom) as geom, t.id as parentline_id, false as matched '
                 'FROM '+table+' t WHERE not exists (SELECT 1 FROM intergeom'+table+' '
                 'WHERE id=intergeom'+table+'.l1id));')
        cursor.execute(query)

        query = ('INSERT INTO '+table+'_points (geom, parentline_id, matched) '
                 '(SELECT st_startpoint(t.geom) as geom, t.id as parentline_id, false as matched '
                 'FROM '+table+' t WHERE not exists (SELECT 1 FROM intergeom'+table+' '
                 'WHERE id=intergeom'+table+'.l1id));')
        cursor.execute(query)

        #: Insert all unique points as junctions into table _junctions and count the number of points in junction
        query = ('INSERT INTO '+table+'_junctions '
                 '(roads_count, geom) '
                 '(SELECT count(tp.geom), tp.geom '
                 'FROM '+table+'_points tp '
                 'GROUP BY tp.geom);')
        cursor.execute(query)

        query = ('CREATE INDEX '+table+'_junctions_geom_idx ON '+table+'_junctions USING GIST (geom);')
        cursor.execute(query)

        #: Update _points table with junction id of the junction they are part of
        query = ('UPDATE '+table+'_points SET junction_id = f.tjid '
                 'FROM (SELECT tj.id AS tjid, tp.id AS id '
                 'FROM '+table+'_junctions tj, '+table+'_points tp '
                 'WHERE st_dwithin(tj.geom, tp.geom, 0.00000000001)) AS f '
                 'WHERE f.id = '+table+'_points.id;')
        cursor.execute(query)

        #: Update _points table with calculated azimuth angle of the line the point is being startpoint of
        query = ('UPDATE '+table+'_points SET azimuth = f.azimuth '
                 'FROM (SELECT ST_AZIMUTH(tp.geom, st_pointn(it.line,2)) AS azimuth, tp.id AS id '
                 'FROM '+table+'_points tp, intergeom'+table+' it '
                 'WHERE it.l1id = tp.parentline_id and st_equals(tp.geom,st_startpoint(it.line))) AS f '
                 'WHERE f.id = '+table+'_points.id;')
        cursor.execute(query)

        #: Update _points table with calculated azimuth angle of the line the point is being endpoint of
        query = ('UPDATE '+table+'_points SET azimuth = f.azimuth '
                 'FROM (SELECT ST_AZIMUTH(tp.geom, st_pointn(it.line,ST_NPoints(it.line)-1)) AS azimuth, tp.id AS id '
                 'FROM '+table+'_points tp, intergeom'+table+' it '
                 'WHERE it.l1id = tp.parentline_id and st_equals(tp.geom,st_endpoint(it.line))) AS f '
                 'WHERE f.id = '+table+'_points.id;')
        cursor.execute(query)

        query = ('CREATE INDEX '+table+'_points_geom_idx ON '+table+'_points  USING GIST (geom);')
        cursor.execute(query)

    def junction_matching(self, basetable, table1, table2, searchradius, azimuthdifftolerance, max_azdiff, max_distancediff,
                          max_roads_countdiff):
        """Used to match the junctions of two datasets to determine if the junctions in table1 have matching partners
        in table2. Junctions from table1 without a matchingpartner or their participating intersectionpoints are then
        used to generate cutpoints in table2, see method cutpoint_creation.

        :param table1: first inputtable with junctions for the matching process
        :param table2: second inputtable with junctions for the matching process
        """
        #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor #connection.cursor()

        #: Creates table with potential junction pairs of the two datasets using fast parameters and the given limits
        query = ('CREATE TEMP TABLE potentialpairs ON COMMIT DROP AS '
                 'WITH neighbours AS '
                 '(SELECT t1j.id AS t1j_id, t2j.id AS t2j_id '
                 'FROM '+table1+'_junctions t1j, '+table2+'_junctions t2j '
                 'WHERE ST_DWithin(t1j.geom, t2j.geom, '+searchradius+')) '
                 'SELECT abs((abs((t1p.azimuth-t2p.azimuth))+'+azimuthdifftolerance+') % '
                 +two_pi+' - '+azimuthdifftolerance+') AS azdiff, '
                 't1p.id AS t1p_id, t2p.id AS t2p_id, neighbours.t2j_id, neighbours.t1j_id '
                 'FROM '+table1+'_points t1p, '+table2+'_points t2p, neighbours '
                 'WHERE t2p.junction_id = neighbours.t2j_id and t1p.junction_id = neighbours.t1j_id '
                 'and abs((abs((t1p.azimuth-t2p.azimuth))+'+azimuthdifftolerance+') % '
                 +two_pi+' - '+azimuthdifftolerance+')<'+azimuthdifftolerance+' order BY t1j_id;')
        cursor.execute(query)

        query = ('DROP TABLE IF EXISTS potentialpairs2;')
        cursor.execute(query)
        #query = ('DROP TABLE IF EXISTS found;')
        #cursor.execute(query)

        #: Creates table with potential sub-junction-point (start- endpoints of lines) pairs of the two datasets
        query = ('CREATE TEMP TABLE potentialpairs2 '
                 '(t1j_id integer, t2j_id integer, t1p_id integer, t2p_id integer, '
                 'found_partner boolean default false, azdiff numeric);')
        cursor.execute(query)

        #: Fill table potentialpairs2 with all potential pairs and parameters on sub-junction-point level
        query = ('INSERT INTO potentialpairs2 (t1j_id, t2j_id, t1p_id, t2p_id, azdiff) '
                 '(SELECT dists.t1j_id, dists.t2j_id, dists.t1p_id,best.t2p_id,best.azdiff '
                 'FROM '
                 '(SELECT potentialpairs.t1j_id, potentialpairs.t2j_id, potentialpairs.t1p_id, potentialpairs.t2p_id, '
                 'potentialpairs.azdiff FROM (SELECT t1j_id, t2j_id, t1p_id, min(azdiff) AS azdiff '
                 'FROM potentialpairs '
                 'WHERE not exists (SELECT 1 FROM potentialpairs2 '
                 'WHERE potentialpairs2.t2j_id = potentialpairs.t2j_id and '
                 'potentialpairs2.t1j_id = potentialpairs.t1j_id and '
                 'potentialpairs2.t2p_id=potentialpairs.t2p_id) '
                 'GROUP BY t1j_id,t2j_id, t1p_id order BY min(azdiff)) p, potentialpairs '
                 'WHERE potentialpairs.t2j_id = p.t2j_id and potentialpairs.t1j_id = p.t1j_id '
                 'and potentialpairs.azdiff = p.azdiff) best, (SELECT distinct t1j_id, t2j_id, t1p_id '
                 'FROM potentialpairs order BY t1j_id) dists WHERE dists.t2j_id = best.t2j_id '
                 'and dists.t1j_id = best.t1j_id and best.t1p_id = dists.t1p_id);')
        cursor.execute(query)


        #: Just keep potential pairs (on sub-junction level) with min. azimuth difference
        query = ('DELETE FROM potentialpairs2 pp2 '
                 'USING (SELECT t1j_id, t2j_id, t2p_id, min(azdiff) AS azdiff '
                 'FROM potentialpairs2 GROUP BY t1j_id, t2j_id, t2p_id) AS f '
                 'WHERE pp2.t1j_id = f.t1j_id and pp2.t2j_id=f.t2j_id '
                 'and pp2.t2p_id = f.t2p_id and pp2.azdiff!=f.azdiff;')
        cursor.execute(query)
        self.connection.commit()

        #: Create a table with the entries of potentialpairs2, which calculated parameters are within the given limits
        #: and save the wighted sum of parameters as junction_diff
        query = ('CREATE TEMP TABLE foundmatches ON COMMIT DROP AS '
                 'select t1j_id, t2j_id, t1p_ids, t2p_ids, azdiff, '
                 '(rel_azdiff*2+dist_diff*3+rc_diff)/6.0 as junction_diff '
                 'from (SELECT t1j_id, t2j_id, array_agg(t1p_id) AS t1p_ids, array_agg(t2p_id) AS t2p_ids, '
                 'sum(azdiff) AS azdiff, '
                 'sum(azdiff)/count(t2p_id)/ '+max_azdiff+' as rel_azdiff, '
                 'st_distance(t2j.geom, t1j.geom)/ '+searchradius+' as dist_diff, '
                 'abs(t2j.roads_count-t1j.roads_count)/'+max_roads_countdiff+' as rc_diff '
                 'FROM potentialpairs2 pp2, '+table1+'_junctions t1j, '+table2+'_junctions t2j '
                 'WHERE pp2.t2j_id = t2j.id and pp2.t1j_id = t1j.id '
                 'GROUP BY t1j_id, t2j_id, t2j.geom,t1j.geom,t2j.roads_count,t1j.roads_count order BY t1j_id) subquery '
                 'where rel_azdiff<1 and dist_diff < 1 and rc_diff < 1;')
        cursor.execute(query)

        # If there are still multiple matches for an entry of table1, delete all but the one with min. junction_diff
        query = ('DELETE FROM foundmatches '
                 'USING (SELECT distinct t1j_id, min(junction_diff) AS junction_diff '
                 'FROM foundmatches GROUP BY t1j_id) AS f, '
                  '(SELECT * FROM (SELECT t1j_id, count(t2j_id) AS t2j_count '
                  'FROM foundmatches GROUP BY t1j_id order BY t1j_id) AS subq '
                  'WHERE subq.t2j_count!=1) AS f2 '
                 'WHERE foundmatches.t1j_id=f.t1j_id and f.t1j_id = f2.t1j_id '
                  'and foundmatches.junction_diff!=f.junction_diff;')
        cursor.execute(query)
        query = ('DELETE FROM foundmatches '
                 'USING (SELECT distinct t2j_id, min(junction_diff) AS junction_diff '
                 'FROM foundmatches GROUP BY t2j_id) AS f, '
                 '(SELECT * FROM (SELECT t2j_id, count(t1j_id) AS t2j_count '
                 'FROM foundmatches GROUP BY t2j_id order BY t2j_id) AS subq '
                 'WHERE subq.t2j_count!=1) AS f2 '
                 'WHERE foundmatches.t2j_id=f.t2j_id and f.t2j_id = f2.t2j_id '
                 'and foundmatches.junction_diff!=f.junction_diff;')
        cursor.execute(query)

        #: Create a table with deviation lines between the matched junctions of the two datasets
        query = 'DROP TABLE IF EXISTS '+basetable+'_junction_deviationlines;'
        cursor.execute(query)
        query = ('CREATE TABLE '+basetable+'_junction_deviationlines AS SELECT st_makeline(refj.geom, osmj.geom) AS geom '
                 'FROM (SELECT * FROM foundmatches) AS ff, '+table2+'_junctions osmj,'+table1+'_junctions refj '
                 'WHERE ff.t1j_id = refj.id and ff.t2j_id = osmj.id;')
        cursor.execute(query)

        query = ('UPDATE '+table2+'_points SET matched = true '
                 'FROM (SELECT * FROM foundmatches) AS ff '
                 'WHERE ff.t2j_id = '+table2+'_points.junction_id;')
        cursor.execute(query)
        query = ('UPDATE '+table1+'_points SET matched = true '
                 'FROM (SELECT * FROM foundmatches) AS ff '
                 'WHERE ff.t1j_id = '+table1+'_points.junction_id;')
        cursor.execute(query)

        #query = ('UPDATE '+table2+'_points SET matched = true '
        #         'FROM (SELECT unnest(t2p_ids) AS t2p_ids FROM foundmatches) AS f '
        #         'WHERE '+table2+'_points.id = f.t2p_ids;')
        #cursor.execute(query)
        #query = ('UPDATE '+table1+'_points SET matched = true '
        #         'FROM (SELECT unnest(t1p_ids) AS t1p_ids FROM foundmatches) AS f '
        #         'WHERE '+table1+'_points.id = f.t1p_ids;')
        #cursor.execute(query)

    def cutpoint_creation(self, table1, table2, searchradius, azimuthdifftolerance, maxcheckpointanglediff):
        """Create cutpoints for the line features of table1 based on non-matched junction points of table2, which
        can be used to split the line features.

        :param table1: first inputtable for the cutpoint creation process
        :param table2: second inputtable for the cutpoint creation process
        """

        #: connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor  # connection.cursor()

        query = ('DROP TABLE IF EXISTS '+table1+'_cutpoints;')
        cursor.execute(query)

        #: Recreate tables if they already exist
        if DEBUG:
            query = ('CREATE TABLE '+table1+'_cutpoints'
                     '(id bigserial PRIMARY KEY, parentline_id integer, sourcepointid integer,sourcelineid integer,'
                     'locus numeric, azimuth numeric, distance numeric, iscurved boolean default false);')
            cursor.execute(query)
        else:
            query = ('CREATE TEMP TABLE '+table1+'_cutpoints '
                     '(id bigserial PRIMARY KEY, parentline_id integer, sourcepointid integer,sourcelineid integer,'
                     'locus numeric, azimuth numeric, distance numeric, iscurved boolean) ON COMMIT DROP;')
            cursor.execute(query)

        query = ('SELECT addGeometryColumn (\''+table1+'_cutpoints\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid FROM '+table1+' WHERE geom IS NOT NULL LIMIT 1),\'POINT\',2);')
        cursor.execute(query)

        #: Calculate and insert cutpoints for line features of table1 using non-matched sub-junction-points of table2
        #: that are within the searchradius of a line of table1. Each cutpoint has two sub-cutpoint-points: the nodes
        #: of the splitted lines
        query = ('INSERT INTO '+table1+'_cutpoints '
                 '(parentline_id, sourcepointid, sourcelineid, locus, geom, distance) '
                 '(SELECT l1id, t1id, sourcelineid, locus, geom, distance '
                 'FROM '
                    '(SELECT t1.id AS l1id, t2p.parentline_id AS sourcelineid, t2p.id AS t1id, '
                        'st_linelocatepoint(t1.geom, st_closestpoint(t1.geom,t2p.geom)) AS locus, '
                        'st_closestpoint(t1.geom,t2p.geom) AS geom, '
                        'st_distance(st_closestpoint(t1.geom,t2p.geom), t2p.geom) AS distance '
                    'FROM '+table1+' t1, '+table2+'_points t2p, '+table2+' t2 '
                    'WHERE t2p.matched = false and t2p.parentline_id = t2.id '
                        'and ST_DWithin(t2p.geom, t1.geom, '+searchradius+')) AS subq '
                 'WHERE locus < 0.9999 and locus > 0.0001);')
        cursor.execute(query)
        # and ((ST_DWithin(t2p.geom, st_startpoint(reflines.geom),0.00007) or
        # ST_DWithin(t2p.geom,st_endpoint(reflines.geom),0.00007)) or not
        # (ST_DWithin(st_closestpoint(osm.geom,t2p.geom),st_startpoint(osm.geom),0.00007) or
        # ST_DWithin(st_closestpoint(osm.geom,t2p.geom),st_endpoint(osm.geom),0.00007)))

        #: Calculate the azimuth for the cutpoints by interpolating a point in direction to the endpoint, only if the
        #: fraction of the cutpoint on the line is not very near the endpoint (avoid overflow errors). These azimuth
        #: values may not be right for the cutpoints and will be updated in the query after the next
        query = ('UPDATE '+table1+'_cutpoints SET azimuth = f.azimuth '
                 'FROM (SELECT ST_AZIMUTH(st_lineinterpolatepoint(t1.geom, t1cp.locus), '
                 'st_lineinterpolatepoint(t1.geom, t1cp.locus+0.000001)) AS azimuth, t1cp.id AS id, '
                 't1cp.sourcepointid AS srcpid '
                 'FROM '+table1+'_cutpoints t1cp, '+table1+' t1 '
                 'WHERE t1.id = t1cp.parentline_id and t1cp.locus !=0 and t1cp.locus<0.999999) AS f '
                 'WHERE f.id = '+table1+'_cutpoints.id;')
        cursor.execute(query)

        #: Not yet completely implemented! Using the parameter iscureved to handle cutpoint deletion on curved lines,
        #: which is a little hard, because of wrong azimuth values
        query = ('UPDATE '+table1+'_cutpoints SET iscurved = TRUE '
                 'FROM (SELECT ST_AZIMUTH(st_lineinterpolatepoint(l.geom, cp.locus - 0.00001 / st_length(l.geom)),'
                 'st_lineinterpolatepoint(l.geom, cp.locus+0.00001 / st_length(l.geom))) AS segmentazimuth, '
                 'cp.azimuth as pointazimuth, cp.id AS id, cp.sourcepointid AS srcpid '
                 'FROM '+table1+'_cutpoints cp, '+table1+' l WHERE l.id = cp.parentline_id '
                 'and cp.locus >0.00001 / st_length(l.geom) and cp.locus<(1 - 0.00001 / st_length(l.geom))) AS f '
                 'WHERE f.id = '+table1+'_cutpoints.id '
                 'and (abs((abs((f.segmentazimuth-f.pointazimuth))+0.2))::numeric(8,1) % ('+two_pi+') - 0.2)>0.2;')
        cursor.execute(query)

        #: The azimuth values of the cutpoints will be corrected using the azimuth/orientation values of the points used
        #: to generate the cutpoints. This helps to bybass the problem of different orientation of lines.
        query = ('UPDATE '+table1+'_cutpoints SET azimuth = (t1cp.azimuth+'+pi+') % '+two_pi+' '
                 'FROM '+table1+'_cutpoints t1cp, '+table2+'_points WHERE '+table1+'_cutpoints.id = t1cp.id '
                 'and t1cp.sourcepointid = '+table2+'_points.id '
                 'and abs((abs(('+table2+'_points.azimuth-t1cp.azimuth))+'+azimuthdifftolerance+') % ('+two_pi+') - '
                 +azimuthdifftolerance+')>'+azimuthdifftolerance+';')
        cursor.execute(query)

        #: Now all generated cutpoints which have an azimuth angle difference to their generating point
        #: above the given limit will be deleted.
        query = ('DELETE FROM '+table1+'_cutpoints USING (SELECT t1cp.id AS t1cpid, '
                 'unmatchedendpoints.azimuth AS azimuth FROM (SELECT id, azimuth, geom FROM '+table2+'_points '
                 'WHERE matched=false) AS unmatchedendpoints, (SELECT id, sourcepointid, azimuth '
                 'FROM '+table1+'_cutpoints) AS t1cp '
                 'WHERE t1cp.sourcepointid = unmatchedendpoints.id and '
                 'abs((abs((unmatchedendpoints.azimuth-t1cp.azimuth))+'+azimuthdifftolerance+') % ('
                 +two_pi+'/2.0) - '+azimuthdifftolerance+')>'+azimuthdifftolerance+') AS DELETElist '
                 'WHERE '+table1+'_cutpoints.id = DELETElist.t1cpid;')
                 # and '+table1+'_cutpoints.iscurved = false;'
        cursor.execute(query)

        # Remove cutpoints on line ends, because line ends are already a point
        # DELETE FROM '+table1+'_cutpoints USING (SELECT '+table1+'_cutpoints.id AS t1cpid
        # FROM '+table1+'_cutpoints, (SELECT id, geom FROM '+table1+') AS t1cpline,
        # (SELECT id, geom FROM '+table2+') AS refpointline
        # WHERE '+table1+'_cutpoints.parentline_id = t1cpline.id
        # and refpointline.id = '+table1+'_cutpoints.sourcelineid and st_length(refpointline.geom)>0.0002
        # and st_distance(st_lineinterpolatepoint(t1cpline.geom,'+table1+'_cutpoints.locus),
        # st_startpoint(t1cpline.geom))<0.0002) AS DELETElist
        # WHERE '+table1+'_cutpoints.id = DELETElist.t1cpid;'
        # cursor.execute(query)

        # query = 'DELETE FROM '+table1+'_cutpoints USING (SELECT '+table1+'_cutpoints.id AS t1cpid
        # FROM '+table1+'_cutpoints, (SELECT id, geom FROM '+table1+') AS t1cpline,
        # (SELECT id, geom FROM '+table2+') AS refpointline
        # WHERE '+table1+'_cutpoints.parentline_id = t1cpline.id
        # and refpointline.id = '+table1+'_cutpoints.sourcelineid and st_length(refpointline.geom)>0.0002
        # and st_distance(st_lineinterpolatepoint(t1cpline.geom,'+table1+'_cutpoints.locus),
        # st_endpoint(t1cpline.geom))<0.0002) AS DELETElist
        # WHERE '+table1+'_cutpoints.id = DELETElist.t1cpid;'
        # cursor.execute(query)

        #: From all the generated cutpoints of each unmatched-point in table2, all besides the one closest to the
        #: generating point will be deleted. See also next query.
        query = ('DELETE FROM '+table1+'_cutpoints USING (SELECT distinct t1cp.sourcepointid AS id, '
                 'min(t1cp.distance) AS distance FROM '+table1+'_cutpoints t1cp, '+table2+'_points t2p '
                 'WHERE t1cp.sourcepointid = t2p.id GROUP BY t1cp.sourcepointid) AS closestpoints, '
                 '(SELECT * FROM (SELECT id, count(sourcepointid) AS spcount FROM '+table1+'_cutpoints GROUP BY id '
                 'order BY id) AS subq WHERE subq.spcount!=1) AS multiplesp '
                 'WHERE '+table1+'_cutpoints.id=multiplesp.id and closestpoints.id = multiplesp.id '
                 'and '+table1+'_cutpoints.distance != closestpoints.distance;')
        cursor.execute(query)

        query = ('DELETE FROM '+table1+'_cutpoints USING (SELECT sourcepointid, min(distance) AS mindist '
                 'FROM '+table1+'_cutpoints GROUP BY sourcepointid) AS minlist '
                 'WHERE '+table1+'_cutpoints.sourcepointid = minlist.sourcepointid and '
                 +table1+'_cutpoints.distance != minlist.mindist;')
        cursor.execute(query)

        #: Recreate tables for Cutpoint Checkpoints if they already exist
        query = 'DROP TABLE IF EXISTS '+table1+'_cutcheckpoints;'
        cursor.execute(query)

        if DEBUG:
            query = ('CREATE TABLE '+table1+'_cutcheckpoints(id bigserial PRIMARY KEY, parentline_id integer, '
                     'sourcepointid integer,sourcelineid integer,locus numeric, azimuth numeric);')
            cursor.execute(query)
        else:
            query = ('CREATE TEMP TABLE '+table1+'_cutcheckpoints(id bigserial PRIMARY KEY, parentline_id integer, '
                     'sourcepointid integer,sourcelineid integer,locus numeric, azimuth numeric) ON COMMIT DROP;')
            cursor.execute(query)

        query = ('SELECT addGeometryColumn (\''+table1+'_cutcheckpoints\',\'geom\',(SELECT ST_SRID(geom) AS srid '
                 'FROM '+table2+' WHERE geom IS NOT NULL LIMIT 1),\'POINT\',2);')
        cursor.execute(query)

        #: Create a table with checkpoints for each cutpoint in a given radius (this process is similar to the creation
        #: of cutpoints). The checkpoints help to determine, if the created cutpoint is justifiably on the line
        #: and there is no other line which could be matched with the line, if there wouldn't be a cutpoint.
        query = ('INSERT INTO '+table1+'_cutcheckpoints (parentline_id, sourcepointid, sourcelineid, locus, geom) '
                 '(SELECT l1id, id, sourcelineid, locus, geom '
                 'FROM (SELECT t2.id AS l1id, t1cp.parentline_id AS sourcelineid, t1cp.id, '
                 'st_linelocatepoint(t2.geom, st_closestpoint(t2.geom,t1cp.geom)) AS locus, '
                 'st_closestpoint(t2.geom,t1cp.geom) AS geom FROM '+table2+' t2, '+table1+'_cutpoints t1cp '
                 'WHERE ST_DWithin(t1cp.geom, t2.geom, '+searchradius+')) AS subq '
                 'WHERE locus < 0.9999 and locus > 0.0001);')
        cursor.execute(query) #abs distanzbeschränkung
        # and not (ST_DWithin(st_closestpoint(t2.geom,o.geom),st_startpoint(t2.geom),0.00002)
        # or ST_DWithin(st_closestpoint(t2.geom,o.geom),st_endpoint(t2.geom),0.00002))

        #: Calculate the azimuth for the linesegment from the checkpoint to an interpolated point in line direction
        query = ('UPDATE '+table1+'_cutcheckpoints SET azimuth = t1cpazimuth.azimuth '
                 'FROM (SELECT ST_AZIMUTH(st_lineinterpolatepoint(t2.geom, t1cp.locus), '
                 'st_lineinterpolatepoint(t2.geom, t1cp.locus+0.000001)) AS azimuth, t1cp.id AS id '
                 'FROM '+table1+'_cutcheckpoints t1cp, '+table2+' t2 '
                 'WHERE t2.id = t1cp.parentline_id and t1cp.locus != 1 and t1cp.locus !=0 '
                 'and t1cp.locus<0.999999) AS t1cpazimuth '
                 'WHERE t1cpazimuth.id = '+table1+'_cutcheckpoints.id;')
        cursor.execute(query)

        #: Correct the direction and azimuth of the checkpoint to match the cutpoints orientation
        query = ('UPDATE '+table1+'_cutcheckpoints SET azimuth = (t1cp.azimuth+'+pi+') % '+two_pi+
                 ' FROM '+table1+'_cutcheckpoints t1cp, '+table1+'_cutpoints '
                 'WHERE '+table1+'_cutcheckpoints.id = t1cp.id and t1cp.sourcepointid = '+table1+'_cutpoints.id '
                 'and abs((abs(('+table1+'_cutpoints.azimuth-t1cp.azimuth))+'+maxcheckpointanglediff+') % '
                 +two_pi+' - '+maxcheckpointanglediff+')>'+maxcheckpointanglediff+';')
        cursor.execute(query)

        #: Delete checkpoint if the difference between the checkpoint-azimuth
        #: and cutpoint-azimtuh is bigger than the defined limit
        query = ('DELETE FROM '+table1+'_cutcheckpoints USING (SELECT t1cpcp.id AS t1cpcpid, '
                 't1cpcp.azimuth AS t1cpcpazimuth FROM (SELECT id, azimuth, sourcepointid, geom '
                 'FROM '+table1+'_cutpoints) AS t1cp, (SELECT id, sourcepointid, azimuth FROM '
                 +table1+'_cutcheckpoints) AS t1cpcp WHERE t1cpcp.sourcepointid = t1cp.id '
                 'and abs((abs((t1cp.azimuth-t1cpcp.azimuth))+'+maxcheckpointanglediff+') %  '
                 +two_pi+' - '+maxcheckpointanglediff+')>'+maxcheckpointanglediff+') AS DELETElist '
                 'WHERE '+table1+'_cutcheckpoints.id = DELETElist.t1cpcpid '
                 'and '+table1+'_cutcheckpoints.azimuth = DELETElist.t1cpcpazimuth;')
        cursor.execute(query)

        # Check if there is a checkpoint that's closer to the cutpoint than the cutpoints sourcepoint,
        # if so delete the cutpoint, because it belongs to another sourcepoint
        query = ('DELETE FROM '+table1+'_cutpoints USING (SELECT t1cp.id FROM (SELECT id, geom, parentline_id, '
                 'sourcepointid FROM '+table1+'_cutcheckpoints) AS t1cpcp, '+table1+'_cutpoints t1cp, '
                 +table2+'_points tpref WHERE t1cpcp.sourcepointid = t1cp.id and '
                 '(t1cpcp.parentline_id != t1cp.sourcelineid) and tpref.id=t1cp.sourcepointid and '
                 'st_distance(t1cp.geom,t1cpcp.geom)+st_distance(t1cp.geom,t1cpcp.geom)*0.1'
                 '<st_distance(t1cp.geom,tpref.geom)) AS DELETElist '
                 'WHERE DELETElist.id = '+table1+'_cutpoints.id;')
        cursor.execute(query)
        print table1

    def linesplit_with_cutpoints(self, table, result_table, keepcolumns={}):
        """This split method uses a set of cutpoints to split the line features of a table and saves the splitted
        features in the result table. The cutpoints used for the splitting process should be created with the
        cutpoint_creation method

        :param table: the input table, which hold the features to be split
        :param result_table: the output table
        """

        #: Build strings for columns that should be included in linesplit result table
        kc_str1 = ''
        kc_str2 = ''
        kc_str3 = ''
        for k in keepcolumns:
            kc_str1 += ', ' + k + ' ' + keepcolumns.get(k)
            kc_str2 += ', ' + k
            kc_str3 += ', l.' + k

        #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = self.cursor #connection.cursor()

        query = ('CREATE TEMP TABLE interloc_'+table+' ON COMMIT DROP AS '
                 '(SELECT cp.parentline_id AS l1id, null AS l2id, locus AS locus FROM '+table+'_cutpoints cp);')
        cursor.execute(query)
        query = 'CREATE INDEX interloc_'+table+'_id_idx on interloc_'+table+'(l1id);'
        cursor.execute(query)

        #: Recreate table for linesplit result if it already exists
        query = ('DROP TABLE IF EXISTS '+result_table+';')
        cursor.execute(query)

        query = ('CREATE TABLE '+result_table+' '
                 '(id bigserial PRIMARY KEY, old_id integer, sub_id integer, '
                 'name varchar, direction numeric '+kc_str1+');')
        cursor.execute(query)
        query = ('SELECT addGeometryColumn(\''+result_table+'\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid '
                 'FROM '+table+' '
                 'WHERE geom IS NOT NULL LIMIT 1),'
                 '(SELECT geometrytype(geom) FROM '+table+' limit 1), 2);')
        cursor.execute(query)
        query = ('CREATE INDEX '+result_table+'_geom_idx ON '+result_table+'  USING GIST (geom);')
        cursor.execute(query)

        #: Insert splitted feature parts into result table
        query = ('INSERT INTO '+result_table+' (old_id, sub_id, geom, name, direction '+kc_str2+') (WITH cut_locations '
                 'AS (SELECT l1id AS lid, locus FROM interloc_'+table+' UNION ALL SELECT i.l1id AS lid, 0 AS locus '
                 'FROM interloc_'+table+' i left join '+table+' b on (i.l1id = b.id) UNION ALL '
                 'SELECT i.l1id AS lid, 1 AS locus FROM interloc_'+table+' i '
                 'left join '+table+' b on (i.l1id = b.id) order BY lid, locus ), '
                 'loc_WITH_idx AS ( SELECT lid, locus, row_number() over (partition BY lid order BY locus) AS idx '
                 'FROM cut_locations) SELECT l.id, loc1.idx AS sub_id, st_linesubstring(l.geom, loc1.locus, loc2.locus)'
                 ' AS geom, l.name AS name, ST_AZIMUTH(st_startpoint(st_linesubstring(l.geom, loc1.locus, loc2.locus)),'
                 'st_endpoint(st_linesubstring(l.geom, loc1.locus, loc2.locus))) AS direction '+kc_str3+' '
                 'FROM loc_WITH_idx loc1 join loc_WITH_idx loc2 USING (lid) join '+table+' l on (l.id = loc1.lid) '
                 'WHERE loc2.idx = loc1.idx+1 and geometryType(st_linesubstring(l.geom, loc1.locus, loc2.locus)) = '
                 '\'LINESTRING\');')
        cursor.execute(query)

        #: Insert non splitted parts into result table
        query = ('INSERT INTO '+result_table+' (old_id, sub_id, geom,name, direction '+kc_str2+') '
                 '(WITH used AS (SELECT distinct old_id FROM '+result_table+') SELECT id, 1 AS sub_id, geom, '
                 'name, ST_AZIMUTH(st_startpoint(geom),st_endpoint(geom)) AS direction '+kc_str2+' '
                 'FROM '+table+' '
                 'WHERE id not in (SELECT * FROM used));')
        cursor.execute(query)

    def noharmonization(self, table, result_table, keepcolumns={}, streetname_column='name'):
            """This split method uses a set of cutpoints to split the line features of a table and saves the splitted
            features in the result table. The cutpoints used for the splitting process should be created with the
            cutpoint_creation method

            :param table: the input table, which hold the features to be split
            :param result_table: the output table
            """

            #: Build strings for columns that should be included in linesplit result table
            kc_str1 = ''
            kc_str2 = ''
            kc_str3 = ''
            for k in keepcolumns:
                kc_str1 += ', ' + k + ' ' + keepcolumns.get(k)
                kc_str2 += ', ' + k
                kc_str3 += ', l.' + k

            #connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
            cursor = self.cursor  # connection.cursor()
            query = ('DROP TABLE IF EXISTS '+result_table+';')
            cursor.execute(query)
            query = ('CREATE TABLE '+result_table+' '
                 '(id bigserial PRIMARY KEY, old_id integer, sub_id integer, '
                 'name varchar, direction numeric '+kc_str1+');')
            cursor.execute(query)
            query = ('SELECT addGeometryColumn(\''+result_table+'\',\'geom\','
                 '(SELECT ST_SRID(geom) AS srid '
                 'FROM '+table+' '
                 'WHERE geom IS NOT NULL LIMIT 1),'
                 '(SELECT geometrytype(geom) FROM '+table+' limit 1), 2);')
            cursor.execute(query)
            query = ('CREATE INDEX '+result_table+'_geom_idx ON '+result_table+'  USING GIST (geom);')
            cursor.execute(query)
            query = ('INSERT INTO '+result_table+' (old_id, sub_id, geom,name, direction '+kc_str2+') '
                 'SELECT id, 1 AS sub_id, geom, '
                 + streetname_column +', ST_AZIMUTH(st_startpoint(geom),st_endpoint(geom)) AS direction '+kc_str2+' '
                 'FROM '+table+';')
            self.cursor.execute(query)

    def harmonize_datasets(self, harmonization_options):
        """Split the line features of two datasets at nearly the same locations to (hopefully) get nearly the same
        segments in both datasets. This tries to minimize 1:M and M:N relationships between matchingpartners and will
        yield in a better line matching result.

        The linesplitting implementation is based on:
        https://github.com/pgRouting/pgrouting/blob/master/src/common/sql/pgrouting_node_network.sql
        (Author: Nicolas Ribot, 2013)

        :param harmonization_options: an object of the HarmonizeOptions Class is used to hold all necessary options,
        see the documentation for HarmonizeOptions Class
        """

        if harmonization_options is None:
            yield 'Error: Harmonization Options not set!'
            return

        #: Shorter parameters for shorter queries
        basetable = harmonization_options.basetable
        reftable = harmonization_options.reftable
        ref_out_table = harmonization_options.basetable+ref_suffix+harmonization_options.outsuffix
        osmtable = harmonization_options.osmtable
        osm_out_table = harmonization_options.basetable+osm_suffix+harmonization_options.outsuffix
        azimuthdifftolerance = str(harmonization_options.azimuthdifftolerance)
        maxcheckpointanglediff = str(harmonization_options.maxcheckpointanglediff)
        searchradius = str(harmonization_options.searchradius)
        max_roads_countdiff = str(harmonization_options.max_roads_countdiff)
        max_azdiff = str(harmonization_options.max_azdiff)
        max_distancediff = str(harmonization_options.max_distancediff)
        keepcolumns_t1 = harmonization_options.keepcolumns_t1
        keepcolumns_t2 = harmonization_options.keepcolumns_t2
        streetnamecol = harmonization_options.streetnamecol

        self.connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        self.cursor = self.connection.cursor()

        if harmonization_options.harmonize:
            #: Clean datasets if options are True
            if harmonization_options.cleanref:
                yield 'Cleaning Reference Dataset'
                self.clean_dataset(reftable, harmonization_options.cleanrefradius, streetnamecol, keepcolumns_t1)
                reftable += '_corrected'
                streetnamecol = 'name'
            if harmonization_options.cleanosm:
                yield 'Cleaning OSM Dataset'
                self.clean_dataset(osmtable, harmonization_options.cleanosmradius, 'name', keepcolumns_t2)
                osmtable += '_corrected'
            #: Presplit queries for reference lines
            if harmonization_options.presplitref:
                yield 'Presplitting Reference Lines'
                self.presplit_dataset(reftable, reftable+'_presplitted', keepcolumns_t1, streetnamecol)
                reftable += '_presplitted'
            if harmonization_options.presplitosm:
                yield 'Presplitting OSM Lines'
                self.presplit_dataset(osmtable, osmtable+'_presplitted', keepcolumns_t2, 'name')
                osmtable += '_presplitted'

            yield 'Generating Reference Junctions'
            self.generate_junctions(reftable)

            yield 'Generating OSM Junctions'
            self.generate_junctions(osmtable)

            yield 'Junction Matching between Reference and OSM Junctions'
            self.junction_matching(basetable, reftable, osmtable, searchradius, azimuthdifftolerance, max_azdiff,
                                   max_distancediff, max_roads_countdiff)

            yield 'Creating Cutpoints for Reference-Dataset based on non-matched junction points'
            self.cutpoint_creation(reftable, osmtable, searchradius, azimuthdifftolerance, maxcheckpointanglediff)

            yield 'Creating Cutpoints for OSM-Dataset based on non-matched junction points'
            self.cutpoint_creation(osmtable, reftable, searchradius, azimuthdifftolerance, maxcheckpointanglediff)

            yield 'Splitting Reference Lines with Reference Cutpoints'
            self.linesplit_with_cutpoints(reftable, ref_out_table, keepcolumns_t1)

            yield 'Splitting OSM Lines with OSM Cutpoints'
            self.linesplit_with_cutpoints(osmtable, osm_out_table, keepcolumns_t2)
        else:
            yield 'No harmonization'
            #self.noharmonization(reftable, ref_out_table, keepcolumns_t1, streetnamecol)
            #self.noharmonization(osmtable, osm_out_table, keepcolumns_t2, 'name')
            #: Clean datasets if options are True
            if harmonization_options.cleanref:
                yield 'Cleaning Reference Dataset'
                self.clean_dataset(reftable, harmonization_options.cleanrefradius, streetnamecol, keepcolumns_t1)
                reftable += '_corrected'
                streetnamecol = 'name'
            if harmonization_options.cleanosm:
                yield 'Cleaning OSM Dataset'
                self.clean_dataset(osmtable, harmonization_options.cleanosmradius, 'name', keepcolumns_t2)
                osmtable += '_corrected'
            #: Presplit queries for reference lines
            if harmonization_options.presplitref:
                yield 'Presplitting Reference Lines'
                self.presplit_dataset(reftable, ref_out_table, keepcolumns_t1, streetnamecol)
                #reftable += '_presplitted'
            if harmonization_options.presplitosm:
                yield 'Presplitting OSM Lines'
                self.presplit_dataset(osmtable, osm_out_table, keepcolumns_t2, 'name')
                #osmtable += '_presplitted'
        self.connection.commit()
        self.connection.close()

    def linematch_datasets(self, linematch_options):
        """Simple Line Matching method to find nearly same Features in both datasets.
        In the first stage of line matching, for each feature in the reference dataset up to numneighbours(10)
        potential neighbours in the osm dataset, based on parameters such as length and area are selected.
        The selection based on length and area is fast, but not precise or significant
        In the second stage, more meaningful parameters are used to decide whether a feature exists in both datasets
        or not, those parameters are st_hausdorffdistance and the mean positional difference of points of the features
        The calculation of the mean positional difference is not fast but the most significant in the matching process;
        for the best result, it should be used in both ways ref-osm, osm-ref
        The PostGIS st_hausdorffdistance is not a real Hausdorffdistance
        (see http://postgis.refractions.net/docs/ST_HausdorffDistance.html),
        it's the maximum distance between the points of two features

        :param linematch_options: an object of the LinematchOptions Class is used to hold all necessary options for
         the linematching process, see the documentation on the LinematchOptions Class
        """

        #: Shorter parameters
        basetable = linematch_options.basetable
        table1 = linematch_options.reftable
        table2 = linematch_options.osmtable
        minmatchingfeatlen = str(linematch_options.minmatchingfeatlen)
        maxlengthdiffratio = str(linematch_options.maxlengthdiffratio)
        maxanglediff = str(linematch_options.maxanglediff)
        maxpmatches = str(linematch_options.maxpotentialmatches)
        searchradius = str(linematch_options.searchradius)
        pdiffseglen = str(linematch_options.posdiffsegmentlength)
        hausdorffseglen = str(linematch_options.hausdorffsegmentlength)
        maxazimuthdiff = str(linematch_options.maxazimuthdiff)
        maxmeanposdevtolength = str(linematch_options.maxmeanposdevtolength)
        minmeanposdevtolength = str(linematch_options.minmeanposdevtolength)
        maxabsolutmeanposdev = str(linematch_options.maxabsolutmeanposdev)
        keepcolumns_t1 = linematch_options.keepcolumns_t1
        keepcolumns_t2 = linematch_options.keepcolumns_t2

        #: Build strings for columns that should be included in linematch result table
        kc_str3 = ''
        for k in keepcolumns_t1:
            kc_str3 += ', t1.' + k
        for k in keepcolumns_t2:
            kc_str3 += ', t2.' + k

        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()

        #: Recreating tables if they already exist
        query = 'drop table if exists '+basetable+'_result;'
        cursor.execute(query)

        query = ('CREATE TABLE '+basetable+'_result (id bigserial PRIMARY KEY, fit double precision, '
                 'meandev double precision, old_id integer,sub_id integer, osmsource bigint, refsource bigint, '
                 'name varchar, matchname varchar);')
        cursor.execute(query)

        query = ('SELECT addGeometryColumn(\''+basetable+'_result\',\'geom\','
                 '(SELECT ST_SRID(geom) as srid FROM '+basetable+
                 '_ref WHERE geom IS NOT NULL LIMIT 1), (SELECT geometrytype(geom) '
                 'FROM '+table1+' limit 1), 2);')
        cursor.execute(query)

        #: Create list with n potential matching-partners of table2 for each feature of table1 using the fast definable
        #: parameters: searchradius, maxlengthdiffratio and maxanglediff
        yield 'Creating potential matching features table'
        query = ('create temp table potentialmatches on commit drop as '
                 'WITH subq AS ('
                 'SELECT t1.id as t1_id, '
                 'unnest(ARRAY(SELECT t2.id '
                 'FROM '+table2+' t2 '
                 'WHERE ST_DWithin(t1.geom, t2.geom,'+searchradius+') '
                 'and st_length(t1.geom)>'+minmatchingfeatlen+' or st_length(t2.geom)>'+minmatchingfeatlen+' '
                 'and greatest(st_length(t1.geom),st_length(t2.geom))/least(st_length(t1.geom), st_length(t2.geom)) < '
                 +maxlengthdiffratio+' and abs((abs((t1.direction - t2.direction))+'+maxanglediff+') % '+pi+' - '
                 +maxanglediff+')<'+maxanglediff+' ORDER BY t1.geom <-> t2.geom LIMIT '+maxpmatches+')) as t2_id '
                 'FROM '+table1+' t1) SELECT * FROM subq;')
        cursor.execute(query)

        #: Positional differences are distances from points along a line in a given interval to the closest points of
        #: another line. The calculation is asymmetrical, therefore the calculations are done in both ways and the
        #: mean value is then used as the mean positional difference.
        #: Calculate the positional differences between the features in potentialmatches for table1 features as source
        yield 'Calculating positional differences for reference lines'
        query = ('create temp table posdev_t1 on commit drop as '
                 '(SELECT n.t1_id, n.t2_id,(sum(ST_Distance(t1p.geom,t2.geom))/count(t1p.id)) as diff '
                 'FROM potentialmatches n, '
                 '(SELECT (st_dumppoints(st_segmentize(t1.geom,'+pdiffseglen+'))).geom, t1.id '
                 'FROM '+table1+' t1) t1p, '+table2+' t2 '
                 'WHERE n.t1_id = t1p.id and n.t2_id = t2.id GROUP BY n.t1_id, n.t2_id);')
        cursor.execute(query)

        #: Calculate the positional differences between the features in potentialmatches for table2 features as source
        yield 'Calculating positional differences for osm lines'
        query = ('create temp table posdev_t2 on commit drop  as '
                 '(SELECT n.t2_id, n.t1_id, (sum(ST_Distance(t2p.geom,t1.geom))/count(t2p.id)) as diff '
                 'FROM potentialmatches n, '
                 '(SELECT (st_dumppoints(st_segmentize(t2.geom,'+pdiffseglen+'))).geom, t2.id '
                 'FROM '+table2+' t2) t2p, '+table1+' t1 '
                 'WHERE n.t2_id = t2p.id and n.t1_id = t1.id '
                 'GROUP BY n.t2_id, n.t1_id);')
        cursor.execute(query)

        #: Calculate more expressive parameters between potential matches and insert them into table matchingparameters
        yield 'Calculating matching parameters'
        query = ('create temp table matchingparameters on commit drop as '
                 'SELECT n.t1_id, n.t2_id, 0.0 as fit, '
                 'st_hausdorffdistance(t1.geom, t2.geom,'+hausdorffseglen+') as hausdorff, '
                 'greatest(st_length(t1.geom),st_length(t2.geom))/least(st_length(t1.geom),st_length(t2.geom)) lengthdiff,'
                 ' st_length(t1.geom)+st_length(t2.geom)/2.0 as meanlength, '
                 'abs((abs(t1.direction - t2.direction)+'+maxazimuthdiff+') %'+pi+' - '+maxazimuthdiff+') directiondiff,'
                 ' ((pd_t1.diff+pd_t2.diff)/2.0) as meanposdev '
                 'FROM '+table2+' t2, '+table1+' t1, posdev_t1 pd_t1, posdev_t2 pd_t2, potentialmatches n '
                 'WHERE n.t1_id = t1.id and n.t2_id = t2.id and n.t1_id = pd_t1.t1_id and n.t2_id = pd_t2.t2_id '
                 'and n.t2_id = pd_t1.t2_id and n.t1_id = pd_t2.t1_id;')
        cursor.execute(query)

        # Posdiff with points at fixed distance on line. Deactivated because of bad results.
        # yield 'Calculating matching parameters'
        # query = 'create temp table matchingparameters on commit drop as
        # SELECT n.t1_id, n.t2_id, 0.0 as fit, st_hausdorffdistance(t1.geom, t2.geom,0.005) as hausdorff,
        # greatest(st_length(t1.geom),st_length(t2.geom))/least(st_length(t1.geom),st_length(t2.geom)) as lengthdiff,
        # abs((abs(t1.direction - t2.direction)+'+maxazimuthdiff+') % '+pi+' - '+maxazimuthdiff+') as directiondiff,
        # ((posdev_t1.diff+posdifft2.diff)/(st_length(t1.geom)+st_length(t2.geom)/2.0))/400.0 as meanposdev
        # FROM '+table2+' t2, '+table1+' t1, posdev_t1, posdev_t2, potentialmatches n
        # WHERE n.t1_id = t1.id and n.t2_id = t2.id and n.t1_id = posdev_t1.t1_id and n.t2_id = posdev_t1.t2_id
        # and n.t2_id = posdifft2.t2_id and n.t1_id = posdifft2.t1_id;'
        # cursor.execute(query)
        #
        #
        # query = 'create temp table posdiff on commit drop as
        # (SELECT n.t1_id, n.t2_id, sum(st_distance(ST_LineInterpolatePoint(t2.geom,serie.i),
        # ST_LineInterpolatePoint(t1.geom,serie.i))) / 30.0 as diff
        # FROM '+table2+' as t2,'+table1+' as t1, potentialmatches n,
        # (SELECT generate_series(1,30)::float/30 as i) as serie
        # WHERE n.t1_id = t1.id and n.t2_id = t2.id and st_distance(st_startpoint(t2.geom),
        # st_startpoint(t1.geom)) < st_distance(st_startpoint(t2.geom),st_endpoint(t1.geom))
        # GROUP BY n.t2_id, n.t1_id union all SELECT n.t1_id, n.t2_id,
        # sum(st_distance(ST_LineInterpolatePoint(t2.geom,serie.i),
        # ST_LineInterpolatePoint(t1.geom,1-serie.i))) / 30.0 as diff
        # FROM '+table2+' as t2,'+table1+' as t1, potentialmatches n,
        # (SELECT generate_series(1,30)::float/30 as i) as serie
        # WHERE n.t1_id = t1.id and n.t2_id = t2.id and st_distance(st_startpoint(t2.geom),
        # st_startpoint(t1.geom)) >= st_distance(st_startpoint(t2.geom),st_endpoint(t1.geom))
        # GROUP BY n.t2_id, n.t1_id)'
        # cursor.execute(query)
        #
        # yield 'Calculating matching parameters'
        # query = 'create temp table matchingparameters on commit drop as
        # SELECT n.t1_id, n.t2_id, 0.0 as fit, st_hausdorffdistance(t1.geom, t2.geom,0.005) as hausdorff,
        # greatest(st_length(t1.geom),st_length(t2.geom))/least(st_length(t1.geom),st_length(t2.geom)) as lengthdiff,
        # abs((abs(t1.direction - t2.direction)+'+maxazimuthdiff+') % '+pi+' - '+maxazimuthdiff+') as directiondiff,
        # posdiff.diff*1.5 as meanposdev FROM '+table2+' t2, '+table1+' r, posdiff, potentialmatches n
        # WHERE n.t1_id = t1.id and n.t2_id = t2.id and n.t1_id = posdiff.t1_id and n.t2_id = posdiff.t2_id;'
        # cursor.execute(query)

        #: The Levenshtein distance is only calculated for feature pairs, where the name attribute of each feature isn't
        #: empty.


        #: All potential matching pairs, whose maxlengthdiffratio is not within the given limits, are eliminated
        yield 'Deleting potential matches which are outside matching limits'
        query = ('DELETE FROM matchingparameters using '
                 '(SELECT matchingparameters.t1_id, matchingparameters.t2_id, matchingparameters.meanposdev '
                 'FROM matchingparameters '
                 'WHERE matchingparameters.lengthdiff>'+maxlengthdiffratio+') as DELETElist '
                 'WHERE DELETElist.t1_id = matchingparameters.t1_id and DELETElist.t2_id = matchingparameters.t2_id '
                 'and DELETElist.meanposdev = matchingparameters.meanposdev;')
        cursor.execute(query)

        #: All potential matching pairs, whose meanposdevtolengthratio, azimuthdiff and meanposdev are not within
        #: the given limits, are eliminated
        yield 'Deleting potential matches which are outside matching limits'
        query = ('DELETE FROM matchingparameters using '
                 '(SELECT matchingparameters.t1_id, matchingparameters.t2_id, matchingparameters.meanposdev '
                 'FROM matchingparameters '
                 'WHERE matchingparameters.meanposdev/matchingparameters.meanlength>'
                 +maxmeanposdevtolength+'+'+minmeanposdevtolength+' or matchingparameters.directiondiff>'
                 +maxazimuthdiff+' or matchingparameters.meanposdev>'
                 +maxabsolutmeanposdev+') as DELETElist '
                 'WHERE DELETElist.t1_id = matchingparameters.t1_id and DELETElist.t2_id = matchingparameters.t2_id '
                 'and DELETElist.meanposdev = matchingparameters.meanposdev;')
        cursor.execute(query)

        #: Calculation of the total deviation based on the sum of weighted parameters
        yield 'Calculating matching pair deviation using weighted and normalized (to the limits) matching parameters'
        query = ('UPDATE matchingparameters set fit = UPDATElist.fit '
                 'FROM (SELECT matchingparameters.t1_id, matchingparameters.t2_id, '
                 '((matchingparameters.lengthdiff*2+matchingparameters.directiondiff/'
                 +maxazimuthdiff+'+(matchingparameters.meanposdev/(matchingparameters.meanlength*'
                 +maxmeanposdevtolength+'))*4+matchingparameters.hausdorff*2)/9) as fit '
                 'FROM matchingparameters) as UPDATElist '
                 'WHERE UPDATElist.t1_id = matchingparameters.t1_id and UPDATElist.t2_id = matchingparameters.t2_id;')
        cursor.execute(query)

        #: Create a table of matching pairs with minimal deviation = best matches
        yield 'Finding matching pairs with minimal deviation'
        query = ('create temp table found on commit drop as '
                 'SELECT matchingparameters.t1_id, '
                 'matchingparameters.t2_id, '
                 'matchingparameters.meanposdev, '
                 'f.minfit '
                 'FROM matchingparameters, '
                 '(SELECT matchingparameters.t1_id, min(fit) as minfit FROM matchingparameters '
                 'GROUP BY matchingparameters.t1_id order BY matchingparameters.t1_id) as f '
                 'WHERE matchingparameters.t1_id = f.t1_id and matchingparameters.fit = f.minfit;')
        cursor.execute(query)

        query = 'drop table if exists '+basetable+'_found;'
        cursor.execute(query)

        #: Generate a table with the results of line matching and link segmented features with their parent feature-id
        yield 'Generating result table'
        query = ('create table '+basetable+'_found as '
                 'SELECT found.t1_id, found.t2_id, t2.old_id as osmid, '
                 't1.old_id as ref_id, t2.name as t2name, t1.name as t1name, '
                 'abs(st_length(geometry(t1.geom)::geography)-st_length(geometry(t2.geom)::geography)) '
                 'as lengthdiff, '
                 'fo.minfit/4 as deviation, found.meanposdev, null::smallint as levenshteindiff1, '
                 'null::smallint as levenshteindiff2, null::varchar as rel_name '+kc_str3+' '
                 'FROM found, '
                 '(SELECT found.t2_id, min(minfit) as minfit '
                 'FROM found  '
                 'GROUP BY found.t2_id order BY found.t2_id) as fo, '
                 +table2+' t2, '+table1+' t1 '
                 'WHERE found.t2_id = fo.t2_id '
                 'and fo.t2_id = t2.id '
                 'and found.t1_id = t1.id '
                 'and found.minfit = fo.minfit;')
        cursor.execute(query)


        #: Correct too small objects by connecting them to their parent object
        yield 'Correcting objects'
        query = ('UPDATE '+basetable+'_found '
                 'set rel_name = subq.rel_name '
                 'FROM '
                 '(SELECT t3.name as rel_name, t2.id as t2_id '
                 'FROM '+table2+' t2, '+basetable+'_osm_rel t3 '
                 'WHERE t3.name is not null and st_contains(t2.geom,t3.geom) and t3.route=\'road\') as subq '
                 'WHERE '+basetable+'_found.t2_id = subq.t2_id;')
        cursor.execute(query)

        #yield 'Calculating levenshtein distance for matches'
        #query = ('UPDATE '+basetable+'_found '
        #         'set levenshteindiff = subq.levenshteindiff '
        #         'FROM '
        #         '(SELECT levenshtein(f.t2name,f.t1name) as levenshteindiff, f.t2_id, f.t1_id '
        #         'FROM '+basetable+'_found f '
        #         'WHERE f.t2_id = t2_id and f.t1_id = t1_id and f.t2name is not null and f.t1name is not null) as subq '
        #         'WHERE '+basetable+'_found.t2_id = subq.t2_id and '+basetable+'_found.t1_id = subq.t1_id;')
        #cursor.execute(query)

        yield 'Calculating levenshtein distance for matches'
        query = ('UPDATE '+basetable+'_found '
                 'set rel_name = subq.rel_name '
                 'FROM '
                 '(SELECT t3.name as rel_name, t2.id as t2_id '
                 'FROM '+table2+' t2, '+basetable+'_osm_rel t3 '
                 'WHERE t3.name is not null and st_contains(t2.geom,t3.geom) and t3.route=\'road\') as subq '
                 'WHERE '+basetable+'_found.t2_id = subq.t2_id;')
        cursor.execute(query)

        yield 'Calculating levenshtein distance for matches'
        query = ('UPDATE '+basetable+'_found '
                 'set levenshteindiff1 = subq.levenshteindiff1 '
                 'FROM '
                 '(SELECT levenshtein(t2.name,t1.name) as levenshteindiff1, t2.id as t2_id, t1.id as t1_id '
                 'FROM '+table1+' t1, '+table2+' t2, '+basetable+'_found f '
                 'WHERE t2.id = f.t2_id and t1.id = f.t1_id and t2.name is not null and t1.name is not null) as subq '
                 'WHERE '+basetable+'_found.t2_id = subq.t2_id and '+basetable+'_found.t1_id = subq.t1_id;')
        cursor.execute(query)

        yield 'Calculating levenshtein distance for matches'
        query = ('UPDATE '+basetable+'_found '
                 'set levenshteindiff2 = subq.levenshteindiff2 '
                 'FROM '
                 '(SELECT levenshtein(f.rel_name, t1.name) as levenshteindiff2, f.t2_id as t2_id, t1.id as t1_id '
                 'FROM '+table1+' t1, '+basetable+'_found f '
                 'WHERE t1.id = t1_id and f.rel_name is not null and t1.name is not null) as subq '
                 'WHERE '+basetable+'_found.t2_id = subq.t2_id and '+basetable+'_found.t1_id = subq.t1_id;')
        cursor.execute(query)

        connection.commit()
        connection.close()

    def create_spatial_index(self, tablename):
        query = ('CREATE INDEX '+tablename+'_gix ON '+tablename+' USING GIST(geom);')
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        cursor.execute(query)
        connection.commit()
        connection.close()

    def create_results(self, result_options):
        """A Function to create useful results based on linematched Features and deviation lines.
        It contains a set of predefined queries to create the results.

        The grid generation method is based on the method shown by Alexander Palamarchuk on
        http://gis.stackexchange.com/questions/16374/how-to-create-a-regular-polygon-grid-in-postgis
        It uses a postgresql-method called makegrid_2d(), this method is shown in install_grid_method()
        """
        if result_options is None:
            yield 'Error: No Options definied!'
            return

        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()

        #: Shorter parameters for queries
        basetable = result_options.basetable
        table1 = result_options.reftable + splitted_suffix
        table2 = result_options.osmtable + splitted_suffix
        posdevlinedist = str(result_options.posdevlinedist)
        matchedt1minlen = str(result_options.matchedrefminlen)
        matchedt2minlen = str(result_options.matchedosmminlen)
        unmatchedt1minlen = str(result_options.unmatchedrefminlen)
        unmatchedt2minlen = str(result_options.unmatchedosmminlen)
        minlev = str(result_options.minlev)
        maxlev = str(result_options.maxlev)
        gridcellsize = str(result_options.gridcellsize)

        #: Drop result tables if they already exist
        yield 'Deleting existing results'
        query = 'drop table if exists '+basetable+'_posdevlines;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_matchedref;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_matchedosm;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_unmatchedref;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_unmatchedosm;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_minlevenshtein;'
        cursor.execute(query)
        query = 'drop table if exists '+basetable+'_maxlevenshtein;'
        cursor.execute(query)
        query = ('drop table if exists '+basetable+'_grid;')
        cursor.execute(query)
        query = ('drop table if exists '+basetable+'_maxdevgrid;')
        cursor.execute(query)
        query = ('drop table if exists '+basetable+'_matchingrategrid;')
        cursor.execute(query)
        query = ('drop table if exists '+basetable+'_absdevgrid;')
        cursor.execute(query)

        #: If chosen by user, create a table with lines representing positional differences
        if result_options.posdevlines and result_options.posdevlinedist is not None:
            yield 'Creating deviation vectors'
            query = ('create table '+basetable+'_posdevlines as '
                     'SELECT st_makeline(st_closestpoint(t2.geom,t1.geom), t1.geom) as geom, '
                     'st_length(st_transform(st_makeline(st_closestpoint(t2.geom, t1.geom), t1.geom),32633)) as fit '
                     'FROM (SELECT id, (st_dumppoints(st_segmentize(geom, '+posdevlinedist+'))).geom '
                     'FROM '+table1+') as t1, '+table2+' as t2, '+basetable+'_found f '
                     'WHERE f.t1_id = t1.id and f.t2_id = t2.id;')
            cursor.execute(query)

        #: If chosen by user, create table with matched features of table1
        if result_options.matchedref and result_options.matchedrefminlen is not None:
            yield 'Extracting matched Reference Lines'
            query = ('create table '+basetable+'_matchedt1 as '
                     '(select matches.*, t1.geom from '+table1+' t1, '+basetable+'_found matches '
                     'WHERE matches.t1_id = t1.id and st_length(t1.geom)>'+matchedt1minlen+');')
            cursor.execute(query)

        #: If chosen by user, create table with matched features of table2
        if result_options.matchedosm and result_options.matchedosmminlen is not None:
            yield 'Extracting matched OSM Lines'
            query = ('create table '+basetable+'_matchedt2 as '
                     '(select matches.*, t2.geom from '+table2+' t2, '+basetable+'_found matches '
                     'WHERE matches.t1_id = t2.id and st_length(t2.geom)>'+matchedt2minlen+');')
            cursor.execute(query)

        #: If chosen by user, create table with unmatched features of table1, whose lengths are > unmatchedt1minlen
        if result_options.unmatchedref and result_options.unmatchedrefminlen is not None:
            yield 'Extracting unmatched Reference Lines'
            query = ('create table '+basetable+'_unmatchedt1 as '
                     '(select matches.*, t1.geom from '+table1+' t1, '+basetable+'_found matches '
                     'WHERE matches.t1_id = t1.id and st_length(t1.geom)>'+unmatchedt1minlen+');')
            cursor.execute(query)

        #: If chosen by user, create table with unmatched features of table2, whose lengths are > unmatchedt2minlen
        if result_options.unmatchedosm and result_options.unmatchedosmminlen is not None:
            yield 'Extracting unmatched OSM Lines'
            query = ('create table '+basetable+'_unmatchedt2 as '
                     '(select matches.*, t2.geom from '+table2+' t2, '+basetable+'_found matches '
                     'WHERE matches.t1_id = t2.id and st_length(t2.geom)>'+unmatchedt2minlen+');')
            cursor.execute(query)

        #: If chosen by user, create table with matched features of table1, whose levenshteindiff < minlev
        if result_options.minlevenshtein and result_options.minlev is not None:
            yield 'Extracting Features with Levenshteindistance < '+ minlev
            query = ('create table '+basetable+'_minlevenshtein as '
                     '(select matches.*, t1.geom from ' + table1 + ' t1, ' + basetable + '_found matches '
                     'WHERE matches.t1_id = t1.id and matches.levenshteindiff<' + minlev +
                     ' and matches.t2name is not Null and matches.t1name is not Null);')
            cursor.execute(query)

        #: If chosen by user, create table with unmatched features of table1, whose levenshteindiff > maxlev
        if result_options.maxlevenshtein and result_options.maxlev is not None:
            yield 'Extracting Features with Levenshteindistance > '+ maxlev
            query = ('create table '+basetable+'_maxlevenshtein as '
                     '(select matches.*, t1.geom from ' + table1 + ' t1, ' + basetable + '_found matches '
                     'WHERE matches.t1_id = t1.id and matches.levenshteindiff>' + maxlev +
                     'and matches.t2name is not Null and matches.t1name is not Null);')
            cursor.execute(query)

        #: If chosen by user, create table containing a grid for the given area of interest
        if result_options.maxdevgrid or result_options.matchingrategrid or result_options.absdevgrid:
            yield 'Creating Grid'
            #: Create grid for the given area and cellsize
            query = ('create table '+basetable+'_grid as SELECT cell '
                     'FROM (SELECT (ST_Dump(makegrid_2d((SELECT ST_ConcaveHull(ST_Collect(geom),0.99) '
                     'FROM '+table1+'),'+gridcellsize+'))).geom AS cell) AS q_grid;')
            cursor.execute(query)

            # Create index for faster operations on grid
            query = ('CREATE INDEX '+basetable+'_grid_cell_idx ON '+basetable+'_grid USING GIST (cell);')
            cursor.execute(query)

        #: If chosen by user, create table containing a grid with maximum deviation per grid cell
        if result_options.maxdevgrid:
            yield 'Creating Maximum Deviation Grid'
            if not result_options.posdevlines:
                query = ('create temp table '+basetable+'_posdevlines on commit drop as '
                         'SELECT st_makeline(st_closestpoint(t2.geom,t1.geom), t1.geom) as geom, r.deviation as fit '
                         'FROM (SELECT id, (st_dumppoints(st_segmentize(geom, '+posdevlinedist+'))).geom '
                         'FROM '+table1+') as t1, '+table2+' as t2, '+basetable+'_found r '
                         'WHERE r.t1_id = t1.id and r.t2_id = t2.id;')
                cursor.execute(query)
            query = ('create table '+basetable+'_maxdevgrid as '
                     '(select max(st_length(geometry(t1s.geom)::geography)) as maxdev, '
                     'grid.cell as cell from '+basetable+'_grid grid, '+basetable+'_posdevlines t1s '
                     'where st_intersects(grid.cell, t1s.geom) group by grid.cell);')
            cursor.execute(query)

        #: If chosen by user, create table containing a grid with matching rate per grid cell
        if result_options.matchingrategrid:
            yield 'Creating Matchingrate Grid'
            query = ('create table '+basetable+'_matchingrategrid as '
                     '(with t1 as (select sum(st_length(st_intersection(grid.cell,t1.geom))) as t1length, '
                     'grid.cell as cell from '+basetable+'_grid grid, '+table1+' t1 '
                     'where st_intersects(grid.cell, t1.geom) group by grid.cell), '
                     'mt1 as (select sum(st_length(st_intersection(grid.cell,t1.geom))) as mt1length, '
                     'grid.cell as cell from '+basetable+'_grid grid, '+table1+' t1,  '+basetable+'_found as matched '
                     'where st_intersects(grid.cell, t1.geom) and t1.id = matched.t1_id group by grid.cell) '
                     'select (mt1.mt1length/t1.t1length) as matchingrate, t1.cell as cell from t1, mt1 '
                     'where st_equals(t1.cell,mt1.cell) and t1.t1length!=0 );')
            cursor.execute(query)

        #: If chosen by user, create table containing a grid with completeness per grid cell
        if result_options.absdevgrid:
            yield 'Creating Completeness Grid'
            query = ('create table '+basetable+'_absdevgrid as '
                     '(with t1 as (select sum(st_length(st_intersection(grid.cell,t1.geom))) as t1lengths, '
                     'grid.cell as cell from '+basetable+'_grid grid, '+table1+' t1 '
                     'where st_intersects(grid.cell, t1.geom) group by grid.cell), '
                     't2 as (select sum(st_length(st_intersection(grid.cell,t2.geom))) as t2lengths, '
                     'grid.cell as cell from '+basetable+'_grid grid, '+table2+' t2 '
                     'where st_intersects(grid.cell, t2.geom) group by grid.cell) '
                     'select (t1.t1lengths/t2.t2lengths) as lengthdiffratio, t1.cell as cell from t1, t2 '
                     'where st_equals(t1.cell,t2.cell));')
            cursor.execute(query)

        connection.commit()
        connection.close()

    def install_asmultipoint(self):
        """Function to install the postgresql-method named asmultipoint used by geometric correction"""
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        query = '''CREATE OR REPLACE FUNCTION public.st_asmultipoint(geometry)
  RETURNS geometry AS
'SELECT ST_Union((d).geom) FROM ST_DumpPoints($1) AS d;'
  LANGUAGE sql IMMUTABLE STRICT
  COST 10;
ALTER FUNCTION public.st_asmultipoint(geometry)
  OWNER TO martin;
'''
        cursor.execute(query)
        connection.commit()
        connection.close()


    def install_grid_method(self):
        """Function to install the postgresql-method named makegrid_2d for grid generation

        The grid generation method is based on the method shown by Alexander Palamarchuk on
        http://gis.stackexchange.com/questions/16374/how-to-create-a-regular-polygon-grid-in-postgis
        It uses a postgresql-method called makegrid_2d(), this method is shown in install_grid_method()
        """
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        query = '''CREATE OR REPLACE FUNCTION public.makegrid_2d (
              bound_polygon public.geometry, grid_step integer, metric_srid integer = 4326)
            RETURNS public.geometry AS
            $body$
            DECLARE
              BoundM public.geometry;
                Xmin DOUBLE PRECISION;
              Xmax DOUBLE PRECISION;
              Ymax DOUBLE PRECISION;
              X DOUBLE PRECISION;
              Y DOUBLE PRECISION;
              sectors public.geometry[];
              i INTEGER;
            BEGIN
              BoundM := ST_Transform($1, $3);
                Xmin := ST_XMin(BoundM);
              Xmax := ST_XMax(BoundM);
              Ymax := ST_YMax(BoundM);

              Y := ST_YMin(BoundM);
                i := -1;
              <<yloop>>
              LOOP
                IF (Y > Ymax) THEN
                        EXIT;
                END IF;

                X := Xmin;
                <<xloop>>
                LOOP
                  IF (X > Xmax) THEN
                      EXIT;
                  END IF;

                  i := i + 1;
                  sectors[i] := ST_GeomFromText('POLYGON(('||X||' '||Y||', '||(X+$2)||' '||Y||',
                   '||(X+$2)||' '||(Y+$2)||', '||X||' '||(Y+$2)||', '||X||' '||Y||'))', $3);

                  X := X + $2;
                END LOOP xloop;
                Y := Y + $2;
              END LOOP yloop;

              RETURN ST_Transform(ST_Collect(sectors), ST_SRID($1));
            END;
            $body$
            LANGUAGE 'plpgsql';'''
        cursor.execute(query)
        connection.commit()
        connection.close()

    def create_subset(self, table1, table2, outtable, distance=0.0001):
        """Function to extract a subset of features of table2 based on the features of table1 and a given bufferdistance
        """
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        #query = ('CREATE TABLE '+outtable+' as SELECT t2.* FROM '+table2+' t2, '+table1 +
        #         ' t1 WHERE ST_DWithin(t2.geom,t1.geom,'+str(distance)+') GROUP BY t2.geom, t2.id')
        query = ('update '+table1 +' set geom=sub.g from (with hull as (select st_concavehull(st_union(geom),1) '
                 'as geom from '+table2 +') select t1.id, st_intersection(hull.geom,t1.geom) as g from '+table1 +
                 ' t1, hull where not st_contains(hull.geom,t1.geom)) sub where '+table1 +'.id = sub.id')
        cursor.execute(query)
        query = 'CREATE INDEX '+outtable+'_gix ON '+outtable+' USING GIST(geom);'
        cursor.execute(query)
        connection.commit()
        connection.close()

    def get_concavehull(self, table):
        """Function to calculate the concavehull of the features of a table and returning it in the geojson format,
        used to generate the bounding-polygon for querying osm data
        """
        query = ('SELECT ST_AsGeoJSON(ST_FlipCoordinates(concavehull.geom),3)::JSON as flippedgeom,'
                 'ST_AsGeoJSON(concavehull.geom,3)::JSON as geom FROM '
                 '(SELECT ST_ConcaveHull(ST_Collect('+table+'.geom),0.90) as geom FROM '+table+') as concavehull;')
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        cursor.execute(query)
        concavehull = cursor.fetchone()
        connection.close()
        if DEBUG:
            print concavehull
        return concavehull

    def get_textcolumns(self, table, schema='public'):
        """Returns all columns of type character varying of chosen table and schema.
        """
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        query=("SELECT column_name FROM information_schema.columns WHERE table_schema = '"+schema+"' "
           "AND table_name   = '" + table + "' "
           "AND data_type = 'character varying';")
        cursor.execute(query)
        cols = cursor.fetchall()
        connection.close()
        return cols

    def create_nonamecolumn(self, table):
        """Creates an empty column of type character varying for the given table.
        Used if there is no column for streetnames in the chosen reference dataset.
        This empty table is used as a substitute containing no data, but will be used for the levenshtein distance
        """
        connection = psycopg2.connect(self.dbconnectioninfo_psycopg)
        cursor = connection.cursor()
        query = ("ALTER TABLE "+table+" ADD NoNameCol character varying;")
        cursor.execute(query)
        connection.close()
        return
    def __del__(self):
        pass


class ShapeDataError(Exception):
    pass
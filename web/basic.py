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

from web import db, login_manager
from models import User, DevMap
from flask import Blueprint, request, redirect, url_for, render_template, Response, make_response
from flask.ext.login import login_required, login_user, logout_user

#: Blueprint for basic functions and simple user management
basic = Blueprint('basic', __name__, template_folder='templates')

@basic.route('/')
def index():
    print 'Index viewed by: '+request.remote_addr
    return render_template('index.html')

@basic.route('/about', methods=['POST', 'GET'])
def about():
    return render_template('about.html')

@basic.route('/documentation', methods=['POST', 'GET'])
def documentation():
    return render_template('documentation.html')

@basic.route('/browse', methods=['POST', 'GET'])
def browse():
    return render_template('browse.html')

@basic.route('/<uid>', methods=['POST', 'GET'])
def deviationmap(uid):
    if uid is None:
        return render_template('index.html')
    uid = uid.encode('ISO-8859-1')
    devmap = DevMap.query.filter_by(uid=uid).first_or_404()
    return render_template('map.html', uid=uid, devmap=devmap)

@basic.route('/manage', methods=['GET', 'POST'])
@login_required
def manage():
    return render_template('manage.html')


@basic.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "POST" and "email" in request.form and "password" in request.form:
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first_or_404()
        remember = False
        if user is None:
            print 'User not found!'
            return Response('User not found')
        if "remember" in request.form:
            remember = True
        if user and user.check_password(password) and user:
            if login_user(user, remember=remember):
                return Response('test')
            else:
                print("Unable to log in user")
    return render_template("index.html")


@basic.route("/register", methods=["GET", "POST"])
def register():
    if request.method == 'POST' and 'email' in request.form:
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        remember = False
        if 'remember' in request.form:
            remember = True
        if User.query.filter_by(email=email).first() is not None:
            print 'Error: User already exists!'
            return Response('Error! User already exists!')
        user = User(username, email, password)
        try:
            db.session.add(user)
            db.session.commit()
            if login_user(user, remember):
                return redirect(url_for('basic.index'))
            else:
                print("Unable to log you in")
        except:
            print("Unable to register with the given email address")
    return render_template(url_for('basic.index'))


@basic.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('basic.index'))


@basic.route('/robots.txt', methods=['GET'])
def robotstxt():
    print 'Robots viewed by: ' + request.remote_addr
    robots = render_template('robots.txt')
    response = make_response(robots)
    response.headers['Content-Type'] = 'text/plain'
    return response


@login_manager.unauthorized_handler
def unauthorized_callback():
    return redirect(url_for('basic.index'))


@login_manager.user_loader
def load_user(id):
    if id is None:
        redirect('/login')
    user = User.query.filter_by(id=id).first_or_404()
    if user is not None:
        return user
    else:
        return None

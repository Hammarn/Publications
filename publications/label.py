"Label pages."

from __future__ import print_function

import logging

import tornado.web

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .saver import Saver


class LabelSaver(Saver):
    doctype = constants.LABEL

    def check_value(self, value):
        "Value must be unique."
        try:
            label = self.rqh.get_label(value)
            if label['_id'] == self.doc.get('_id'): return
        except KeyError:
            pass
        else:
            raise ValueError("label '%s' is not unique" % value)


class Label(RequestHandler):
    "Label page."

    def get(self, value):
        try:
            label = self.get_label(value)
        except KeyError, msg:
            self.see_other('home', error=str(msg))
            return
        publications = self.get_docs('publication/label', key=label['value'])
        publications.sort(key=lambda i: i['published'], reverse=True)
        self.render('label.html',
                    label=label,
                    publications=publications)


class Labels(RequestHandler):
    "Labels list page."

    def get(self):
        self.render('labels.html', labels=self.get_labels())


class LabelAdd(RequestHandler):
    "Label addition page."

    @tornado.web.authenticated
    def get(self):
        self.check_admin()
        self.render('label_add.html')

    @tornado.web.authenticated
    def post(self):
        self.check_admin()
        try:
            value = self.get_argument('value')
        except tornado.web.MissingArgumentError:
            self.see_other('label_add', error='No label provided.')
            return
        try:
            with LabelSaver(rqh=self) as saver:
                saver['value'] = value
                saver['value_normalized'] = utils.to_ascii(value)
                saver['accounts'] = []
            label = saver.doc
        except ValueError, msg:
            self.see_other('label_add', error=str(msg))
            return
        self.see_other('label', label['value'])


class LabelEdit(RequestHandler):
    "Label edit page."

    @tornado.web.authenticated
    def get(self, identifier):
        self.check_admin()
        try:
            label = self.get_label(identifier)
        except KeyError, msg:
            self.see_other('labels', error=str(msg))
            return
        self.render('label_edit.html', label=label)

    @tornado.web.authenticated
    def post(self, identifier):
        self.check_admin()
        try:
            label = self.get_label(identifier)
        except KeyError, msg:
            self.see_other('labels', error=str(msg))
            return
        old_value = label['value']
        with LabelSaver(label, rqh=self) as saver:
            saver['value'] = self.get_argument('value')
        # XXX Change all publications with this label
        self.see_other('label', label['email'])


class LabelDelete(RequestHandler):
    "Label Delete page."

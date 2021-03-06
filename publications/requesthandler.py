"RequestHandler subclass."

from __future__ import print_function

import base64
import json
import logging
import urllib
from collections import OrderedDict as OD

import couchdb
import tornado.web

from . import constants
from . import settings
from . import utils


class RequestHandler(tornado.web.RequestHandler):
    "Base request handler."

    def prepare(self):
        "Get the database connection."
        self.db = utils.get_db()

    def get_template_namespace(self):
        "Set the variables accessible within the template."
        result = super(RequestHandler, self).get_template_namespace()
        result['constants'] = constants
        result['settings'] = settings
        result['utils'] = utils
        result['is_admin'] = self.is_admin()
        result['is_curator'] = self.is_curator()
        result['error'] = self.get_cookie('error', '').replace('_', ' ')
        self.clear_cookie('error')
        result['message'] = self.get_cookie('message', '').replace('_', ' ')
        self.clear_cookie('message')
        result['year_counts'] = [(r.key, r.value) for r in 
                                 self.db.view('publication/year',
                                              descending=True,
                                              group_level=1)]
        return result

    def see_other(self, name, *args, **kwargs):
        """Redirect to the absolute URL given by name
        using HTTP status 303 See Other."""
        query = kwargs.copy()
        try:
            self.set_error_flash(query.pop('error'))
        except KeyError:
            pass
        try:
            self.set_message_flash(query.pop('message'))
        except KeyError:
            pass
        url = self.absolute_reverse_url(name, *args, **query)
        self.redirect(url, status=303)

    def absolute_reverse_url(self, name, *args, **query):
        "Get the absolute URL given the handler name, arguments and query."
        if name is None:
            path = ''
        else:
            path = self.reverse_url(name, *args, **query)
        return settings['BASE_URL'].rstrip('/') + path

    def reverse_url(self, name, *args, **query):
        "Allow adding query arguments to the URL."
        url = super(RequestHandler, self).reverse_url(name, *args)
        url = url.rstrip('?')   # tornado bug? sometimes left-over '?'
        if query:
            query = dict([(k, utils.to_utf8(v)) for k,v in query.items()])
            url += '?' + urllib.urlencode(query)
        return url

    def set_message_flash(self, message):
        "Set message flash cookie."
        self.set_flash('message', message)

    def set_error_flash(self, message):
        "Set error flash cookie message."
        self.set_flash('error', message)

    def set_flash(self, name, message):
        message = message.replace(' ', '_')
        message = message.replace(';', '_')
        message = message.replace(',', '_')
        self.set_cookie(name, message)

    def get_doc(self, key, viewname=None):
        """Get the document with the given id, or from the given view.
        Raise KeyError if not found.
        """
        return utils.get_doc(self.db, key, viewname=viewname)

    def get_docs(self, viewname, key=None, last=None, **kwargs):
        """Get the list of documents using the named view
        and the given key or interval.
        """
        return utils.get_docs(self.db, viewname, key=key, last=last, **kwargs)

    def get_publication(self, identifier, unverified=False):
        """Get the publication given its IUID, DOI or PMID.
        Search among unverified if that flag is set to True.
        Raise KeyError if no such publication.
        """
        return utils.get_publication(self.db, identifier, unverified=unverified)

    def get_label(self, identifier):
        """Get the label document by its IUID or value.
        Raise KeyError if no such publication.
        """
        return utils.get_label(self.db, identifier)

    def get_blacklisted(self, identifier):
        """Get the blacklist document id if the publication with
        the external identifier has been blacklisted.
        """
        return utils.get_blacklisted(self.db, identifier)

    def get_account(self, email):
        """Get the account identified by the email address.
        Raise KeyError if no such account.
        """
        return utils.get_account(self.db, email)

    def get_current_user(self):
        """Get the currently logged-in user account, if any.
        This overrides a tornado function, otherwise it should have
        been called 'get_current_account', since terminology 'account'
        is used in this code rather than 'user'."""
        try:
            account = self.get_current_user_session()
            if not account:
                account = self.get_current_user_basic()
            return account
        except KeyError:
            return None

    def get_current_user_session(self):
        """Get the current user from a secure login session cookie.
        Return None if no attempt at authentication.
        Raise KeyError if invalid authentication."""
        email = self.get_secure_cookie(
            constants.USER_COOKIE,
            max_age_days=settings['LOGIN_MAX_AGE_DAYS'])
        if not email: return None
        account = self.get_account(email)
        # Check if login session is invalidated.
        if account.get('login') is None:
            self.set_secure_cookie(constants.USER_COOKIE, '')
            raise KeyError
        # Check if disabled
        if account.get('disabled'):
            self.set_secure_cookie(constants.USER_COOKIE, '')
            raise KeyError
        return account

    def get_current_user_basic(self):
        """Get the current user by HTTP Basic authentication.
        This should be used only if the site is using TLS (SSL, https).
        Return None if no attempt at authentication.
        Raise KeyError if incorrect authentication."""
        try:
            auth = self.request.headers['Authorization']
        except KeyError:
            return None
        try:
            auth = auth.split()
            if auth[0].lower() != 'basic': raise ValueError
            auth = base64.b64decode(auth[1])
            email, password = auth.split(':', 1)
            account = self.get_account(email)
            if utils.hashed_password(password) != account.get('password'):
                raise ValueError
        except (IndexError, ValueError, TypeError):
            raise KeyError
        # Check if disabled
        if account.get('disabled'):
            self.set_secure_cookie(constants.USER_COOKIE, '')
            raise KeyError
        return account

    def get_logs(self, iuid):
        "Get the log entries for the document with the given IUID."
        return self.get_docs('log/doc',
                             key=[iuid, constants.CEILING],
                             last=[iuid, ''],
                             descending=True)

    def is_admin(self):
        "Does the current user have the 'admin' role?"
        return bool(self.current_user) and \
               self.current_user['role'] == constants.ADMIN

    def check_admin(self):
        "Check that the current user has the 'admin' role."
        if self.is_admin(): return
        raise tornado.web.HTTPError(403, reason="Role 'admin' required.")

    def is_curator(self):
        "Does the current user have the 'curator' or 'admin' role?"
        return bool(self.current_user) and \
               self.current_user['role'] in (constants.CURATOR, constants.ADMIN)
        
    def check_curator(self):
        "Check that the current user has the 'curator' or 'admin' role."
        if self.is_curator(): return
        raise tornado.web.HTTPError(403, reason="Role 'curator' required.")

    def is_owner(self, doc):
        """Is the current user the owner of the document?
        Role 'admin' is also allowed."""
        return bool(self.current_user) and \
               (self.current_user['email'] == doc['owner'] or
                self.is_admin())

    def check_owner(self, doc):
        "Check that the current user is the owner of the document."
        if self.is_owner(doc): return
        raise tornado.web.HTTPError(403, reason="You are not the owner.")

    def delete_entity(self, doc):
        "Delete the entity and its log entries."
        assert constants.DOCTYPE in doc, 'doctype must be defined'
        assert doc[constants.DOCTYPE] in constants.ENTITIES, 'must be an entity'
        for log in self.get_logs(doc['_id']):
            self.db.delete(log)
        self.db.delete(doc)

    def get_publication_json(self, publication, full=False):
        "Format publication for JSON."
        URL = self.absolute_reverse_url
        result = OD()
        result['entity'] = 'publication'
        result['iuid'] = publication['_id']
        result['title'] = publication['title']
        if full:
            result['timestamp'] = utils.timestamp()
        result['authors'] = []
        for author in publication['authors']:
            au = OD()
            au['family'] = author.get('family')
            au['given'] = author.get('given')
            au['initials'] = author.get('initials')
            result['authors'].append(au)
        for key in ['type', 'published', 'journal', 'abstract',
                    'doi', 'pmid', 'labels', 'xrefs', 'verified']:
            result[key] = publication.get(key)
        result['links'] = OD([
            ('self', { 'href': URL('publication_json', publication['_id'])}),
            ('display', {'href': URL('publication', publication['_id'])})])
        if full:
            result['created'] = publication['created']
            result['modified'] = publication['modified']
        return result

    def get_account_json(self, account, full=False):
        "Format account for JSON."
        URL = self.absolute_reverse_url
        result = OD()
        result['entity'] = 'account'
        result['iuid'] = account['_id']
        result['email'] = account['email']
        result['role'] = account['role']
        result['status'] = account.get('disabled') and 'disabled' or 'enabled'
        result['login'] = account.get('login')
        if full:
            result['timestamp'] = utils.timestamp()
            result['labels'] = labels = []
            for label in account['labels']:
                links = OD()
                links['self'] = {'href': URL('label_json', label)}
                links['display'] = {'href': URL('label', label)}
                labels.append(OD([('value', label),
                                  ('links', links)]))
        result['links'] = OD([
            ('self', { 'href': URL('account_json', account['email'])}),
            ('display', {'href': URL('account', account['email'])})])
        if full:
            result['created'] = account['created']
            result['modified'] = account['modified']
        return result

    def get_label_json(self, label, 
                       full=False, publications=None, accounts=None):
        "Format label for JSON."
        URL = self.absolute_reverse_url
        result = OD()
        result['entity'] = 'label'
        result['iuid'] = label['_id']
        result['value'] = label['value']
        if full:
            result['timestamp'] = utils.timestamp()
        result['links'] = links = OD()
        links['self'] = {'href': URL('label_json', label['value'])}
        links['display'] = {'href': URL('label', label['value'])}
        if full:
            result['created'] = label['created']
            result['modified'] = label['modified']
        if accounts is not None:
            result['accounts'] = [self.get_account_json(account)
                                  for account in accounts]
        if publications is None:
            try:
                result['publications_count'] = label['count']
            except KeyError:
                pass
        else:
            result['publications_count'] = len(publications)
            result['publications'] = [self.get_publication_json(publication)
                                      for publication in publications]
        return result

"Get the epublished date for all publications."

from __future__ import print_function

import time

from publications import constants
from publications import settings
from publications import utils
from publications import pubmed
from publications import crossref
from publications.publication import PublicationSaver

DELAY = 4.0

def get_args():
    parser = utils.get_command_line_parser(
        "Get the epublished date for all publications.")
    return parser.parse_args()

def get_epublished_pubmed(db):
    "Get the epublished date for all publications from PubMed."
    for row in db.view('publication/modified', include_docs=True):
        doc = row.doc
        epublished = doc.get('epublished')
        if epublished is not None and epublished <= doc['published']: continue
        if not doc['pmid']: continue
        time.sleep(DELAY)
        with PublicationSaver(doc=doc, db=db) as saver:
            published = doc['published']
            data = pubmed.fetch(doc['pmid'])
            saver['published'] = data['published']
            saver['epublished'] = data['epublished']
            print (published != doc['published'] and 'diff' or 'same',
                   doc['published'], doc['epublished'])

def get_epublished_crossref(db):
    "Get the epublished date for all publications from CrossRef."
    for row in db.view('publication/modified', include_docs=True):
        doc = row.doc
        if doc.get('epublished'): continue
        if not doc['doi']: continue
        time.sleep(DELAY)
        with PublicationSaver(doc=doc, db=db) as saver:
            published = doc['published']
            data = crossref.fetch(doc['doi'])
            saver['published'] = data['published']
            saver['epublished'] = data['epublished']
            print (published != doc['published'] and 'diff' or 'same',
                   doc['published'], doc['epublished'])

if __name__ == '__main__':
    args = get_args()
    utils.load_settings(filepath=args.settings)
    db = utils.get_db()
    get_epublished_pubmed(db)
    get_epublished_crossref(db)

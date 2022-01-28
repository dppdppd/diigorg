# -*- coding: utf-8 -*-

# Get your diigo application key here: https://www.diigo.com/api_keys/new/

import sys
import logging
import requests
from requests.auth import HTTPBasicAuth
from dateutil import parser
import argparse
import itertools
import orgparse
from orgparse import load, loads
import os
from datetime import datetime, timezone
import django
from django.template.defaultfilters import slugify
import time
import fileinput

logging.basicConfig(filename='diigorg.log', encoding='utf-8', level=logging.DEBUG, filemode='w')

spinner = itertools.cycle(['-', '\\', '|', '/'])

argParser = argparse.ArgumentParser(description = 'Sync Diigo bookmarks to Org files')
argParser.add_argument('key', type=str, help='Your Diigo application key')
argParser.add_argument('username', type=str, help='Your Diigo username')
argParser.add_argument('pw', type=str, help='Your Diigo password')
argParser.add_argument('-fd','--force-download', nargs='?', const=True, help='Force downloading of bookmarks. This will overwrite anything local.')

args = argParser.parse_args()

print(args)

# debugging variables
limit = 10
count = 10

bookmarks_file = "diigo-bookmarks.org"
id_format = '%y%m%d%H%M%S'
org_timestamp_format = '[%Y-%m-%d %a %H:%M:%S]'
filename_delimiter = ' - '
work_dir = "."

class DiigoBookmark:
  # {
  #*   "title":"Diigo API Help",
  #*   "url":"http://www.diigo.com/help/api.html",
  #   "user":"foo",
  #*   "desc":"",
  #*   "tags":"test,diigo,help",
  #*   "shared":"yes",
  #   "readlater":"yes",
  #   "created_at":"2008/04/30 06:28:54 +0800",
  #   "updated_at":"2008/04/30 06:28:54 +0800",
  #   "comments":[],
  #   "annotations":[]
  # },
    def __init__(self, downloaded_bookmark):
        self.bookmark = downloaded_bookmark
        self.modified_timestamp = self._get_modified_timestamp()
        self.created_timestamp = self._get_created_timestamp()
        self.id = self._get_id()
        self.file = self._create_filename()
        self._convert_tag_string_to_tag_set()
        self.has_changed = self.modified_timestamp > last_sync_time
        self.logging_title = self.bookmark["url"][:50].ljust(50)
        logging.info('Receiving'.ljust(15) + f'{self.logging_title}  {"HAS CHANGED" if self.has_changed else ""}')
        logging.debug(self.bookmark)

    def _convert_tag_string_to_tag_set(self):
        self.bookmark['tags'] = set(self.bookmark['tags'].split(',')) if self.bookmark['tags'] not in ['no_tag',''] else set()

    def _get_created_timestamp(self):
        return int(parser.parse(self.bookmark['created_at']).timestamp())

    def _get_modified_timestamp(self):
        return int(parser.parse(self.bookmark['updated_at']).timestamp())

    def _get_id(self):
        return datetime.fromtimestamp(self.created_timestamp).strftime(id_format)

    def _create_slug(self):
        return slugify(self.bookmark['title']).replace("-", " ")[:80]

    def _create_filename(self):
        return self.id + filename_delimiter + self._create_slug() + ".org"

    def _get_org_created_timestamp(self):
        return datetime.fromtimestamp(self.created_timestamp).strftime(org_timestamp_format)

    def _get_org_modified_timestamp(self):
        return datetime.fromtimestamp(self.modified_timestamp).strftime(org_timestamp_format)

    def _get_org_readlater(self):
        return 'TODO ' if self.bookmark['readlater'] == 'yes' else ''

    def _tags_as_string(self):
        return ':'.join(self.bookmark['tags'])

    def _tags_as_org_string(self):
        if not self._has_tags():
            return ''
        else:
            return '\t:' + self._tags_as_string() + ':'

    def write_bookmark_file(self):
        ""
        with open(os.path.join(work_dir, self.file), "w") as f:
            f.write(f'* {self._get_org_readlater()}[[{self.bookmark["url"]}][{self.bookmark["title"]}]]{self._tags_as_org_string()}')

            # PROPERTY DRAWER
            f.write('\n')
            f.write(':PROPERTIES:\n')
            f.write(f':CREATED: {self._get_org_created_timestamp()}\n')
            f.write(f':UPDATED: {self._get_org_modified_timestamp()}\n')
            f.write(f':SHARED: {self.bookmark["shared"]}\n')
            f.write(":END:\n")

            f.write(f'{self.bookmark["desc"]}\n')

    def _has_tags(self):
        return self.bookmark['tags'] != 'no_tags'

    def update_bookmark_file(self):
        ""
        root = orgparse.load(self.file)
        start_lineno = root.children[0].linenumber
        end_lineno = 7 if len(root.children) == 1 else root.children[1].linenumber
        file_object = open(self.file, 'r')
        new_file_buffer = ''
        lineno = 0
        for line in file_object:
            if lineno == start_lineno:
                new_file_buffer += f'* {self._get_org_readlater()}[[{self.bookmark["url"]}][{self.bookmark["title"]}]]{self._tags_as_org_string()}\n'
                new_file_buffer += f':PROPERTIES:\n'
                new_file_buffer += f':CREATED: {self._get_org_created_timestamp()}\n'
                new_file_buffer += f':UPDATED: {self._get_org_modified_timestamp()}\n'
                new_file_buffer += f':SHARED: {self.bookmark["shared"]}\n'
                new_file_buffer += f':END:\n'
                new_file_buffer += f'{self.bookmark["desc"]}\n'
            elif lineno >= end_lineno:
                new_file_buffer += line
            lineno += 1

        file_object.close()

        file_object = open(self.file, 'w')
        file_object.write(new_file_buffer)
        file_object.close()

    def delete(self):
        print('delete remote bookmark ', self.bookmark['title'])

class OrgBookmark:
    def __init__(self, file):
        self.file = file
        self.modified_timestamp = self._get_file_modtime()
        self.id = self._get_id_from_filename()
        self.bookmark = {}
        self.has_changed = self.modified_timestamp > last_sync_time
        self.logging_title = f'{self.file[:50]}'.ljust(50)
        logging.info('Parsing'.ljust(15) + f'{self.logging_title}  {"HAS CHANGED" if self.has_changed else ""}')

    def _get_id_from_filename(self):
        basename = os.path.basename(self.file)
        return basename[0:basename.find(filename_delimiter)]

    def _get_file_modtime(self):
        return os.path.getmtime(self.file)

    def get_node_title(self,node):
        h=node.get_heading(format='raw')
        title = h[h.rfind("][")+2:h.rfind("]")-1]
        return title

    def get_node_url(self,node):
        h=node.get_heading(format='raw')
        url = h[h.find("[")+2:h.find("]")]
        return url

    def get_node_tags(self,node):
        return node.shallow_tags

    def get_node_desc(self,node):
        return node.body

    def get_node_id(self,node):
        return node.get_property('ID')

    def get_node_shared(self,node):
        return node.get_property('SHARED')

    def get_node_readlater(self,node):
        return 'yes' if node.todo != None else 'no'

    def is_identical_to_match(self):
        return are_bookmarks_identical(self, self.match)

    def parse_and_fill_out(self):
        root = orgparse.load(self.file)
        for node in root.children:
            self.bookmark['title'] = self.get_node_title(node)
            self.bookmark['url'] = self.get_node_url(node)
            self.bookmark['tags'] = (self.get_node_tags(node))
            self.bookmark['desc'] = self.get_node_desc(node)
            self.bookmark['node_id'] = self.get_node_id(node)
            self.bookmark['shared'] = self.get_node_shared(node)
            self.bookmark['readlater'] = self.get_node_readlater(node)

    def fix_tags_for_upload(self):
        self.bookmark['tags'] = (',').join(self.bookmark['tags'])

    def send(self, reason=''):
        self.parse_and_fill_out()
        self.fix_tags_for_upload()
        print( 'sending ', self.bookmark['title'], reason )
        url = f'https://secure.diigo.com/api/v2/bookmarks?key={args.key}&user={args.username}&merge=no'
        response = requests.post(url, auth=HTTPBasicAuth(args.username, args.pw), json=self.bookmark)
        response.close()
        return response.json()

    def delete(self):
        print( 'deleting ', self.bookmark['title'] )

def find_bookmark_by_id(bm_list, id):
    res = [item for item in bm_list if item.id == id]
    return res[0] if len(res) > 0 else None

def are_bookmarks_identical(bm1, bm2):
    if type(bm1) == OrgBookmark:
        bm1.parse_and_fill_out()

    if type(bm2) == OrgBookmark:
        bm2.parse_and_fill_out()

    same = True

    for item in ['title', 'url', 'tags', 'desc', 'shared', 'readlater']:
        if bm1.bookmark[item] != bm2.bookmark[item]:
            same = False
            print(bm1.id, item, type(bm1), bm1.bookmark[item])
            print(bm2.id, item, type(bm2), bm2.bookmark[item])
            print('\n')
            break

    return same

def fetch_tranche(start, count):
    if limit >= 0 and start >= limit:
        return ''

    if count == -1 or count > 100:
        count = 100

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={args.key}&user={args.username}&filter=all&count={count}&start={start}'
    response = requests.get(url, auth=HTTPBasicAuth(args.username, args.pw))

    # spinner
    sys.stdout.write(next(spinner))   # write the next character
    sys.stdout.flush()                # flush stdout buffer (actual character display)
    sys.stdout.write('\b')            # erase the last written char

    response.close()
    return response.json()

def fetch_diigo_bookmarks(target_list):

    start = 0
    while bookmarks_tranche := fetch_tranche(start=start, count=count):
        if bookmarks_tranche:
            for b in bookmarks_tranche:
                entry = DiigoBookmark(b)
                remote_bookmark_list.append(entry)
            start += 100

#mark_test = list_of_remote_raw_bookmarks[-1]
# b print(aookmark_test['tags'] = 'deft,emacs'
# bookmark_test['desc']='This is a new description. NEW'
# print(bookmark_test)
# send_bookmark(bookmark_test)
#--------------------------------------------------------------------------------------------------------
#
sys.stdout.write("Fetching bookmarks...\n")

last_sync_time = 0;
try:
    with open('.diigorg.sync', 'r') as f:
        last_sync_time = int(f.readline())
        print( last_sync_time )
        print( 'last sync was ', time.strftime(org_timestamp_format, time.localtime(last_sync_time)) )
except IOError:
    print("first sync. stomping local data")

# if there is no synctime
#   print I don't see a synctime in this directory. the only option is to download everthing.
#   continue?
# else if PUSH
#   diigorg will upload all local bookmarks and overwrite the ones on diigo.
#   continue?
# else if PULL
#   diigorg will download all diigo bookmarks and overwrite all local ones.
#   continue?
#

# fetch all diigo bookmarks
remote_bookmark_list = []
fetch_diigo_bookmarks(remote_bookmark_list)

if args.force_download:
    print( 'OVERWRITING LOCAL FILES' )
    for bm in remote_bookmark_list:
        bm.write_bookmark_file()
    exit()

# iterate local bookmarks
local_bookmark_list = []
for file in os.listdir("."):
    if not file.endswith('.org'):
        logging.debug(f'Skipping local file -- {file}')
        continue

    local_bookmark_list.append(lbm := OrgBookmark(file))

# we don't need to iterate twice but this keeps the logs pretty
for lbm in local_bookmark_list:

    lbm.match = find_bookmark_by_id(remote_bookmark_list, lbm.id)
    lbm.is_matched = lbm.match != None

    action=''
    if not lbm.has_changed and lbm.is_matched:
        logging.info('Local'.ljust(15) + f'{lbm.logging_title}- No local change')
        continue
    elif not lbm.has_changed and not lbm.is_matched:
        logging.info('Local'.ljust(15) + f'{lbm.logging_title}- is old and does not exist on server. Mark to delete.')
        action = 'delete'
    elif lbm.has_changed and not lbm.is_matched:
        logging.info('Local'.ljust(15) + f'{lbm.logging_title}- is a new bookmark. Mark to upload.')
        action = 'send new'
    else: # has changed and is matched
        if (match_is_old := lbm.match.modified_timestamp <= last_sync_time):
            logging.info('Local'.ljust(15) + f'{lbm.logging_title}- has changed and remote bookmark has not changed. Mark to upload.')
            action = 'send update'
        else: # remote bookmark has also changed
            if (real_conflict := not lbm.is_identical_to_match()):
                logging.info('Local'.ljust(15) + f'{lbm.logging_title}- has changed and remote bookmark has also changed. Mark to resolve.')
                action = 'resolve'
            else:
                logging.info('Local'.ljust(15) + f'{lbm.logging_title}- has been touched but is identical to remote bookmark. Mark to update remote timestamp.')
                action = 'send timestamp'

    result = ''
    match action:
        case 'resolve':
            print(lbm.id,lbm.bookmark['title'],"both local and remote bookmarks have changed")
        case 'send new':
            result = lbm.send(action)
        case 'send update':
            result = lbm.send(action)
        case 'send timestamp':
            result = lbm.send(action)
        case 'delete':
            result = lbm.delete()

    print(result)

for rbm in remote_bookmark_list:

    rbm.match = find_bookmark_by_id(local_bookmark_list, rbm.id)
    rbm.is_matched = rbm.match != None

    # old bookmark. Move on.
    if not rbm.has_changed and rbm.is_matched:
        logging.info('Remote'.ljust(15) + f'{rbm.logging_title}- no remote change')
        continue

    action = ''
    if rbm.has_changed and not rbm.is_matched:
        logging.info('Remote'.ljust(15) + f'{rbm.logging_title}- is a new bookmark. Mark for writing to file.')
        action = 'write new'
    elif rbm.has_changed: # and is matched
        logging.info('Remote'.ljust(15) + f'{rbm.logging_title}- has changed. Mark for updating {rbm.match.logging_title}.')
        action = 'write update'
    elif not rbm.has_changed and not rbm.is_matched:
        logging.info('Remote'.ljust(15) + f'{rbm.logging_title}- is old and has been deleted locally. Mark for deletion.')
        action = 'delete'

    result = ''
    match action:
        case 'write new':
            result = rbm.write_bookmark_file()
        case 'write update':
            result = rbm.update_bookmark_file()
        case 'delete':
            result = rbm.delete()

    print(result)

with open('.diigorg.sync', 'w') as f:
    f.write(str(int(time.time())))


sys.stdout.write("done!\n")


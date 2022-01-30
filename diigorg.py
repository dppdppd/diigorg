# -*- coding: utf-8 -*-

# Get your diigo application key here: https://www.diigo.com/api_keys/new/

import os
import sys
import logging
import requests
from requests.auth import HTTPBasicAuth
from dateutil import parser
import argparse
import itertools
import orgparse
from datetime import datetime
from django.template.defaultfilters import slugify
import time
import shortuuid

logging.basicConfig(filename='diigorg.log', encoding='utf-8', level=logging.INFO, filemode='w')

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"{path} is not a valid path")

argParser = argparse.ArgumentParser(description = 'Sync Diigo bookmarks to Org files')
argParser.add_argument('key', type=str, help='Your Diigo application key')
argParser.add_argument('username', type=str, help='Your Diigo username')
argParser.add_argument('pw', type=str, help='Your Diigo password')
argParser.add_argument('-a', '--all', nargs='?', const=True,  help='Sync all bookmarks. Otherwise only bookmarks changed since last sync will be sunc')
argParser.add_argument('-d', '--dir', type=dir_path, default=os.getcwd(), help='Directory to sync')
argParser.add_argument('--force-download', nargs='?', const=True, help='for debugging only. do not use')
argParser.add_argument('--test', nargs='?', const=True, help='for debugging only. do not use.')
argParser.add_argument('--dry-run', nargs='?', const=True,  help='for debugging only. do not use.')

args = argParser.parse_args()

ORG_TIMESTAMP_FORMAT = '[%Y-%m-%d %a %H:%M:%S]'
FILENAME_DELIMITER = ' - '

todo_readlater = ['NEXT']

num_dl = 0
num_ul = 0
num_del = 0

spinner = itertools.cycle(['-', '\\', '|', '/'])
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
class DiigoBookmark:
    def __init__(self, downloaded_bookmark):
        self.bookmark = downloaded_bookmark
        self.modified_timestamp = self._get_modified_timestamp()
        self.has_changed = self.modified_timestamp > last_sync_time
        self.created_timestamp = self._get_created_timestamp()
        self.is_new = self.created_timestamp > last_sync_time
        self.id = self._get_id()
        self.file = self._find_or_create_filename()
        self._convert_tag_string_to_tag_set()
        # print( self.get_field('title'),org_timestamp(self.modified_timestamp), time.strftime(ORG_TIMESTAMP_FORMAT, time.localtime(last_sync_time)))
        # print(self.get_field('title'),self.has_changed, self.modified_timestamp, last_sync_time)
        self.logging_title = self.id + ' ' + self.bookmark["url"][6:56]
        self.incomplete = False
        logline('Receiving', self.logging_title, org_timestamp(self.modified_timestamp), 'NEW' if self.is_new else '')
        logging.debug(self.bookmark)

    def get_field(self, field):
        return self.bookmark[field]

    def _convert_tag_string_to_tag_set(self):
        self.bookmark['tags'] = set(self.bookmark['tags'].split(',')) if self.bookmark['tags'] not in ['no_tag',''] else set()

    def _get_created_timestamp(self):
        return int(parser.parse(self.bookmark['created_at']).timestamp())

    def _get_modified_timestamp(self):
        return int(parser.parse(self.bookmark['updated_at']).timestamp())

    def _get_id(self):
        # return datetime.fromtimestamp(self.created_timestamp).strftime(ID_FORMAT)
        return shortuuid.uuid(name=str(self.created_timestamp) + self.bookmark['url'])[:6]

    def _create_slug(self):
        return slugify(self.bookmark['title']).replace("-", " ")[:80]

    def _find_or_create_filename(self):
        # first see if file we expect exists
        # if not, search for it by suuid, and if found, rename it
        # if not found, return ideal name
        correct_filename = os.path.join(args.dir, self.id + FILENAME_DELIMITER + self._create_slug() + ".org")
        if os.path.exists(correct_filename):
            return correct_filename
        else:
            for file in os.listdir(args.dir):
                if os.path.basename(file).startswith(self.id):
                    os.rename(file, correct_filename)
                    return correct_filename
            return correct_filename

    def _get_org_readlater(self):
        return f'{todo_readlater[0]} ' if self.bookmark['readlater'] == 'yes' else ''

    def _tags_as_string(self):
        return ':'.join(self.bookmark['tags'])

    def _tags_as_org_string(self):
        if self.bookmark['tags']:
            return '\t:' + self._tags_as_string() + ':'
        else:
            return ''

    def write_bookmark_file(self):
        global num_dl
        bm = self.bookmark
        with open(self.file, "w") as f:
            f.write(f'\n* {self._get_org_readlater()}[[{bm["url"]}][{bm["title"]}]]{self._tags_as_org_string()}')

            # PROPERTY DRAWER
            f.write('\n')
            f.write(':PROPERTIES:\n')
            f.write(f':CREATED: {org_timestamp(self.created_timestamp)}\n')
            f.write(f':UPDATED: {org_timestamp(self.modified_timestamp)}\n')
            f.write(f':SHARED: {bm["shared"]}\n')
            f.write(":END:\n")

            f.write(f'{bm["desc"]}\n')

            if bm['annotations']:
                f.write('\n')
                for annot in bm['annotations']:
                    f.write('** Annotation\n')
                    # f.write('#+BEGIN_QUOTE\n')
                    f.write(f'{annot["content"]}\n')
                    # f.write('#+END_QUOTE\n')

                    if annot['comments']:
                        f.write('*** Comments\n')
                        for comment in annot['comments']:
                            f.write('#+BEGIN_QUOTE\n')
                            f.write(f'{comment["content"]}\n')
                            f.write(f'-- {comment["user"]}, ')
                            f.write(f'{comment["created_at"]}\n')
                            f.write('#+END_QUOTE\n')
            num_dl += 1

            return f'Saved {self.file}'

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
                new_file_buffer += f':CREATED: {org_timestamp(self.created_timestamp)}\n'
                new_file_buffer += f':UPDATED: {org_timestamp(self.modified_timestamp)}\n'
                new_file_buffer += f':SHARED: {self.bookmark["shared"]}\n'
                new_file_buffer += f':END:\n'
                new_file_buffer += f'{self.bookmark["desc"]}'
            elif lineno >= end_lineno:
                new_file_buffer += line
            lineno += 1

        file_object.close()

        file_object = open(self.file, 'w')
        file_object.write(new_file_buffer)
        file_object.close()

    def fix_tags_for_delete(self):
        self.bookmark['tags'] = (',').join(self.bookmark['tags'])

    def delete(self, reason='local bookmark was deleted.'):
        global num_del
        self.fix_tags_for_delete()
        if not args.dry_run:
            print( 'deleting ', self.bookmark['title'], reason )
            url = f'https://secure.diigo.com/api/v2/bookmarks?key={args.key}&user={args.username}'
            response = requests.delete(url, auth=HTTPBasicAuth(args.username, args.pw), json=self.bookmark)
            response.close()
            num_del += 1
            return response.json()

class OrgBookmark:
    def __init__(self, file):
        self.file = file
        self.modified_timestamp = self._get_file_modtime()
        self.id = self._get_id_from_filename()
        self.bookmark = {}
        self.has_changed = self.modified_timestamp > last_sync_time
        self.logging_title = f'{self.file[:50]}'
        self.incomplete = True
        logline('Reading', self.logging_title, org_timestamp(self.modified_timestamp), "CHANGED" if self.has_changed else "")

    def get_field(self, field):
        if self.incomplete:
            self.parse_and_fill_out()

        return self.bookmark[field]

    def _get_id_from_filename(self):
        basename = os.path.basename(self.file)
        return basename[0:basename.find(FILENAME_DELIMITER)]

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

    def get_node_shared(self,node):
        return node.get_property('SHARED')

    def get_node_readlater(self,node):
        return 'yes' if node.todo != None else 'no'

    def is_identical_to_match(self):
        return are_bookmarks_identical(self, self.match)

    def parse_and_fill_out(self):
        env = orgparse.OrgEnv(todos=todo_readlater, filename=self.file)
        root = orgparse.load(self.file, env=env)
        node = root.children[0]
        self.bookmark['title'] = self.get_node_title(node)
        self.bookmark['url'] = self.get_node_url(node)
        self.bookmark['tags'] = (self.get_node_tags(node))
        self.bookmark['desc'] = self.get_node_desc(node)
        self.bookmark['shared'] = self.get_node_shared(node)
        self.bookmark['readlater'] = self.get_node_readlater(node)
        self.incomplete = False

    def fix_tags_for_upload(self):
        self.bookmark['tags'] = (',').join(self.bookmark['tags'])

    def fix_readlater_for_upload(self):
        self.bookmark['readLater'] = self.bookmark['readlater']

    def send(self, reason=''):
        global num_ul
        self.parse_and_fill_out()
        self.fix_tags_for_upload()
        self.fix_readlater_for_upload()
        url = f'https://secure.diigo.com/api/v2/bookmarks?key={args.key}&user={args.username}&merge=no'
        if not args.dry_run:
            print( 'sending ', self.bookmark['title'], reason )
            response = requests.post(url, auth=HTTPBasicAuth(args.username, args.pw), json=self.bookmark)
            response.close()
            num_ul += 1
            return response.json()
        else:
            print( 'Dry-run: ', self.bookmark['title'], reason, '\n', url )

    def delete(self):
        global num_del
        os.remove(self.file)
        num_del += 1

    def get_id_desc_tail(self):
        return f'//diigorg id:{self.id}'

def org_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(ORG_TIMESTAMP_FORMAT)

def find_matching_bookmark(bm_list, bm):
    results = [item for item in bm_list if item.id == bm.id]
    return results[0] if len(results) == 1 else None

def logline( action='', title='', timestamp='', status='' ):
    logging.info( f'{action.ljust(10)} {title.ljust(50)} {timestamp.ljust(10)} {status.ljust(10)}')

def are_bookmarks_identical(bm1, bm2):
    if type(bm1) == OrgBookmark:
        bm1.parse_and_fill_out()

    if type(bm2) == OrgBookmark:
        bm2.parse_and_fill_out()

    same = True

    # these are the fields we can upload
    for item in ['title', 'url', 'tags', 'desc', 'shared', 'readlater']:
        if bm1.bookmark[item] != bm2.bookmark[item]:
            same = False
            # print(bm1.id, item, type(bm1), bm1.bookmark[item])
            # print(bm2.id, item, type(bm2), bm2.bookmark[item])
            # print('\n')
            break

    return same

if args.test:
    FETCH_START = 0
    FETCH_STOP_AT = 10
    FETCH_COUNT_PER_TRANCHE = 4
    FETCH_SORT = 1
    print( "TESTING..." )
else:
    FETCH_START = 0
    FETCH_STOP_AT = -1
    FETCH_COUNT_PER_TRANCHE = 100
    FETCH_SORT = 1

def fetch_tranche(start):
    if FETCH_STOP_AT >= 0 and start >= FETCH_STOP_AT:
        return ''

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={args.key}&user={args.username}&filter=all&count={FETCH_COUNT_PER_TRANCHE}&start={start}&sort={FETCH_SORT}'
    response = requests.get(url, auth=HTTPBasicAuth(args.username, args.pw))

    # spinner
    sys.stdout.write(next(spinner))
    sys.stdout.flush()
    sys.stdout.write('\b')

    response.close()
    return response.json()


def fetch_diigo_bookmarks(target_list):

    logging.info('\n-- Downloading bookmarks from Diigo')

    start = FETCH_START
    while bookmarks_tranche := fetch_tranche(start=start):
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

last_sync_time = 0;
try:
    with open(os.path.join(args.dir,'.diigorg.sync'), 'r') as f:
        last_sync_time = int(f.readline())
        last_sync_time_string = f'-- LAST SYNC: {time.strftime(ORG_TIMESTAMP_FORMAT, time.localtime(last_sync_time))}'
except IOError:
    last_sync_time_string = "first sync. stomping local data"

print(last_sync_time_string)
logline(last_sync_time_string)

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
sys.stdout.write("Fetching bookmarks...")
remote_bookmark_list = []
fetch_diigo_bookmarks(remote_bookmark_list)

if args.force_download:
    print( 'OVERWRITING LOCAL FILES' )
    for bm in remote_bookmark_list:
        bm.write_bookmark_file()
    exit()

#-----------------------------------------------
# iterate local bookmarks
local_bookmark_list = []

logging.info('\n-- Collecting local org bookmarks')
for file in os.listdir(args.dir):
    if not file.endswith('.org'):

        logging.debug(f'Skipping local file -- {file}')

        continue

    local_bookmark_list.append(lbm := OrgBookmark(file))

# we don't need to iterate twice but this keeps the logs pretty
logging.info('\n-- Evaluating local org bookmarks')
for lbm in local_bookmark_list:
    lbm.match = find_matching_bookmark(remote_bookmark_list, lbm)
    lbm.is_matched = lbm.match != None

    action=''
    if not lbm.has_changed and lbm.is_matched:
        logline('Local', lbm.logging_title, 'No Change')
        continue
    elif not lbm.has_changed and not lbm.is_matched:
        logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' is old and does not exist on server. Mark to delete.')
        action = 'delete'
    elif lbm.has_changed and not lbm.is_matched:
        logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' is a new bookmark. Mark to upload.')
        action = 'send new'
    else: # has changed and is matched
        if (match_is_old := lbm.match.modified_timestamp <= last_sync_time):
            logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' has changed and remote bookmark has not changed. Mark to upload.')
            action = 'send update'
        else: # remote bookmark has also changed
            if (real_conflict := not lbm.is_identical_to_match()):
                logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' has changed and remote bookmark has also changed. Mark to resolve.')
                action = 'resolve'
            else:
                logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' has been touched but is identical to remote bookmark. Mark to update remote timestamp.')
                action = 'send timestamp'

    result = ''
    match action:
        case 'resolve':
            print(lbm.id,lbm.get_field('title'),"both local and remote bookmarks have changed")
        case 'send new':
            result = lbm.send(action)
        case 'send update':
            result = lbm.send(action)
        case 'send timestamp':
            result = lbm.send(action)
        case 'delete':
            result = lbm.delete()

    # print(result)

logging.info('\n-- Comparing to downloaded Diigo bookmarks')
for rbm in remote_bookmark_list:
    rbm.match = find_matching_bookmark(local_bookmark_list, rbm)
    rbm.is_matched = rbm.match != None

    # old bookmark. Move on.
    if not rbm.has_changed and rbm.is_matched:
        logline('Remote', rbm.logging_title, org_timestamp(rbm.modified_timestamp), '- has not changed')
        continue

    action = ''
    if rbm.is_new:
        logline('Remote', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'NEW. Writing to {rbm.file}')
        rbm.write_bookmark_file()
    elif rbm.has_changed:
        logline('Remote', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'CHANGED. Mark for updating {rbm.match.logging_title}.')
        action = 'write update'
    elif not rbm.is_new and not rbm.is_matched:
        logline('Remote', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'DELETED. Mark for deletion.')
        action = 'delete'

    result = ''
    match action:
        case 'write update':
            result = rbm.update_bookmark_file()
        case 'delete':
            result = rbm.delete()

    # print(result)

with open(os.path.join(args.dir, '.diigorg.sync'), 'w') as f:
    f.write(str(int(time.time() + 1)))


print('Done!')
print(f'Downloaded: {num_dl}')
print(f'Uploaded: {num_ul}')
print(f'Deleted {num_del}')

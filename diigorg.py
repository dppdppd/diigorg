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
import uuid
import re
import glob
import configparser


def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"{path} is not a valid path")

argParser = argparse.ArgumentParser(description = 'Sync Diigo bookmarks to Org files')
argParser.add_argument('-i', '--incremental', nargs='?', const=True,  help='Will push any recent local changes but will only download recent changes in bookmark name, url, description, and/or annotations on diigo.com.')
argParser.add_argument('-d', '--dir', type=dir_path, default=os.getcwd(), help='Directory to sync')
argParser.add_argument('--reset', nargs='?', const=True, help='If specified, diigorg will redownload all bookmarks and ignore local changes')
argParser.add_argument('--safe', nargs='?', const=True, help='If specified, diigorg will not delete or modify any bookmarks on diigo.com')
argParser.add_argument('--test', nargs='?', const=True, help='for debugging only. do not use.')
argParser.add_argument('--fix-tags-on-server', nargs='?', const=True, help='If specified, diigorg will do a --full sync and make all diigo server tags org-compliant')
args = argParser.parse_args()

####### CONFIG FILE
cfg = configparser.ConfigParser()
CFG_FILE = os.path.join(args.dir, 'diigorg.cfg')

if os.path.exists(CFG_FILE):
    cfg.read(CFG_FILE)

    if not cfg.getboolean("file_properties","tags",fallback=False) and not cfg.getboolean("heading_properties", "tags", fallback=False):
        print( "diigorg.cfg error: Both file_properties:tags and heading_properties:tags are set off. One of them needs to be on." )
        exit()
else:
    cfg.add_section('diigo_credentials')
    cfg['diigo_credentials'] = {
        'username' : '',
        'passwd' : '',
        'api_key' : 'Get your diigo application key here: https://www.diigo.com/api_keys/new/'
    }
    cfg.add_section('options')
    cfg['options'] = {
        'subdirs' : '%%Y',
        'todo_keyword' : 'TODO',
        'notes_section' : 'yes'
    }
    cfg.add_section('file_properties')
    cfg['file_properties'] = {
        'title' : 'yes',
        'org_id' : 'no',
        'roam_refs' : 'no',
        'diigo_search_link' : 'no',
        'tags' : 'no'
        }
    cfg.add_section('heading_properties')
    cfg['heading_properties'] = {
        'org_id' : 'yes',
        'roam_refs' : 'no',
        'diigo_search_link' : 'yes',
        'tags' : 'yes'
        }

    with open(CFG_FILE, 'w') as cfgfile:
        cfg.write(cfgfile)
    print( 'diigorg.cfg has been created. Edit it and rerun diigorg.' )
    exit()

if not args.dir.endswith('/'):
    args.dir = args.dir + '/'

stuff_dir = os.path.join(args.dir, '.diigorg')
if not os.path.exists(stuff_dir):
    os.mkdir(stuff_dir)

if args.reset:
    args.incremental = False
    args.safe = True

if args.fix_tags_on_server:
    args.incremental = False

logging.basicConfig(filename=os.path.join(stuff_dir,'diigorgg.log'), encoding='utf-8', level=logging.INFO, filemode='w')

ORG_TIMESTAMP_FORMAT = '[%Y-%m-%d %a %H:%M:%S]'
FILENAME_DELIMITER = ' - '

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
        self.folder = datetime.fromtimestamp(self.created_timestamp).strftime(cfg["options"]["subdirs"]) if cfg["options"]["subdirs"] else ''
        self.is_new = self.created_timestamp > last_sync_time
        self.full_id = self._get_full_id()
        self.short_id = self._get_short_id()
        self.file = self._find_or_create_filename()
        self._convert_tag_string_to_tag_set()
        self._convert_shared_to_private()
        self.logging_title = self.bookmark["url"][6:56].ljust(50)
        logline('Receiving', self.logging_title, org_timestamp(self.modified_timestamp), 'NEW' if self.is_new else '')
        logging.debug(self.bookmark)

    def get_field(self, field):
        return self.bookmark[field]

    def _convert_shared_to_private(self):
        self.bookmark['private'] = 'yes' if self.bookmark['shared'] == 'no' else 'yes'

    def _convert_tag_string_to_tag_set(self):
        # print(self.bookmark['tags'])
        tag_set = set()
        for tag in set(self.bookmark['tags'].split(',')):
            if tag not in ['notag', 'no_tag', '']:
                tag_set.add(tag)
        self.bookmark['tags'] = tag_set
        # print(self.bookmark['tags'])
        # print('\n')

    def _get_created_timestamp(self):
        return int(parser.parse(self.bookmark['created_at']).timestamp())

    def _get_modified_timestamp(self):
        return int(parser.parse(self.bookmark['updated_at']).timestamp())

    def _get_full_id(self):
        return uuid.uuid5(uuid.NAMESPACE_URL, str(self.created_timestamp) + self.bookmark['url'])

    def _get_short_id(self):
        # return datetime.fromtimestamp(self.created_timestamp).strftime(ID_FORMAT)
        return datetime.fromtimestamp(self.created_timestamp).strftime('%y%m%d') + shortuuid.encode(self.full_id)[:4]

    def _create_slug(self):
        return slugify(self.bookmark['title']).replace("-", " ")[:80]

    def _find_or_create_filename(self):
        # first see if file we expect exists
        # if not, search for it by suuid, and if found, rename it
        # if not found, return ideal name
        correct_filename = os.path.join(args.dir, self.folder, self.short_id + FILENAME_DELIMITER + self._create_slug() + ".org")
        if os.path.exists(correct_filename):
            return correct_filename
        else:
            for file in glob.iglob(args.dir + '**/*.org', recursive=True):
                if os.path.basename(file).startswith(self.short_id):
                    os.rename(file, correct_filename)
                    return correct_filename
            return correct_filename

    def _get_org_readlater(self):
        return f'{cfg["options"]["todo_keyword"]} ' if self.bookmark['readlater'] == 'yes' else ''

    def _tags_to_org_string(self):
        if self.bookmark['tags']:
            for tag in self.bookmark['tags']:
                self.bookmark['tags'] = [re.sub('[^A-Za-z0-9@]+', '_', tag) for tag in self.bookmark['tags']]

            return ':' + ':'.join(self.bookmark['tags']) + ':'
        else:
            return ''

    def write_bookmark_file(self):
        global num_dl
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w") as f:
            f.write(self.create_bookmark_file_synced_section())
            num_dl += 1

        return f'Saved {self.file}'

    def create_bookmark_file_synced_section(self):
        bm = self.bookmark

        query = slugify(bm['title']).replace("-", "+")[:30]
        query = query[:query.rfind('+')]
        query_link = f'https://diigo.com/user/{cfg["diigo_credentials"]["username"]}?query={query}'

        buf = ''
        if cfg.getboolean('file_properties','title',fallback=False):
            buf += f'#+TITLE: {bm["title"]}\n'

        if cfg.getboolean('file_properties','diigo_search_link',fallback=False):
            buf += f'#+DIIGO_LINK: {query_link}\n'

        if cfg.getboolean('file_properties','tags',fallback=False):
            buf += f'#+FILETAGS: {self._tags_to_org_string()}\n'

        if cfg.getboolean('file_properties','roam_refs',fallback=False):
            buf += f'#+ROAM_REFS: {bm["url"]}\n'

        buf += f'* {self._get_org_readlater()}[[{bm["url"]}][{bm["title"]}]]'

        if cfg.getboolean('heading_properties','tags',fallback=True):
            buf += f' {self._tags_to_org_string()}'

        buf += '\n'
        buf += ':PROPERTIES:\n'

        if cfg.getboolean('heading_properties','diigo_search_link',fallback=False):
            buf += f':DIIGO_LINK:{query_link}\n'

        buf += f':CREATED: {org_timestamp(self.created_timestamp)}\n'
        buf += f':UPDATED: {org_timestamp(self.modified_timestamp)}\n'

        if cfg.getboolean('heading_properties','org_id',fallback=False):
            buf += f':ID: {self.full_id}\n'

        if cfg.getboolean('heading_properties','roam_refs',fallback=False):
            buf += f':ROAM_REFS: {bm["url"]}\n'

        buf += f':ID2: {self.short_id}\n'
        buf += f':PRIVATE: {bm["private"]}\n'
        buf += ":END:\n"
        buf += f'{bm["desc"]}'

        if bm['annotations']:
            buf += '\n'
            for annot in bm['annotations']:
                buf += '** Highlight\n'
                buf += '#+Editing of highlights and comments can only be done on Diigo.com\n'
                buf += f'#+{query_link}\n'
                # buf += '#+BEGIN_QUOTE\n')
                buf += f'{annot["content"]}\n'
                # buf += '#+END_QUOTE\n')

                if annot['comments']:
                    # buf += '*** Comments\n'
                    for comment in annot['comments']:
                        buf += '#+BEGIN_QUOTE\n'
                        buf += f'{comment["content"]}\n'
                        buf += f'-- {comment["user"]}, '
                        buf += f'{comment["created_at"]}\n'
                        buf += '#+END_QUOTE\n'

        if cfg.getboolean('options', 'notes_section', fallback=True):
            buf += '* Notes\n'

        return buf

    def update_bookmark_file(self):
        ""
        global num_dl
        file_object = open(self.file, 'r')
        source_buffer = file_object.readlines()
        file_object.close()

        new_buffer = self.create_bookmark_file_synced_section()

        root = orgparse.loadi(source_buffer)

        if len(root.children) > 1:
            start_copy_line = root.children[1].linenumber

            for idx, line in enumerate(source_buffer):
                if idx >= start_copy_line:
                    new_buffer += line

        file_object = open(self.file, 'w')
        file_object.write(new_buffer)
        file_object.close()
        num_dl += 1

    def fix_tags_for_delete(self):
        self.bookmark['tags'] = (',').join(self.bookmark['tags'])

    def delete(self, reason='local bookmark was deleted.'):
        global num_del
        self.fix_tags_for_delete()
        num_del += 1
        if not args.safe:
            print( 'deleting on server:', self.bookmark['title'], ':', reason )
            url = f'https://secure.diigo.com/api/v2/bookmarks?key={cfg["diigo_credentials"]["api_key"]}&user={cfg["diigo_credentials"]["username"]}'
            response = requests.delete(url, auth=HTTPBasicAuth(cfg["diigo_credentials"]["username"], cfg["diigo_credentials"]['passwd']), json=self.bookmark)
            response.close()
            return response.json()
        else:
            print( 'Would be deleting ', self.bookmark['title'], reason )

# a class for local bookmark files. We don't open the file unless we have to.
class OrgBookmark:
    def __init__(self, file):
        self.file = file
        self.short_id = self.get_short_id_from_file()
        self.full_id = None
        self.node = None
        self.modified_timestamp = self._get_file_modtime()
        self.bookmark = {}
        self.has_changed = self.modified_timestamp > last_sync_time
        self.logging_title = self.short_id + ' ' + f'{self.file[:50].ljust(50)}'
        # logline('Reading', self.logging_title, org_timestamp(self.modified_timestamp), "CHANGED" if self.has_changed else "")

    def is_an_org_bookmark(self):
        self.parse_and_fill_out()
        return self.node and self.get_node_short_id()

    def get_field(self, field):
        self.parse_and_fill_out()
        return self.bookmark[field]

    def get_short_id_from_file(self):
        basename = os.path.basename(self.file)
        return basename[0:basename.find(FILENAME_DELIMITER)]

    def _get_file_modtime(self):
        return os.path.getmtime(self.file)

    def get_node_title(self):
        self.parse_and_fill_out()
        h = self.node.get_heading(format='raw')
        title = h[h.rfind("][")+2:h.rfind("]")-1]
        return title

    def get_node_url(self):
        self.parse_and_fill_out()
        h = self.node.get_heading(format='raw')
        url = h[h.find("[")+2:h.find("]")]
        return url

    def get_node_tags(self):
        self.parse_and_fill_out()
        # print(self.node.shallow_tags)
        return self.node.tags

    def get_node_desc(self):
        self.parse_and_fill_out()
        return self.node.body

    def get_node_private(self):
        self.parse_and_fill_out()
        return self.node.get_property('PRIVATE')

    def get_node_full_id(self):
        self.parse_and_fill_out()
        return self.node.get_property('ID')

    def get_node_short_id(self):
        self.parse_and_fill_out()
        return self.node.get_property('ID2')

    def get_node_readlater(self):
        return 'yes' if self.node.todo != None else 'no'

    def compare_to_match(self):
        return compare_bookmarks(self, self.match, comparison_fields = ['title', 'url', 'desc'])

    def compare_to_match_minor(self):
        return compare_bookmarks(self, self.match,  comparison_fields = ['tags', 'private', 'readlater'])

    def parse_and_fill_out(self):
        if self.node:
            return

        env = orgparse.OrgEnv(todos=[cfg["options"]["todo_keyword"]], filename=self.file)
        root = orgparse.load(self.file, env=env)
        self.node = root.children[0] if root.children else None
        if not self.node:
            return

        self.bookmark['title'] = self.get_node_title()
        self.bookmark['url'] = self.get_node_url()
        self.bookmark['tags'] = (self.get_node_tags())
        self.bookmark['desc'] = self.get_node_desc()
        self.bookmark['private'] = self.get_node_private()
        self.bookmark['readlater'] = self.get_node_readlater()
        self.full_id = self.get_node_full_id()

    def fix_tags_for_upload(self):
        self.bookmark['tags'] = (',').join(self.bookmark['tags'])

    def fix_readlater_for_upload(self):
        self.bookmark['readLater'] = self.bookmark['readlater']

    def send(self, reason=''):
        global num_ul
        self.parse_and_fill_out()
        self.fix_tags_for_upload()
        self.fix_readlater_for_upload()
        url = f'https://secure.diigo.com/api/v2/bookmarks?key={cfg["diigo_credentials"]["api_key"]}&user={cfg["diigo_credentials"]["username"]}&merge=no'
        if not args.safe:
            print( 'sending ', self.bookmark['title'], reason )
            response = requests.post(url, auth=HTTPBasicAuth(cfg["diigo_credentials"]["username"], cfg["diigo_credentials"]['passwd']), json=self.bookmark)
            response.close()
            num_ul += 1
            return response.json()

    def delete(self):
        global num_del
        os.remove(self.file)
        num_del += 1

def org_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(ORG_TIMESTAMP_FORMAT)

def find_matching_bookmark(bm_list, bm):
    results = [item for item in bm_list if item.short_id == bm.short_id]
    return results[0] if len(results) == 1 else None

def logline( action='', title='', timestamp='', status='' ):
    logging.info( f'{action.ljust(10)} {title.ljust(50)} {timestamp.ljust(10)} {status.ljust(10)}')


def compare_bookmarks(bm1, bm2, comparison_fields):
    if type(bm1) == OrgBookmark:
        bm1.parse_and_fill_out()

    if type(bm2) == OrgBookmark:
        bm2.parse_and_fill_out()

    diff = []

    # these are the fields we can upload
    for item in comparison_fields:
        # print(bm1.bookmark)
        # print(bm2.bookmark)
        if bm1.bookmark[item] != bm2.bookmark[item]:
            diff.append([item, bm1.bookmark[item], bm2.bookmark[item]])

    return diff

if args.test:
    FETCH_START = 0
    FETCH_STOP_AT = 30
    FETCH_COUNT_PER_TRANCHE = 20
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

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={cfg["diigo_credentials"]["api_key"]}&user={cfg["diigo_credentials"]["username"]}&filter=all&count={FETCH_COUNT_PER_TRANCHE}&start={start}&sort={FETCH_SORT}'
    response = requests.get(url, auth=HTTPBasicAuth(cfg["diigo_credentials"]["username"], cfg["diigo_credentials"]['passwd']))

    # spinner
    sys.stdout.write(next(spinner))
    sys.stdout.flush()
    sys.stdout.write('\b')

    response.close()
    return response.json()


def fetch_diigo_bookmarks(target_list):

    logging.info('\n-- Downloading bookmarks from Diigo')

    start = FETCH_START
    done = False
    while bookmarks_tranche := fetch_tranche(start=start):
        for b in bookmarks_tranche:
            entry = DiigoBookmark(b)
            if not args.incremental or entry.has_changed:
                remote_bookmark_list.append(entry)
            elif args.incremental and not entry.has_changed:
                done = True
                break
        if done:
            break
        else:
            start += 100


last_sync_time = 0
last_sync_time_string = "First sync. Downloading all bookmarks and stomping local data, if there is any."
if args.reset:
    for file in glob.iglob(args.dir + '**/*.org', recursive=True):
        if OrgBookmark(file).is_an_org_bookmark():
            os.remove(file)
else:
    try:
        with open(os.path.join(stuff_dir,'.diigorg.sync'), 'r') as f:
            last_sync_time = int(f.readline())
            last_sync_time_string = f'-- LAST SYNC: {time.strftime(ORG_TIMESTAMP_FORMAT, time.localtime(last_sync_time))}'
    except:
        decision = input( f'Can\'t find {stuff_dir}. Are you sure you are in the correct directory or specified the correct --dir? [y/n]: ' )
        match decision:
            case 'y':pass
            case 'n':exit()


print(last_sync_time_string)
logline(last_sync_time_string)

# fetch all diigo bookmarks
sys.stdout.write('Fetching bookmarks...')
remote_bookmark_list = []
fetch_diigo_bookmarks(remote_bookmark_list)

sys.stdout.write('\n')

#-----------------------------------------------
# iterate local bookmarks
local_bookmark_list = []

if not args.reset:
    logging.info('\n-- Collecting local org bookmarks from ' + args.dir)
    for file in glob.iglob(args.dir + '**/*.org', recursive=True):
        logline('Local', file, '-- Parsing')
        local_bookmark_list.append(lbm := OrgBookmark(file))

    # we don't need to iterate twice but this keeps the logs pretty
    logging.info('\n-- Evaluating local org bookmarks')
    for lbm in local_bookmark_list:
        lbm.match = find_matching_bookmark(remote_bookmark_list, lbm)
        lbm.is_matched = lbm.match != None

        action=''
        if not args.incremental and lbm.is_matched and lbm.compare_to_match_minor():
            # if we're doing a full sync, compare every bookmark
            logline('Local', lbm.logging_title, 'full sync and tags or readlater are different')
            action = 'resolve'
        elif not args.incremental and not lbm.has_changed and not lbm.is_matched:
            # in the case that we downloaded all remote bookmarks, we can determine whether
            # the absence of a bookmark on diigo means we should delete it locally
            logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' hasn\'t changed and we know it does not exist on server. Delete.')
            action = 'delete'
        elif not lbm.has_changed and lbm.is_matched:
            logline('Local', lbm.logging_title, 'hasn\'t changed and remote match exists.')
        elif not args.incremental and not lbm.has_changed:
            logline('Local', lbm.logging_title, 'hasn\'t changed and we don\'t know whether remote exists')
        elif lbm.has_changed:
            if lbm.is_matched and lbm.match.has_changed and lbm.compare_to_match():
                action = 'resolve'
            else:
                logline('Local', lbm.logging_title, org_timestamp(lbm.modified_timestamp), ' has changed and there\'s no conflict. Upload.')
                action = 'upload'

        if action == 'resolve':
            decision = ''
            all_diffs = lbm.compare_to_match() + lbm.compare_to_match_minor()

            if args.fix_tags_on_server:
                if len(all_diffs) == 1 and all_diffs[0][0] == 'tags':
                    print(f'{lbm.logging_title} : {all_diffs[0][2]} --> {all_diffs[0][1]}')
                    action = 'upload'
            else:
                print('THERE\'S A CONFLICT:')
                print(f'{lbm.logging_title} has changed both in file and on the server.')
                print('\n')
                print(f'{"Field".ljust(40)} {"Local".ljust(40)} {"Server".ljust(40)}')
                for item in all_diffs:
                    print(f'{str(item[0]).ljust(40)} {str(item[1]).ljust(40)} {str(item[2]).ljust(40)}')
                print('\n')

                while decision.lower() not in ['l','s']:
                    decision = input('Enter "s" or "l" or "Ctrl-c"\n[l] Keep local version. [s] Keep server version. [Ctrl-c] Cancel sync :')

                match decision:
                    case 'l':
                        action = 'upload'
                    case 's':
                        action = 'update'

        match action:
            case 'upload':
                lbm.send()
            case 'delete':
                lbm.delete()
            case 'update':
                lbm.match.update_bookmark_file()

logging.info('\n-- Comparing to downloaded Diigo bookmarks')
for rbm in remote_bookmark_list:
    rbm.match = find_matching_bookmark(local_bookmark_list, rbm)
    rbm.is_matched = rbm.match != None

    # old bookmark. Move on.
    action = ''
    if not rbm.has_changed and rbm.is_matched:
        logline('Server', rbm.logging_title, org_timestamp(rbm.modified_timestamp), '- has not changed')
    elif rbm.is_new or args.reset:
        logline('Server', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'NEW. Writing to {rbm.file}')
        action = 'write'
    elif rbm.has_changed:
        logline('Server', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'CHANGED. Mark for updating {rbm.match.logging_title}.')
        action = 'update'
    elif not rbm.is_new and not rbm.is_matched:
        logline('Server', rbm.logging_title, org_timestamp(rbm.modified_timestamp), f'DELETED. Mark for deletion.')
        action = 'delete'

    result = ''
    match action:
        case 'write':
            rbm.write_bookmark_file()
        case 'update':
            rbm.update_bookmark_file()
        case 'delete':
            rbm.delete()

with open(os.path.join(stuff_dir, '.diigorg.sync'), 'w') as f:
    f.write(str(int(time.time() + 1)))


print('Done!')
print(f'Downloaded \t{num_dl} bookmarks.')
print(f'Uploaded \t{num_ul} bookmarks.')
print(f'Deleted \t{num_del} bookmarks.')

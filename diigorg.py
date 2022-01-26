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

logging.basicConfig(filename='diigorg.log', encoding='utf-8', level=logging.DEBUG, filemode='w')

spinner = itertools.cycle(['-', '\\', '|', '/'])

argParser = argparse.ArgumentParser(description = 'Import Diigo bookmarks into Buku')
argParser.add_argument('key', metavar='key', type=str, help='Your Diigo application key')
argParser.add_argument('username', metavar='username', type=str, help='Your Diigo username')
argParser.add_argument('pw', metavar='pw', type=str, help='Your Diigo password')

key = argParser.parse_args().key
user = argParser.parse_args().username
pw = argParser.parse_args().pw

# debugging variables
limit = 10
count = 10

bookmarks_file = "diigo-bookmarks.org"
date_id_format = '%y%m%d%H%M%S'
filename_delimiter = ' - '
target_dir = "."

# * old shit
# def buku_item_to_dict(b_item):
#     """ convert buku item to universal dict """
#     out = {
#         'url': b_item[1],
#         'title': b_item[2],
#         'tags': sorted(b_item[3].split(',')[1:-1]),
#         'timestamp': b_item[0],
#         'desc' : b_item[4]
#     }

#     return out


# def tags_to_tagstring(tag_list):
#     """ convert list of tags to tagstring """
#     if tag_list == []:
#         return ','

#     return ',{},'.format(','.join(tag_list))


# def sort_dict_items(item_list):
#     """ sort list of dict items based on update time """
#     return sorted(item_list, key=lambda x: x['timestamp'])


# def dict_list_difference(l1, l2):
#     """ return items in l1 but not in l2 """
#     return [i for i in l1 if i['url'] not in [j['url'] for j in l2]]


# def dict_list_ensure_unique(item_list):
#     """ ensure all items in list have a unique url (newer wins) """
#     return list({i['url']: i for i in item_list}.values())

# ########
# def no_tag(var):
#     return var != 'no_tag'


# def diigo_get_desc(item):
#     desc = f"{item.get('desc')}\n" if item.get('desc') else ""
#     return desc

# def diigo_get_comm(item, sub):
#     rval = ""
#     if item.get('comments'):
#         for c in item.get('comments'):
#             rval += '\n'
#             if sub: rval += '\t'
#             rval += f'\"{c.get("content")}\" --{c.get("user")}, {c.get("created_at")}\n'
#     return rval

# def diigo_get_annot(item):
#     rval = ""
#     if item.get('annotations'):
#         for a in item.get('annotations'):
#             rval += f'\n\"{a.get("content")}\"\n'
#             rval += diigo_get_comm(a, sub = True)
#     return rval

# def diigo_make_desc(item):
#     desc = diigo_get_desc(item)
#     anno = diigo_get_annot(item)
#     comm = diigo_get_comm(item, sub = False)
#     rval = f"{desc}{anno}{comm}"
#     return rval

# def diigo_item_to_dict(p_item):
#     """ convert diigo item to universal dict """
#     out = {
#         'url': p_item.get('url'),
#         'title': p_item.get('title'),
#         'tags': sorted((filter(no_tag, p_item.get('tags').split(',')))),
#         'timestamp': parser.parse(p_item.get('created_at')),
#         'desc' : diigo_make_desc(p_item)
#     }
#     return out

def fetch_bookmarks(start, count):
    if limit >= 0 and start >= limit:
        return ''

    if count == -1 or count > 100:
        count = 100

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={key}&user={user}&filter=all&count={count}&start={start}'
    response = requests.get(url, auth=HTTPBasicAuth(user, pw))

    # spinner
    sys.stdout.write(next(spinner))   # write the next character
    sys.stdout.flush()                # flush stdout buffer (actual character display)
    sys.stdout.write('\b')            # erase the last written char

    response.close()
    return response.json()

def send_bookmark(bookmark):

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={key}&user={user}&merge=no'
    response = requests.post(url, auth=HTTPBasicAuth(user, pw), json=bookmark)

    response.close()
    return response.json()


def create_slug(title):
   return slugify(title).replace("-", " ")[:80]

def get_date_id(bookmark):
    return get_date(bookmark, 'created_at').strftime(date_id_format)

def create_file_name(bookmark):
    out = os.path.join(target_dir, get_date_id(bookmark) + filename_delimiter + create_slug(bookmark.get('title')) + ".org")
    return out

# * [[title][url]] :tags:
#:PROPERTIES:
#:CREATED:
#:END:
# desc
#
def get_date(bookmark, date_string):
    return parser.parse(bookmark.get(date_string))

def convert_to_org_timestamp(date):
    return date.strftime('[%Y-%m-%d %a %H:%M:%S]')

def get_read_later(bookmark):
    if (bookmark.get('readlater') == 'yes'):
        return 'TODO '
    else:
        return ''

def write_bookmark_file(bookmark):
    ""
    with open(create_file_name(bookmark), "w") as write_buffer:
        write_buffer.write(f'* {get_read_later(bookmark)}[[{bookmark.get("url")}][{bookmark.get("title")}]]')

        # TAGS
        if bookmark.get("tags") != "no_tag":
            write_buffer.write("\t:")
            write_buffer.writelines(bookmark.get("tags").replace(',',':'))
            write_buffer.write(":")

        # PROPERTY DRAWER
        write_buffer.write('\n')
        write_buffer.write(':PROPERTIES:\n')
        write_buffer.write(f':ID: {get_date_id(bookmark)}\n')
        write_buffer.write(f':CREATED: {convert_to_org_timestamp(get_date(bookmark, "created_at"))}\n')
        write_buffer.write(f':UPDATED: {convert_to_org_timestamp(get_date(bookmark, "updated_at"))}\n')
        write_buffer.write(f':SHARED: {bookmark.get("shared")}\n')
        write_buffer.write(":END:\n")

        write_buffer.write(f'{bookmark.get("desc")}\n')

def get_node_title(node):
    h=node.get_heading(format='raw')
    title = h[h.rfind("[")+1:h.rfind("]")-1]
    return title

def get_node_url(node):
    h=node.get_heading(format='raw')
    url = h[h.find("[")+2:h.find("]")]
    return url

def get_node_tags(node):
    return node.shallow_tags

def get_node_desc(node):
    return node.body

def get_node_id(node):
    return node.get_property('ID')

def get_node_shared(node):
    return node.get_property('SHARED')

def get_node_readlater(node):
    return node.todo != None

def get_file_modtime(file):
    return datetime.fromtimestamp(os.path.getmtime(file), timezone.utc).strftime(date_id_format)

def get_node_id_from_filename(file):
    basename = os.path.basename(file)
    return basename[0:basename.find(filename_delimiter)]

def fill_out_local_bookmark(bookmark, file):
    root = orgparse.load(file)
    for node in root.children:
        bookmark['title'] = get_node_title(node)
        bookmark['url'] = get_node_url(node)
        bookmark['tags'] = get_node_tags(node)
        bookmark['desc'] = get_node_desc(node)
        bookmark['node_id'] = get_node_id(node)
        bookmark['shared'] = get_node_shared(node)
        bookmark['readlater'] = get_node_readlater(node)

def get_date_id_from_diigo_bookmark(bookmark):
    get_date(bookmark, "created_at").strftime(date_id_format)

def bookmarks_are_different(bm1, bm2):
    return

def is_bookmark_updated(bookmark):
    int(bookmark['modified']) > last_sync_time

def find_bookmark_by_id(bm_list, id):
    return next(item for item in bm_list if get_date_id_from_diigo_item(item) == id)

# bookmark_test = list_of_remote_bookmarks[-1]
# bookmark_test['tags'] = 'deft,emacs'
# bookmark_test['desc']='This is a new description. NEW'
# print(bookmark_test)
# send_bookmark(bookmark_test)
#--------------------------------------------------------------------------------------------------------
#
sys.stdout.write("Fetching bookmarks...")

last_sync_time = 0;
with open('.diigorg.sync') as f:
    last_sync_time = int(f.readline())

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


# dl all bookmarks items into robj

start = 0
list_of_remote_bookmarks = []
while bookmarks_tranche := fetch_bookmarks(start=start, count=count):
    if bookmarks_tranche:
        for b in bookmarks_tranche:
            logging.info(f'Recieving -- {b.get("url")}')
        list_of_remote_bookmarks += bookmarks_tranche
        start += 100

# read all local bookmarks into lobj (orgparse)
list_of_local_bookmarks = []
for file in os.listdir("."):
    if not file.endswith('.org'):
        continue

    bookmark = {
        'date_id' : get_node_id_from_filename(file),
        'modified' : get_file_modtime(file),
        'file' : file
    }
    list_of_local_bookmarks += bookmark;

#for each item in lobj
for lbm in list_of_local_bookmarks:
#   new = update > synctime
    bm_is_updated = is_bookmark_updated(lbm)
#   bm_is_matched = item in robj exists
    remote_matching_bm = find_bookmark_by_id(list_of_remote_bookmarks, lbm['date_id'])
    bm_is_matched = match != None

#   if not new and bm_is_matched
    if not bm_is_updated and bm_is_matched:
#       continue
        continue

#   conflict = new and bm_is_matched and remote item is new
    bm_is_conflicted = bm_is_updated and bm_is_matched and get_updated_time_from_diigo_item(remote_matching_bm) > last_sync_time
#   real_conflict = conflict and items different except for update time
    bm_is_truly_conflicted = bm_is_conflicted and not are_bookmarks_identical(lbm, remote_matching_bm)

#   add if bm_is_updated and not bm_is_matched
#   merge if new and not real_conflict // local mod time has changed and we just want to update the time on the remote bookmark
    act_send = bm_is_updated and (not bm_is_matched or not bm_is_truly_conflicted)

#   delete if not bm_is_updated and not bm_is_matched // we haven't changed it locally and it's no longer on the server
    act_delete_remotely = not bm_is_updated and not bm_is_matched

    act_resolve = bm_is_truly_conflicted

    if (act_resolve):
        # resolve
        print("both local and remote bookmarks have been bm_is_updated")

    elif (act_send):
        # add
        fill_out_local_bookmark(lbm,lbm['file'])
        print('send',lbm['title'])

    elif (act_delete_remotely):
        # delete
        fill_out_local_bookmark(lbm,lbm['file'])
        print('delete', lbm['title'])

#for each item in robj
for rbm in list_of_remote_bookmarks:
#   new = update > synctime
    bm_is_updated = is_bookmark_updated(rbm)
#   bm_is_matched = item in lobj exists
    local_matching_bm = find_bookmark_by_id(list_of_local_bookmarks, rbm['date_id'])
    bm_is_matched = local_matching_bm != None
#
#   if not new and bm_is_matched
    if not bm_is_updated and bm_is_matched:
        continue
#
#   conflict = updated and is matched and local item updated
#   // we already dealt with these but need to skip them here
    bm_is_conflicted = bm_is_updated and bm_is_matched and is_bookmark_updated(local_matching_bm)
#
#   write = new and not real_conflict
    act_write_locally = bm_is_updated and not bm_is_conflicted
#   delete = not updated and not bm_is_matched
    act_delete_locally = not bm_is_updated and not rbm['match']

    if (act_write_locally):
        print("write", rbm['title'])
    elif(act_delete_locally):
        print("delete", rbm['title'])

# for bookmark in list_of_remote_bookmarks:
#     logging.debug(bookmark)
#     write_bookmark_file(bookmark)

#
#write down sync time
#


sys.stdout.write("done!\n")

sys.stdout.write(f'{len(list_of_remote_bookmarks)} bookmarks fetched.\n')

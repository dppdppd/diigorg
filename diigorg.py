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
import os
from datetime import datetime
import django
from django.template.defaultfilters import slugify

logging.basicConfig(filename='diigorg.log', encoding='utf-8', level=logging.INFO, filemode='w')

spinner = itertools.cycle(['-', '\\', '|', '/'])

argParser = argparse.ArgumentParser( description = 'Import Diigo bookmarks into Buku')
argParser.add_argument('key', metavar='key', type=str, help='Your Diigo application key')
argParser.add_argument('username', metavar='username', type=str, help='Your Diigo username')
argParser.add_argument('pw', metavar='pw', type=str, help='Your Diigo password')

key = argParser.parse_args().key
user = argParser.parse_args().username
pw = argParser.parse_args().pw

# debugging variables
limit = 10
count = 10

def buku_item_to_dict(b_item):
    """ convert buku item to universal dict """
    out = {
        'url': b_item[1],
        'title': b_item[2],
        'tags': sorted(b_item[3].split(',')[1:-1]),
        'timestamp': b_item[0],
        'desc' : b_item[4]
    }

    return out


def tags_to_tagstring(tag_list):
    """ convert list of tags to tagstring """
    if tag_list == []:
        return ','

    return ',{},'.format(','.join(tag_list))


def sort_dict_items(item_list):
    """ sort list of dict items based on update time """
    return sorted(item_list, key=lambda x: x['timestamp'])


def dict_list_difference(l1, l2):
    """ return items in l1 but not in l2 """
    return [i for i in l1 if i['url'] not in [j['url'] for j in l2]]


def dict_list_ensure_unique(item_list):
    """ ensure all items in list have a unique url (newer wins) """
    return list({i['url']: i for i in item_list}.values())

########
def no_tag(var):
    return var != 'no_tag'


def diigo_get_desc( item ):
    desc = f"{item.get( 'desc' )}\n" if item.get('desc') else ""
    return desc

def diigo_get_comm( item, sub ):
    rval = ""
    if item.get( 'comments' ):
        for c in item.get( 'comments' ):
            rval += '\n'
            if sub: rval += '\t'
            rval += f'\"{c.get("content")}\" --{c.get("user")}, {c.get("created_at")}\n'
    return rval

def diigo_get_annot( item ):
    rval = ""
    if item.get( 'annotations' ):
        for a in item.get( 'annotations' ):
            rval += f'\n\"{a.get("content")}\"\n'
            rval += diigo_get_comm( a, sub = True )
    return rval

def diigo_make_desc( item ):
    desc = diigo_get_desc( item )
    anno = diigo_get_annot( item )
    comm = diigo_get_comm( item, sub = False )
    rval = f"{desc}{anno}{comm}"
    return rval

def diigo_item_to_dict(p_item):
    """ convert diigo item to universal dict """
    out = {
        'url': p_item.get('url'),
        'title': p_item.get('title'),
        'tags': sorted((filter(no_tag, p_item.get('tags').split(',')))),
        'timestamp': parser.parse(p_item.get('created_at')),
        'desc' : diigo_make_desc( p_item )
    }
    return out

def fetch_bookmarks( start, count ):
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

def create_slug(title):
   return slugify(title).replace("-", " ")[:80]

def create_file_name(bookmark):
    out = os.path.join( target_dir, get_created_date(bookmark).strftime('%Y%m%d%H%M%S') + " - " + create_slug(bookmark.get('title')) + ".org" )
    return out

# * [[title][url]] :tags:
#:PROPERTIES:
#:CREATED:
#:END:
# desc
#
def get_created_date(bookmark):
    return parser.parse(bookmark.get('created_at'))

def convert_to_org_timestamp(time_str):
    return time_str.strftime('[%Y-%m-%d %a %H:%M:%S]')

def create_bookmark_org_file(bookmark):
    ""
    file_name = create_file_name(bookmark)
    with open(file_name, "w") as file:
        file.write(f'* [[{bookmark.get("title")}][{bookmark.get("url")}]]')

        # TAGS
        if bookmark.get("tags") != "no_tag":
            file.write("\t:")
            file.writelines(bookmark.get("tags").replace(',',':'))
            file.write(":\n")

        # PROPERTY DRAWER
        file.write(':PROPERTIES:\n')
        file.write(f':CREATED: {convert_to_org_timestamp(get_created_date(bookmark))}\n')
        file.write(":END:\n")


#--------------------------------------------------------------------------------------------------------
#
sys.stdout.write( "Fetching bookmarks..." )


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

target_dir = "."
start = 0

remote_bookmarks = []
while bookmarks_tranche := fetch_bookmarks(start=start, count=count):
    if bookmarks_tranche:
        for b in bookmarks_tranche:
            logging.info( f'Recieving -- {b.get("url")}' )
        remote_bookmarks += bookmarks_tranche
        start += 100


# read all local bookmarks into lobj (orgparse)
#
#if not PULL
#for each item in lobj
#   new = update > synctime
#   matched = item in robj exists
#
#   if not new and matched
#       continue
#
#   conflict = new and matched and remote item is new
#   real_conflict = conflict and items different except for update time
#
#   add = new and not matched
#   merge = new and not real_conflict
#   delete = not new and not matched
#
#if not PUSH
#for each item in robj
#   new = update > synctime
#   matched = item in lobj exists
#
#   if not new and matched
#       continue
#
#   conflict = new and matched and local item new
#   real_conflict = conflict and items !=
#
#   write = new and not real_conflict
#   delete = not new and not matched



for bookmark in remote_bookmarks:
    create_bookmark_org_file(bookmark)

#
#write down sync time
#


sys.stdout.write( "done!\n" )

sys.stdout.write( f'{len(remote_bookmarks)} bookmarks fetched.\n' )

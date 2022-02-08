# diigorg
Sync back and forth between diigo and org mode

0. you'll need python 3.10+ and all of the packages it will complain that you're missing when you first try to run it.
1. create a bookmarks directory, e.g. "bookmarks"
2. run diigorg `python3.10 /path/to/diigorg.py
3. diigorg will have created diigorg.cfg. At a minimum, you will need to insert your diigo username, diigo password, and diigo api key.
4. run diigorg again.
5. ...profit.

some notes:
- diigorg only touches the first heading in the org file, which is the bookmark, its metadata, and annotations and comments. 
Any other headings in the file (such as the default `notes` heading, are untouched and can be written in without worrying about them being erased if changes are brought down from diigo.
However, if the bookmark is deleted on diigo.com, then the whole org file will be marked for deletion.

- the diigo api does not allow for the modification of annotations or comments so those are read only.

- because the updated timestamp on diigo bookmarks is not updated when tags, read later, or privacy states are changed on diigo.com, diigorg has no way to detect that these have changed or compare them to local changes.
if you make these changes on diigo.com, you'll want to do a --full-sync to bring them down.

- diigorg always asks for confirmations before committing changes, but if you're super nervous, you can run with --safe, which prevents any changes from actually being sent to diigo.com

- --reset will try to wipe the local dir and redownload everything. this is safe to do unless you've entered notes into your org files, since those aren't uploaded in any way.

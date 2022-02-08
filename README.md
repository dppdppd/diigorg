# diigorg
Sync back and forth between diigo and org mode

0. You'll need python 3.10+ and all of the packages it will complain that you're missing when you first try to run it.
1. Create a bookmarks directory, e.g. "bookmarks"
2. Run diigorg `python3.10 /path/to/diigorg.py` in the bookmarks directory
3. Diigorg will have not done anything other than create `diigorg.cfg`.
4. Edit `diigorg.cfg` and insert your diigo username, diigo password, and diigo api key.
5. Run diigorg again to download all of your bookmarks.
6. ...Profit.

Some notes:

Diigorg only touches the first heading in the org file, which is the bookmark, its metadata, annotations and comments. 
Any other headings in the file (such as the default "* notes" heading, can be written to without worrying about them being cleared when/if changes are made to the bookmark on diigo.com.

The cfg file allows you to specify which metadata you want at the file level (e.g. #+FILETAGS) and which metadata you want at the heading level (e.g. :roam_refs:/url/) so you can match your org-roam convention

The diigo api does not support pushing changes to annotations or comments, so any changes to the local org file will not get pushed up to diigo.com.
Best to use the diigo.com annotation tool for that.

Because the updated timestamp on diigo bookmarks is not updated when tags, read later, or privacy states are changed on diigo.com, diigorg has no way to detect that these have changed or know whether they conflict with local changes.
If you make these changes on diigo.com, you'll want to do a --full-sync to bring them down.

Diigorg always asks for confirmations before committing changes, but if you're super nervous, you can run with --safe, which prevents any changes from actually being sent to diigo.com

--reset will try to wipe the local dir and redownload everything. this is safe to do unless you've entered notes into your org files, since those aren't uploaded in any way.

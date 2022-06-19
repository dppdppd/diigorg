# diigorg
Sync back and forth between Diigo.com and org mode files

0. You'll need python 3.10+ and pip
1. `gh repo clone dppdppd/diigorg`
2. `pip install -r requirements.txt`
3. Create a bookmarks directory, e.g. "bookmarks"
4. Run diigorg `python3.10 /path/to/diigorg.py` in the bookmarks directory
5. Diigorg will have not done anything other than create `diigorg.cfg`.
6. Edit `diigorg.cfg` and insert your diigo username, diigo password, and diigo api key.
7. Run diigorg again to download all of your bookmarks.
8. ...Profit.

Some notes:

The following changes on Diigo.com trigger an update to their updated_time timestamp, which means that incremental (normal) syncs will catche them:
- changes to description.
- changes to title.
- changes to url.
- addition of annotiations or comments.

The following changes on Diigo.com do not result in an update to their updated_time timestamp and will not be caught in and of themselves:
- deletion of annotations or comments.
- changes to tags.
- changes to readlater state.
If you made any of these changes, you should run diigorg with --full-sync.

If you don't have many bookmarks and/or don't mind waiting, it's safe to do a --full-sync with every sync.

Diigorg uses the org file modified time and compares it to the last sync time to determine what files need to be sunc to diigo.com.

Diigorg only touches the first heading in the org file, which is the bookmark, its metadata, annotations and comments. 
Any other headings in the file can be written to without worrying about them being cleared when/if changes are made to the bookmark on diigo.com.

The cfg file allows you to specify which metadata you want at the file level (e.g. #+FILETAGS) and which metadata you want at the heading level (e.g. :roam_refs:/url/) so you can match your org-roam convention

The diigo api does not support updating or deleting annotations or comments, so any changes to those in the local org file will not get pushed up to diigo.com and will get rewritten if any other changes on the Diigo.com version of the bookmark need to be brought down. So it's best to use the diigo.com annotation tool for editing annotations and/pr comments.


Diigorg usually asks for confirmations before committing changes, but if you're super nervous, you can run with --safe, which prevents any changes from actually being sent to Diigo.com. It will write to local files, so you should git them or back them up.

There'll be bugs. Back up your files.

![Screenshot 2022-02-07 230447](https://user-images.githubusercontent.com/1166577/152935455-cc69c736-c3ab-487f-8c70-214b35d4ba39.png)


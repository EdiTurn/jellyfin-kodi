# -*- coding: utf-8 -*-

#################################################################################################

import datetime
import logging
import json
import os
import sqlite3

import xbmc
import xbmcvfs

import emby_db
from helper.utils import delete_folder
from helper import _, settings, window, dialog

#################################################################################################

LOG = logging.getLogger("EMBY."+__name__)

#################################################################################################

try:
    from objects import obj
except Exception as error:
    # clear patch
    LOG.exception(error)
    delete_folder()
    dialog("ok", heading="{emby}", line1=_(33155))
    xbmc.executebuiltin('RestartApp')


class Database(object):

    ''' This should be called like a context.
        i.e. with Database('emby') as db:
            db.cursor
            db.conn.commit()
    '''
    timeout = 120

    def __init__(self, file=None, commit_close=True):

        ''' file: emby, texture, music, video, :memory: or path to file
        '''
        self.db_file = file or "video"
        self.commit_close = commit_close

    def __enter__(self):

        ''' Open the connection and return the Database class.
            This is to allow for both the cursor and conn to be accessible.
            at any time.
        '''
        self.conn = sqlite3.connect(self._sql(self.db_file), timeout=self.timeout)
        self.cursor = self.conn.cursor()

        if self.db_file in ('video', 'music', 'texture'):
            self.conn.execute("PRAGMA journal_mode=WAL")

        LOG.debug("--->[ database: %s ] %s", self.db_file, id(self.conn))

        if not window('emby_db_check.bool') and self.db_file == 'emby':

            window('emby_db_check.bool', True)
            emby_tables(self.cursor)
            self.conn.commit()

        return self

    def _sql(self, file):

        databases = obj.Objects().objects

        return xbmc.translatePath(databases[file]).decode('utf-8') if file in databases else file

    def __exit__(self, exc_type, exc_val, exc_tb):

        ''' Close the connection and cursor.
        '''
        changes = self.conn.total_changes

        if exc_type is not None: # errors raised
            LOG.error("type: %s value: %s", exc_type, exc_val)

        if self.commit_close and changes:

            LOG.info("[%s] %s rows updated.", self.db_file, changes)
            self.conn.commit()

        LOG.debug("---<[ database: %s ] %s", self.db_file, id(self.conn))
        self.cursor.close()
        self.conn.close()

def emby_tables(cursor):

    ''' Create the tables for the emby database.
        emby, view, version
    '''
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS emby(
        emby_id TEXT UNIQUE, media_folder TEXT, emby_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER, emby_parent_id TEXT)""")
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS view(
        view_id TEXT UNIQUE, view_name TEXT, media_type TEXT)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS version(idVersion TEXT)")

    columns = cursor.execute("SELECT * FROM emby")
    if 'emby_parent_id' not in [description[0] for description in columns.description]:
        
        LOG.info("Add missing column emby_parent_id")
        cursor.execute("ALTER TABLE emby ADD COLUMN emby_parent_id 'TEXT'")

def reset():

    ''' Reset both the emby database and the kodi database.
    '''
    from views import Views
    views = Views()

    if not dialog("yesno", heading="{emby}", line1=_(33074)):
        return

    window('emby_should_stop.bool', True)
    count = 10

    while window('emby_sync.bool'):

        LOG.info("Sync is running...")
        count -= 1

        if not count:
            dialog("ok", heading="{emby}", line1=_(33085))

            return

        if xbmc.Monitor().waitForAbort(1):
            return

    reset_kodi()
    reset_emby()
    views.delete_playlists()
    views.delete_nodes()

    if dialog("yesno", heading="{emby}", line1=_(33086)):
        reset_artwork()

    addon_data = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/").decode('utf-8')

    if dialog("yesno", heading="{emby}", line1=_(33087)):

        xbmcvfs.delete(os.path.join(addon_data, "settings.xml"))
        xbmcvfs.delete(os.path.join(addon_data, "data.json"))
        LOG.info("[ reset settings ]")

    if xbmcvfs.exists(os.path.join(addon_data, "sync.json")):
        xbmcvfs.delete(os.path.join(addon_data, "sync.json"))

    settings('enableMusic.bool', False)
    settings('MinimumSetup.bool', False)
    settings('MusicRescan.bool', False)
    settings('SyncInstallRunDone.bool', False)
    dialog("ok", heading="{emby}", line1=_(33088))
    xbmc.executebuiltin('RestartApp')

def reset_kodi():

    with Database() as videodb:
        videodb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in videodb.cursor.fetchall():
            name = table[0]

            if name != 'version':
                videodb.cursor.execute("DELETE FROM " + name)

    if settings('enableMusic.bool') or dialog("yesno", heading="{emby}", line1=_(33162)):

        with Database('music') as musicdb:
            musicdb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

            for table in musicdb.cursor.fetchall():
                name = table[0]

                if name != 'version':
                    musicdb.cursor.execute("DELETE FROM " + name)

    LOG.warn("[ reset kodi ]")

def reset_emby():
    
    with Database('emby') as embydb:    
        embydb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in embydb.cursor.fetchall():
            name = table[0]

            if name not in ('version', 'view'):
                embydb.cursor.execute("DELETE FROM " + name)

            embydb.cursor.execute("DROP table IF EXISTS emby")
            embydb.cursor.execute("DROP table IF EXISTS view")
            embydb.cursor.execute("DROP table IF EXISTS version")

    LOG.warn("[ reset emby ]")

def reset_artwork():

    ''' Remove all existing texture.
    '''
    thumbnails = xbmc.translatePath('special://thumbnails/').decode('utf-8')

    if xbmcvfs.exists(thumbnails):
        dirs, ignore = xbmcvfs.listdir(thumbnails)

        for directory in dirs:
            ignore, thumbs = xbmcvfs.listdir(os.path.join(thumbnails, directory.decode('utf-8')))

            for thumb in thumbs:
                LOG.debug("DELETE thumbnail %s", thumb)
                xbmcvfs.delete(os.path.join(thumbnails, directory.decode('utf-8'), thumb.decode('utf-8')))

    with Database('texture') as texdb:
        texdb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in texdb.cursor.fetchall():
            name = table[0]

            if name != 'version':
                texdb.cursor.execute("DELETE FROM " + name)

    LOG.warn("[ reset artwork ]")

def get_sync():

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    try:
        with open(os.path.join(path, 'sync.json')) as infile:
            sync = json.load(infile)
    except Exception:
        sync = {}

    sync['Libraries'] = sync.get('Libraries', [])
    sync['RestorePoint'] = sync.get('RestorePoint', {})
    sync['Whitelist'] = list(set(sync.get('Whitelist', [])))
    sync['SortedViews'] = sync.get('SortedViews', [])

    return sync

def save_sync(sync):

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    sync['Date'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    with open(os.path.join(path, 'sync.json'), 'w') as outfile:
        json.dump(sync, outfile, sort_keys=True, indent=4, ensure_ascii=False)

def get_credentials():

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    try:
        with open(os.path.join(path, 'data.json')) as infile:
            credentials = json.load(infile)
    except Exception:
        credentials = {}

    credentials['Servers'] = credentials.get('Servers', [])

    return credentials

def save_credentials(credentials):

    credentials = credentials or {}
    path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    with open(os.path.join(path, 'data.json'), 'w') as outfile:
        json.dump(credentials, outfile, sort_keys=True, indent=4, ensure_ascii=False)

def get_item(kodi_id, media):

    ''' Get emby item based on kodi id and media.
    '''
    with Database('emby') as embydb:
        item = emby_db.EmbyDatabase(embydb.cursor).get_full_item_by_kodi_id(kodi_id, media)

        if not item:
            LOG.debug("Not an emby item")

            return

    return item

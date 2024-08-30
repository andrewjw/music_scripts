#!/usr/bin/python

import glob
import math
import mutagen
import os.path
from PIL import Image
import subprocess
import sys

HQ_ROOT = "/mnt/nfs/music_hq/"
CONVERT_ROOT = "/mnt/nfs/music/"

GLOB_UNSAFE = {"(", ")", "[", "]", "'", '"', "-", "–", ","}

def strip_path(path, names):
    return {n[len(path):].replace("’", "'").replace("-", "–") for n in names if not n.endswith("@eaDir")}

def strip_type(files):
    return {".".join(fn.split(".")[:-1]) for fn in files}

def glob_escape(path):
    for unsafe in GLOB_UNSAFE:
        path = path.replace(unsafe, "?")
    return path

def quote(s):
    return s.replace("'", "\\'").replace('"', '\\"')

def main(path_filter, commit):
    hq_artists = strip_path(HQ_ROOT, (glob.glob(HQ_ROOT + "*")))

    hq_artists = {a for a in hq_artists if a.startswith(path_filter.split("/")[0])}

    if "musiclibrary.blb" in hq_artists:
        hq_artists.remove("musiclibrary.blb")
    if "Playlists" in hq_artists:
        hq_artists.remove("Playlists")

    release_dates = {}

    for name in sorted(hq_artists):
        process_artist(name, commit)

    print(release_dates)

def process_artist(artist_name, commit, release_dates):
    path = "/%s/" % (artist_name, )
    hq_albums = strip_path(HQ_ROOT + path, (glob.glob(HQ_ROOT + path + "*")))

    for album in hq_albums:
        if os.path.isdir(f"{HQ_ROOT}{path}/{album}"):
            process_album(artist_name, album, commit, release_dates)

def process_album(artist_name, album_name, commit, release_dates):
    path = "/%s/%s/" % (artist_name, album_name)
    hq_tracks = strip_type(strip_path(HQ_ROOT + path, (glob.glob(HQ_ROOT + path + "*"))))

    if "folder" in hq_tracks:
        hq_tracks.remove("folder")

    disc_count = get_disc_count(artist_name, album_name)
    if disc_count is not None and disc_count > 1:
        for disc in range(disc_count):
            hq_playlist_path = os.path.join(os.path.join(HQ_ROOT, "Playlists", artist_name, artist_name + " - " + album_name + f" Disc {disc+1}.m3u"))
            convert_playlist_path = os.path.join(os.path.join(CONVERT_ROOT, "Playlists", artist_name, artist_name + " - " + album_name + f" Disc {disc+1}.m3u"))

            hq_playlist, convert_playlist = get_disc_m3u(artist_name, album_name, disc+1)
            if hq_playlist is None:
                if os.path.exists(hq_playlist_path):
                    if commit:
                        os.remove(hq_playlist_path)
                    else:
                        print(f"Would remove playlist {hq_playlist_path}")
                if os.path.exists(convert_playlist_path):
                    if commit:
                        os.remove(convert_playlist_path)
                    else:
                        print(f"Would remove playlist {convert_playlist_path}")
                continue

            if commit:
                try:
                   os.makedirs(os.path.join(HQ_ROOT, "Playlists", artist_name))
                except FileExistsError:
                    pass
                try:
                    os.makedirs(os.path.join(CONVERT_ROOT, "Playlists", artist_name))
                except FileExistsError:
                    pass

            if not os.path.exists(hq_playlist) or open(hq_playlist_path).read() != hq_playlist:
                if commit:
                    open(hq_playlist_path, "w").write(hq_playlist)
                else:
                    print(f"Would create playlist {hq_playlist_path}")

            if not os.path.exists(convert_playlist) or open(convert_playlist_path).read() != convert_playlist:
                if commit:
                    open(convert_playlist_path, "w").write(convert_playlist)
                else:
                    print(f"Would create playlist {convert_playlist_path}")

    for tracks in hq_tracks:
        music = mutagen.File(fn)
        if music is None:
            raise ValueError(f"Unable to load file {fn}")
        year, month, day = None, None, None
        if "originaldate" in music and music["originaldate"] is not None:
            year = int(music["originaldate"].split("-")[0])
            month = int(music["originaldate"].split("-")[0])
        elif "date" in music and music["date"] is not None:
            year = int(music["date"].split("-")[0])
            month = int(music["date"].split("-")[0])

        if year is None or month is None:
            continue

        if year not in release_dates:
            release_dates[year] = {}
        if month not in release_dates[year]:
            release_dates[year][month] = []
        release_dates[year][month].append(fn)

IGNORE_FILES = {"folder", "cover", "@eaDir", "Thumbs"}

def get_disc_count(artist_name, album_name):
    path = "%s/%s/%s/*" % (HQ_ROOT , artist_name, album_name)
    for fn in glob.glob(path):
        if any(fn.split("/")[-1].startswith(ignore) for ignore in IGNORE_FILES):
            continue

        music = mutagen.File(fn)
        if music is None:
            raise ValueError(f"Unable to load file {fn}")
        if "totaldiscs" in music and music["totaldiscs"] is not None:
            return int(music["totaldiscs"][0])
    return 1

def get_disc_files(artist_name, album_name, disc_number):
    path = "/%s/%s/*" % (artist_name, album_name)

    file_list = []
    for fn in glob.glob(HQ_ROOT + path):
        if fn.split("/")[-1].startswith("folder") or fn.split("/")[-1].startswith("cover") or fn.split("/")[-1].startswith("@eaDir") or fn.split("/")[-1].startswith("Thumbs.db"):
            continue
        music = mutagen.File(fn)
        disc = int(music["disc"][0]) if music is not None and "disc" in music and music["disc"] is not None and len(music["disc"]) > 0 else 1
        if disc == disc_number:
            tracknumber = int(music["tracknumber"][0]) if music is not None and "tracknumber" in music and music["tracknumber"] is not None and len(music["tracknumber"]) > 0 else int(fn.split("/")[-1].split(" ")[0])
            file_list.append((tracknumber, fn))
    return [f[1] for f in sorted(file_list, key=lambda x: x[0])]

def get_disc_m3u(artist_name, album_name, disc_number):
    files = get_disc_files(artist_name, album_name, disc_number)
    if len(files) == 0:
        return None, None
    hq_contents = "#EXTM3U\n"
    convert_contents = "#EXTM3U\n"
    for fn in get_disc_files(artist_name, album_name, disc_number):
        hq_contents += "../.." + fn[len(HQ_ROOT):] + "\n"
        convert_contents += "../.." + ".".join(fn[len(HQ_ROOT):].split(".")[:-1]) + ".mp3\n"
    return hq_contents, convert_contents

if __name__ == "__main__":
    main("" if len(sys.argv) == 1 or sys.argv[1] == "--commit" else sys.argv[1], "--commit" in sys.argv[1])

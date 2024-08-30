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

def main(path_filter, execute):
    hq_artists = strip_path(HQ_ROOT, (glob.glob(HQ_ROOT + "*")))
    convert_artists = strip_path(CONVERT_ROOT, (glob.glob(CONVERT_ROOT + "*")))

    hq_artists = {a for a in hq_artists if a.startswith(path_filter.split("/")[0])}
    convert_artists = {a for a in convert_artists if a.startswith(path_filter.split("/")[0])}

    if "musiclibrary.blb" in hq_artists:
        hq_artists.remove("musiclibrary.blb")

    for name in sorted(hq_artists - convert_artists):
        print("Missing: ", name)

    for name in sorted(convert_artists - hq_artists):
        print("Extra: ", name)

    for name in sorted(hq_artists):
        compare_artist(name, execute)

def compare_artist(artist_name, execute):
    path = "/%s/" % (artist_name, )
    hq_albums = strip_path(HQ_ROOT + path, (glob.glob(HQ_ROOT + path + "*")))
    convert_albums = strip_path(CONVERT_ROOT + path, (glob.glob(CONVERT_ROOT + path + "*")))

    title = False
    for name in sorted(hq_albums - convert_albums):
        if not title:
            title = True
            print()
            print(artist_name)
        print("Missing: ", name)

    for name in sorted(convert_albums - hq_albums):
        if not title:
            title = True
            print()
            print(artist_name)
        print("Extra: ", name)

    for album in hq_albums & convert_albums:
        if os.path.isdir(f"{HQ_ROOT}{path}/{album}"):
            compare_album(artist_name, album, execute)

def compare_album(artist_name, album_name, execute):
    path = "/%s/%s/" % (artist_name, album_name)
    hq_tracks = strip_type(strip_path(HQ_ROOT + path, (glob.glob(HQ_ROOT + path + "*"))))
    convert_tracks = strip_type(strip_path(CONVERT_ROOT + path, (glob.glob(CONVERT_ROOT + path + "*"))))

    title = False
    if "folder" in hq_tracks:
        title = check_folder_cover_art(artist_name, album_name, execute)
        hq_tracks.remove("folder")

    for name in sorted(hq_tracks - convert_tracks):
        if not title:
            title = True
            print()
            print(artist_name, "/", album_name)
        print("Missing: ", name)

        if name.lower() == "thumbs" and os.path.exists(f"{HQ_ROOT}{artist_name}/{album_name}/{name}.db"):
            execute(f"rm \"{HQ_ROOT}/{artist_name}/{album_name}/{name}.db\"")

    if len(hq_tracks - convert_tracks) > 0:
        execute(f"beet convert -y {artist_name} {album_name}")

    for name in sorted(convert_tracks - hq_tracks):
        if not title:
            title = True
            print()
            print(artist_name, "/", album_name)
        print("Extra: ", name)

        if name.lower() == "thumbs" and os.path.exists(f"{CONVERT_ROOT}{artist_name}/{album_name}/{name}.db"):
            execute(f"rm \"{CONVERT_ROOT}/{artist_name}/{album_name}/{name}.db\"")

    for name in hq_tracks & convert_tracks:
        faults = check_track(artist_name, album_name, name, execute)
        if len(faults) > 0:
            if not title:
                title = True
                print()
                print(artist_name, "/", album_name)
            for f in faults:
                print(f)

    if title:
        print()

def check_track(artist_name, album_name, track, execute):
    faults = []
    path = glob_escape(f"{artist_name}/{album_name}/{track}*")
    hq_track = glob.glob(HQ_ROOT + path)[0]
    convert_track = glob.glob(CONVERT_ROOT + path)[0]
    hq_mtime = os.path.getmtime(hq_track)
    convert_mtime = os.path.getmtime(convert_track)

    if hq_mtime > convert_mtime:
        faults.append(f"Outdated: {track}")
        execute(f"rm \"{convert_track}\"")
        execute(f"beet convert -y {artist_name} {album_name}")

    if ".flac" in hq_track:
        soxi = subprocess.run(["soxi", hq_track], capture_output=True)
        bitrate = [line for line in soxi.stdout.decode("utf8").split("\n") if "Bit Rate" in line][0]
        bitrate = bitrate.split(":")[1].strip()

        if (bitrate[-1] == "M" and float(bitrate[:-1]) >= 1.11) or (bitrate[-1] == "k" and int(bitrate[:-1]) >= 1110):
            faults.append(f"Bit Rate too high: {hq_track} - {bitrate}")
        elif bitrate[-1] not in ("M", "k"):
            assert False, (hq_track, bitrate)
    return faults

def check_folder_cover_art(artist_name, album_name, execute):
    path = "/%s/%s/folder*" % (artist_name, album_name)
    cover_art = glob.glob(HQ_ROOT + path)[0]

    img = Image.open(cover_art)
    width, height = img.size
    if width > 1024 or height > 1024:
        print()
        print(artist_name, "/", album_name)
        print(f"Cover art: Too big. {width}x{height}")
        execute(f"beet fetchart -f {artist_name} {album_name}")
        return True
    return False

IGNORE_FILES = {"folder", "cover", "@eaDir", "Thumbs"}

if __name__ == "__main__":
    main("" if len(sys.argv) == 1 or sys.argv[1] == "--commit" else sys.argv[1], os.system if "--commit" in sys.argv else print)

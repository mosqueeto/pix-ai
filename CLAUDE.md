# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**pix** is a self-contained web photo gallery: pure JS/HTML/CSS frontend
plus Perl initialization scripts.  No framework, no database.

## Files

| File | Role |
|------|------|
| `pix-init.pl` | CLI + CGI-callable init script; scans photos, calls ImageMagick, writes `_pix/index.json` |
| `pix-init.cgi` | Web entry point; detects state (idle/running/done/error), double-forks `pix-init.pl` in background, serves polling UI |
| `index.html` | Static gallery shell; loads `pix.js` and `pix.css` |
| `pix.js` | All gallery logic: fetch index.json, hash-based routing, grid renderer, lightbox |
| `pix.css` | Dark-theme styles; CSS custom properties in `:root` |

## Generated structure (not committed)

    _pix/
      index.json      photo tree (see schema below)
      log.txt         written by pix-init.pl; tailed by pix-init.cgi?action=status
      .running        sentinel: exists while init is in progress
      thumb/          150 px JPEG thumbnails, mirroring source tree
      medium/         800 px JPEG
      large/          1600 px JPEG

## index.json schema

    { version, generated, tree: DirNode }

    DirNode  { name, path, cover, dirs: [DirNode], photos: [PhotoNode] }
    PhotoNode{ name, path, w, h, bytes, mtime }

`path` is always relative to the gallery root with `/` separators.
`cover` on a DirNode is the `_pix/medium/…` path of the first photo in that subtree.

## URL convention in pix.js

Generated sizes are always JPEG.  The JS derives their URLs:

    thumbUrl(p)  →  _pix/thumb/  + p.path with extension replaced by .jpg
    mediumUrl(p) →  _pix/medium/ + …
    largeUrl(p)  →  _pix/large/  + …
    origUrl(p)   →  p.path  (original file, kept as-is)

## ImageMagick flags

    convert -auto-orient -strip -resize NxN> -quality Q input output

`-auto-orient` corrects EXIF rotation.  `>` means shrink-only.
`-strip` removes metadata from generated sizes (originals untouched).

## CGI state machine (pix-init.cgi)

State is derived from filesystem:

    index.json exists               → done
    .running exists                 → running
    log.txt exists but not .running → error (previous run failed)
    none of the above               → idle

The double-fork pattern (fork→fork→exec) detaches the worker from the
web server process group so it survives CGI process exit.

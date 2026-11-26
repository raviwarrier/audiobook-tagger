import os
import re
import sys
import shutil
import json
import argparse
import urllib.parse
from datetime import datetime, timezone
import tkinter as tk
from tkinter import filedialog
import requests
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import (
    ID3, TIT2, TIT3, TALB, TPE1, TPE2, TPUB, TDRC,
    TCON, COMM, APIC, TXXX, ID3NoHeaderError
)

REGION_MAP = {
    "us": ".com",
    "ca": ".ca",
    "uk": ".co.uk",
    "au": ".com.au",
    "fr": ".fr",
    "de": ".de",
    "jp": ".co.jp",
    "it": ".it",
    "in": ".in",
    "es": ".es",
}


def sanitize_filename(name: str) -> str:
    """Replaces colons with ' -' and strips characters invalid in Windows file/folder paths."""
    if not name:
        return "Unknown"
    name = name.replace(":", " -")
    name = re.sub(r'[<>"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.rstrip(". ")


def normalize_for_comparison(text: str) -> str:
    """Strips subtitles, punctuation, and extra spaces for title/author comparison."""
    if not text:
        return ""
    base = text.split(":")[0].split("(")[0]
    base = re.sub(r"[^\w\s]", "", base.lower())
    return re.sub(r"\s+", " ", base).strip()


def is_title_match(searched_title: str, found_title: str) -> bool:
    """Verifies whether the returned book title reasonably matches the searched title."""
    norm_search = normalize_for_comparison(searched_title)
    norm_found = normalize_for_comparison(found_title)

    if not norm_search or not norm_found:
        return False

    if norm_search == norm_found or norm_search in norm_found or norm_found in norm_search:
        return True

    search_words = [w for w in norm_search.split() if len(w) > 2]
    if not search_words:
        search_words = norm_search.split()

    found_words = set(norm_found.split())
    matches = sum(1 for w in search_words if w in found_words)
    return (matches / len(search_words)) >= 0.8


def is_author_match(searched_author: str | None, found_author: str | None) -> bool:
    """Checks if at least one significant word from searched_author appears in found_author."""
    if not searched_author or not searched_author.strip():
        return True
    if not found_author:
        return False
    s_words = [w for w in normalize_for_comparison(searched_author).split() if len(w) > 2]
    if not s_words:
        s_words = normalize_for_comparison(searched_author).split()
    f_norm = normalize_for_comparison(found_author)
    return any(w in f_norm for w in s_words)


def clean_series_sequence(sequence: str) -> str:
    """Normalizes sequence formatting from Audible (e.g. 'Book 1' -> '1')."""
    if not sequence:
        return ""
    match = re.search(r"\.\d+|\d+(?:\.\d+)?", str(sequence))
    return match.group(0) if match else str(sequence)


def clean_result(item: dict) -> dict:
    """Standardizes raw Audnex metadata into the cleaned book structure."""
    if not item:
        return {}

    series = []
    series_primary = item.get("seriesPrimary")
    if isinstance(series_primary, dict) and series_primary.get("name"):
        series.append({
            "series": series_primary["name"],
            "sequence": clean_series_sequence(series_primary.get("position", "")),
        })

    series_secondary = item.get("seriesSecondary")
    if isinstance(series_secondary, dict) and series_secondary.get("name"):
        series.append({
            "series": series_secondary["name"],
            "sequence": clean_series_sequence(series_secondary.get("position", "")),
        })

    genres_raw = item.get("genres") or []
    genres_cleaned = list(dict.fromkeys(
        g["name"] for g in genres_raw if isinstance(g, dict) and g.get("type") == "genre" and g.get("name")
    ))

    authors = item.get("authors") or []
    narrators = item.get("narrators") or []
    release_date = item.get("releaseDate")
    pub_year = release_date.split("-")[0][:4] if isinstance(release_date, str) and release_date else None

    raw_summary = item.get("summary") or ""
    clean_summary = re.sub(r"<[^>]+>", "", raw_summary).strip() or None

    return {
        "title": item.get("title") or "",
        "subtitle": item.get("subtitle") or None,
        "author": ", ".join(a["name"] for a in authors if isinstance(a, dict) and a.get("name")) or None,
        "narrator": ", ".join(n["name"] for n in narrators if isinstance(n, dict) and n.get("name")) or None,
        "publisher": item.get("publisherName") or None,
        "publishedYear": pub_year,
        "description": clean_summary,
        "cover": item.get("image") or None,
        "asin": item.get("asin") or None,
        "isbn": item.get("isbn") or None,
        "genres": genres_cleaned or None,
        "series": series or None,
    }


def fetch_book_details(title: str, author: str = None, region: str = "us", timeout: int = 10) -> list:
    """Searches Audible Catalog, enriches via Audnex, and falls back to OpenLibrary if no match is found."""
    if not title or not title.strip():
        return []

    tld = REGION_MAP.get(region.lower().strip(), ".com")
    all_results = []
    products = []

    # 1. Primary Audible Catalog Search (title + optional author)
    try:
        params = {
            "num_results": "10",
            "products_sort_by": "Relevance",
            "title": title.strip(),
        }
        if author and author.strip():
            params["author"] = author.strip()

        resp = requests.get(f"https://api.audible{tld}/1.0/catalog/products", params=params, timeout=timeout)
        if resp.status_code == 200:
            products = resp.json().get("products") or []
    except Exception:
        pass

    # 2. Fallback 1: Audible Keyword Search
    if not products:
        try:
            kw_params = {
                "num_results": "10",
                "products_sort_by": "Relevance",
                "keywords": f"{title} {author or ''}".strip(),
            }
            resp = requests.get(f"https://api.audible{tld}/1.0/catalog/products", params=kw_params, timeout=timeout)
            if resp.status_code == 200:
                products = resp.json().get("products") or []
        except Exception:
            pass

    # 3. Enrich ASINs via Audnex
    if products:
        for prod in products[:8]:
            asin = prod.get("asin")
            if not asin:
                continue
            try:
                audnex_url = f"https://api.audnex.us/books/{urllib.parse.quote(asin.upper())}?region={urllib.parse.quote(region)}"
                ax_resp = requests.get(audnex_url, timeout=timeout)
                if ax_resp.status_code == 200 and ax_resp.json().get("asin"):
                    cleaned = clean_result(ax_resp.json())
                    if cleaned.get("title"):
                        all_results.append(cleaned)
                        if is_title_match(title, cleaned["title"]) and is_author_match(author, cleaned.get("author")):
                            return all_results
            except Exception:
                continue

    # 4. Fallback 2: OpenLibrary Search (runs if Audible returned nothing OR no verified match)
    try:
        ol_params = {"title": title.strip(), "limit": 5}
        if author and author.strip():
            ol_params["author"] = author.strip()
        ol_resp = requests.get(
            "https://openlibrary.org/search.json",
            params=ol_params,
            headers={"User-Agent": "W-Simple-Media-Tools/1.5.1"},
            timeout=timeout,
        )
        if ol_resp.status_code == 200:
            docs = ol_resp.json().get("docs") or []
            for d in docs:
                cover_url = f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg" if d.get("cover_i") else None
                author_name = d["author_name"][0] if d.get("author_name") else author
                pub_year = str(d["first_publish_year"])[:4] if d.get("first_publish_year") else None
                all_results.append({
                    "title": d.get("title") or title.strip(),
                    "subtitle": d.get("subtitle") or None,
                    "author": author_name,
                    "narrator": None,
                    "publisher": d["publisher"][0] if d.get("publisher") else None,
                    "publishedYear": pub_year,
                    "description": None,
                    "cover": cover_url,
                    "asin": None,
                    "isbn": d["isbn"][0] if d.get("isbn") else None,
                    "genres": d["subject"][:4] if d.get("subject") else None,
                    "series": None,
                })
    except Exception:
        pass

    return all_results


def find_verified_match(results: list, searched_title: str, searched_author: str | None = None) -> dict | None:
    """Returns the first result matching title (and author if provided), or None."""
    for item in results:
        if is_title_match(searched_title, item.get("title", "")) and is_author_match(searched_author, item.get("author")):
            return item
    return None


def download_cover_bytes(cover_url: str) -> bytes | None:
    """Downloads cover image bytes from URL."""
    if not cover_url:
        return None
    try:
        resp = requests.get(cover_url, timeout=15)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def fetch_chapters(asin: str, region: str = "us", timeout: int = 10) -> list | None:
    """Fetch chapter list from Audnexus for a given ASIN."""
    if not asin:
        return None
    try:
        url = f"https://api.audnex.us/books/{urllib.parse.quote(asin.upper())}/chapters?region={urllib.parse.quote(region)}"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            chapters = data.get("chapters")
            if isinstance(chapters, list):
                return chapters
    except Exception:
        pass
    return None


def get_audio_info(filepath: str) -> tuple[int, int]:
    """Return (file_size_bytes, duration_ms) for an audio file."""
    file_size = os.path.getsize(filepath)
    duration_ms = 0
    try:
        if filepath.lower().endswith(".m4b"):
            audio = MP4(filepath)
        else:
            audio = ID3(filepath)
        info = audio.info
        duration_ms = int(getattr(info, "length", 0) * 1000)
    except Exception:
        pass
    return file_size, duration_ms


def save_chapters_json(target_dir: str, filename: str, chapters: list, file_size: int, duration_ms: int) -> str | None:
    """Save chapters.json inside [book]/.audiosilo/ folder."""
    if not chapters:
        return None
    try:
        audiosilo_dir = os.path.join(target_dir, ".audiosilo")
        os.makedirs(audiosilo_dir, exist_ok=True)

        payload = {
            "version": 1,
            "generator": "chapter-sidecar",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "from": "audnexus",
            "files": [
                {
                    "path": filename,
                    "size": file_size,
                    "duration_ms": duration_ms,
                }
            ],
            "chapters": chapters,
        }

        chapters_path = os.path.join(audiosilo_dir, "chapters.json")
        with open(chapters_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return chapters_path
    except Exception:
        return None


def write_m4b_tags(filepath: str, meta: dict, cover_bytes: bytes | None):
    """Writes MP3Tag & Audiobookshelf compatible metadata to M4B/MP4 files."""
    audio = MP4(filepath)
    if audio.tags is None:
        audio.add_tags()

    # Title -> ALBUM & TITLE
    if meta.get("title"):
        audio.tags["\xa9alb"] = [meta["title"]]
        audio.tags["\xa9nam"] = [meta["title"]]

    # Sub Title -> SUBTITLE
    if meta.get("subtitle"):
        audio.tags["----:com.apple.iTunes:SUBTITLE"] = [meta["subtitle"].encode("utf-8")]

    # Author(s) -> ALBUMARTIST & ARTIST
    if meta.get("author"):
        audio.tags["aART"] = [meta["author"]]
        audio.tags["\xa9ART"] = [meta["author"]]

    # Purge ALL existing Composer / Narrator atoms (case-insensitive) to prevent Mp3tag '\\' duplicates
    keys_to_remove = [
        k for k in audio.tags.keys()
        if k in ("\xa9wrt", "\xa9nrt")
        or k.lower().endswith(":composer")
        or k.lower().endswith(":narrator")
    ]
    for k in keys_to_remove:
        audio.tags.pop(k, None)

    if meta.get("narrator"):
        audio.tags["----:com.apple.iTunes:NARRATOR"] = [meta["narrator"].encode("utf-8")]

    # Publisher -> PUBLISHER
    if meta.get("publisher"):
        audio.tags["\xa9pub"] = [meta["publisher"]]
        audio.tags["----:com.apple.iTunes:PUBLISHER"] = [meta["publisher"].encode("utf-8")]

    # Release Date -> YEAR (4-digit year only)
    if meta.get("publishedYear"):
        audio.tags["\xa9day"] = [str(meta["publishedYear"])]

    # Description -> COMMENT
    if meta.get("description"):
        audio.tags["\xa9cmt"] = [meta["description"]]

    # Genre -> GENRE
    if meta.get("genres"):
        audio.tags["\xa9gen"] = [", ".join(meta["genres"])]

    # ASIN & ISBN
    if meta.get("asin"):
        audio.tags["----:com.apple.iTunes:ASIN"] = [meta["asin"].encode("utf-8")]
    if meta.get("isbn"):
        audio.tags["----:com.apple.iTunes:ISBN"] = [meta["isbn"].encode("utf-8")]

    # Series & Sequence
    if meta.get("series"):
        primary = meta["series"][0]
        audio.tags["----:com.apple.iTunes:SERIES"] = [primary["series"].encode("utf-8")]
        if primary.get("sequence"):
            audio.tags["----:com.apple.iTunes:SERIES-PART"] = [primary["sequence"].encode("utf-8")]

    # Front Cover
    if cover_bytes:
        img_format = MP4Cover.FORMAT_PNG if meta.get("cover", "").lower().endswith(".png") else MP4Cover.FORMAT_JPEG
        audio.tags["covr"] = [MP4Cover(cover_bytes, imageformat=img_format)]

    audio.save()


def write_mp3_tags(filepath: str, meta: dict, cover_bytes: bytes | None):
    """Writes MP3Tag & Audiobookshelf compatible ID3v2 tags to MP3 files."""
    try:
        tags = ID3(filepath)
    except ID3NoHeaderError:
        tags = ID3()

    # Title -> ALBUM & TITLE
    if meta.get("title"):
        tags.delall("TALB")
        tags.delall("TIT2")
        tags.add(TALB(encoding=3, text=meta["title"]))
        tags.add(TIT2(encoding=3, text=meta["title"]))

    # Sub Title -> SUBTITLE
    if meta.get("subtitle"):
        tags.delall("TIT3")
        tags.add(TIT3(encoding=3, text=meta["subtitle"]))
        tags.add(TXXX(encoding=3, desc="SUBTITLE", text=meta["subtitle"]))

    # Author(s) -> ALBUMARTIST & ARTIST
    if meta.get("author"):
        tags.delall("TPE2")
        tags.delall("TPE1")
        tags.add(TPE2(encoding=3, text=meta["author"]))
        tags.add(TPE1(encoding=3, text=meta["author"]))

    # Purge ALL existing Composer / Narrator frames (case-insensitive) to prevent Mp3tag '\\' duplicates
    tags.delall("TCOM")
    for frame_id in list(tags.keys()):
        if frame_id.startswith("TXXX:"):
            desc = frame_id.split(":", 1)[1].lower()
            if desc in ("composer", "narrator"):
                tags.delall(frame_id)

    if meta.get("narrator"):
        tags.add(TXXX(encoding=3, desc="NARRATOR", text=meta["narrator"]))

    # Publisher -> PUBLISHER
    if meta.get("publisher"):
        tags.delall("TPUB")
        tags.add(TPUB(encoding=3, text=meta["publisher"]))

    # Release Date -> YEAR (4-digit year only)
    if meta.get("publishedYear"):
        tags.delall("TDRC")
        tags.add(TDRC(encoding=3, text=str(meta["publishedYear"])))

    # Description -> COMMENT
    if meta.get("description"):
        tags.delall("COMM")
        tags.add(COMM(encoding=3, lang="eng", desc="", text=meta["description"]))

    # Genre -> GENRE
    if meta.get("genres"):
        tags.delall("TCON")
        tags.add(TCON(encoding=3, text=", ".join(meta["genres"])))

    # ASIN & ISBN
    if meta.get("asin"):
        tags.add(TXXX(encoding=3, desc="ASIN", text=meta["asin"]))
    if meta.get("isbn"):
        tags.add(TXXX(encoding=3, desc="ISBN", text=meta["isbn"]))

    # Series & Sequence
    if meta.get("series"):
        primary = meta["series"][0]
        tags.add(TXXX(encoding=3, desc="SERIES", text=primary["series"]))
        if primary.get("sequence"):
            tags.add(TXXX(encoding=3, desc="SERIES-PART", text=primary["sequence"]))

    # Front Cover
    if cover_bytes:
        tags.delall("APIC")
        mime = "image/png" if meta.get("cover", "").lower().endswith(".png") else "image/jpeg"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_bytes))

    tags.save(filepath, v2_version=3)


def strip_subtitle_from_title(title: str, subtitle: str | None = None) -> str:
    """Remove subtitle from title for clean folder/file naming."""
    if not title:
        return title
    # Use the parsed subtitle field if available
    if subtitle and subtitle.strip():
        sub = subtitle.strip()
        if sub in title:
            new_title = title.replace(sub, "").strip()
            new_title = re.sub(r"[\s\-:]+$", "", new_title).strip()
            if new_title:
                return new_title
    # Fallback: split on ': ' separator and take the main title part
    if ": " in title:
        candidate = title.split(": ")[0].strip()
        if len(candidate) > 1:
            return candidate
    return title


def organize_file(filepath: str, base_folder: str, meta: dict) -> str:
    """
    Moves and renames the file to:
    [ALBUM] ([YEAR]) - [ALBUMARTIST]\\[ALBUM] - [ALBUMARTIST].ext
    """
    _, ext = os.path.splitext(filepath)
    raw_title = meta.get("title") or "Unknown Title"
    subtitle = meta.get("subtitle")
    album = sanitize_filename(strip_subtitle_from_title(raw_title, subtitle))
    album_artist = sanitize_filename(meta.get("author") or "Unknown Author")
    year = sanitize_filename(meta.get("publishedYear") or "")

    if year and year != "Unknown":
        folder_name = f"{album} ({year}) - {album_artist}"
    else:
        folder_name = f"{album} - {album_artist}"

    new_filename = f"{album} - {album_artist}{ext}"
    target_dir = os.path.join(base_folder, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    target_path = os.path.join(target_dir, new_filename)

    if os.path.abspath(filepath) != os.path.abspath(target_path):
        shutil.move(filepath, target_path)

    return os.path.join(folder_name, new_filename)


def parse_filename(stem: str) -> tuple[str, str | None]:
    """Splits filename stem by ' - ' into two parts."""
    if " - " in stem:
        part1, part2 = stem.split(" - ", 1)
        return part1.strip(), part2.strip()
    return stem.strip(), None


def resolve_args() -> tuple[str, list[str], str]:
    """
    Parses CLI arguments for optional target path and --region flag.
    If no path is provided, opens a GUI folder picker and prompts for region.
    Returns (base_folder_path, list_of_filenames, region).
    """
    parser = argparse.ArgumentParser(description="Fetch audiobook metadata, tag, and organize files.")
    parser.add_argument("target", nargs="?", help="Path to an audiobook file (.mp3/.m4b) or folder")
    parser.add_argument("-r", "--region", default=None, help="Audible region (us, uk, ca, au, in, de, fr, it, es, jp)")
    args = parser.parse_args()

    if args.target:
        target = os.path.abspath(args.target.strip('"'))
        region = (args.region or "us").strip().lower()
        if os.path.isfile(target):
            if target.lower().endswith((".mp3", ".m4b")):
                return os.path.dirname(target), [os.path.basename(target)], region
            raise SystemExit(f"[-] Error: Unsupported file type '{os.path.basename(target)}'. Only .mp3 and .m4b are supported.")
        if os.path.isdir(target):
            files = [
                f for f in os.listdir(target)
                if os.path.isfile(os.path.join(target, f)) and f.lower().endswith((".mp3", ".m4b"))
            ]
            return target, files, region
        raise SystemExit(f"[-] Error: Path not found: {target}")

    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Select Audiobook Folder (Top-Level Only)")
    if not folder:
        raise SystemExit("[-] Error: No folder selected.")

    region = (args.region or input("[?] Audible region [us/uk/ca/au/in/de/fr] (default: us): ").strip() or "us").lower()
    files = [
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith((".mp3", ".m4b"))
    ]
    return folder, files, region


def generate_and_save_report(folder_path: str, succeeded: list[str], failed: list[tuple[str, str]]):
    """Formats the end-of-run summary, displays it on screen, and saves to results-[yyyy-mm-dd].txt."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_filename = f"results-{date_str}.txt"
    report_path = os.path.join(folder_path, report_filename)

    lines = [
        "=" * 60,
        f"AUDIOBOOK TAGGING & ORGANIZATION SUMMARY ({date_str})",
        "=" * 60,
        f"Total Processed : {len(succeeded) + len(failed)}",
        f"Successful      : {len(succeeded)}",
        f"Failed          : {len(failed)}",
        "-" * 60,
    ]

    if failed:
        lines.append("FAILED BOOKS:")
        for idx, (book_name, reason) in enumerate(failed, 1):
            lines.append(f"  {idx}. {book_name}")
            lines.append(f"     Reason: {reason}")
    else:
        lines.append("FAILED BOOKS: None — all books processed successfully!")

    lines.append("=" * 60)
    report_text = "\n".join(lines)

    print("\n" + report_text)

    with open(report_path, mode="w", encoding="utf-8") as f:
        f.write(report_text + "\n")

    print(f"\n[*] Summary report saved to: {report_path}")


def main():
    folder_path, audio_files, region = resolve_args()
    print(f"\n[*] Target directory: {folder_path} (Region: {region})\n")

    if not audio_files:
        print("[-] No .mp3 or .m4b files found.")
        return

    print(f"[*] Processing {len(audio_files)} audiobook file(s).\n")

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for idx, filename in enumerate(audio_files, 1):
        filepath = os.path.join(folder_path, filename)
        stem, ext = os.path.splitext(filename)
        ext_lower = ext.lower()

        print(f"[{idx}/{len(audio_files)}] File: {filename}")
        part1, part2 = parse_filename(stem)

        meta = None
        last_unmatched = None
        current_title = part1

        if part2:
            print(f"    [...] Trying Title='{part1}', Author='{part2}'...")
            results = fetch_book_details(title=part1, author=part2, region=region)
            meta = find_verified_match(results, part1, part2)
            if not meta and results:
                last_unmatched = results[0]

            if not meta:
                print(f"    [...] Swapping -> Trying Title='{part2}', Author='{part1}'...")
                results = fetch_book_details(title=part2, author=part1, region=region)
                meta = find_verified_match(results, part2, part1)
                if meta:
                    current_title = part2
                elif results:
                    last_unmatched = results[0]
        else:
            print(f"    [...] Searching Title='{part1}'...")
            results = fetch_book_details(title=part1, region=region)
            meta = find_verified_match(results, part1)
            if not meta and results:
                last_unmatched = results[0]

        # Interactive fallback if no exact title match was found
        while not meta:
            if last_unmatched:
                print(f"    [!] Top result did not match searched title: '{last_unmatched.get('title')}' by {last_unmatched.get('author')}")
            else:
                print("    [-] No matching metadata found.")

            user_input = input("    --> Enter Author (or 'Title - Author') to retry, or press [Enter] to skip: ").strip()
            if not user_input:
                reason = (
                    f"Title mismatch (top result: '{last_unmatched.get('title')}' by {last_unmatched.get('author')}) — skipped by user"
                    if last_unmatched
                    else "No metadata match found — skipped by user"
                )
                failed.append((filename, reason))
                print("    [s] Skipped file.\n")
                break

            if " - " in user_input:
                search_title, search_author = [x.strip() for x in user_input.split(" - ", 1)]
            else:
                search_title = current_title
                search_author = user_input

            print(f"    [...] Retrying with Title='{search_title}', Author='{search_author}'...")
            results = fetch_book_details(title=search_title, author=search_author, region=region)
            meta = find_verified_match(results, search_title, search_author)
            last_unmatched = results[0] if results and not meta else None

        if not meta:
            continue

        narrator_display = meta.get("narrator") or "N/A"
        print(f"    [+] Matched: '{meta.get('title')}' ({meta.get('publishedYear') or 'N/A'}) by {meta.get('author')} | Narrator: {narrator_display}")

        cover_bytes = download_cover_bytes(meta.get("cover"))
        try:
            if ext_lower == ".m4b":
                write_m4b_tags(filepath, meta, cover_bytes)
            elif ext_lower == ".mp3":
                write_mp3_tags(filepath, meta, cover_bytes)
            print("    [✓] Tags and cover embedded.")

            rel_dest = organize_file(filepath, folder_path, meta)
            print(f"    [→] Organized to: {rel_dest}\n")

            # Fetch and save chapters from Audnexus
            asin = meta.get("asin")
            if asin:
                chapters = fetch_chapters(asin, region)
                if chapters:
                    target_dir = os.path.join(folder_path, os.path.dirname(rel_dest))
                    final_filename = os.path.basename(rel_dest)
                    target_path = os.path.join(target_dir, final_filename)
                    file_size, duration_ms = get_audio_info(target_path)
                    chapters_path = save_chapters_json(
                        target_dir, final_filename, chapters, file_size, duration_ms
                    )
                    if chapters_path:
                        print(f"    [→] Chapters saved to: {os.path.relpath(chapters_path, folder_path)}\n")
            succeeded.append(filename)
        except Exception as e:
            print(f"    [!] Failed to tag/organize file: {e}\n")
            failed.append((filename, f"File tagging/organization error: {e}"))

    generate_and_save_report(folder_path, succeeded, failed)


if __name__ == "__main__":
    main()
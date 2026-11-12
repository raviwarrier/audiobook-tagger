# Audiobook Tagger

A lightweight Python utility to automatically fetch audiobook metadata, embed tags and cover art, and organize local `.mp3` and `.m4b` files into a clean folder structure.

## What It Does

* **Metadata & Cover Art Fetching:** Scans a top-level directory for `.mp3` and `.m4b` files, queries Audible, Audnex, and Open Library based on the filename (`[Title] - [Author]` or `[Author] - [Title]`), verifies title matches, and prompts you if manual input is needed.
* **MP3Tag & Audiobookshelf Compatible Tagging:** Embeds `ALBUM`, `TITLE`, `SUBTITLE`, `ALBUMARTIST`, `ARTIST`, `COMPOSER` (Narrator), `PUBLISHER`, `YEAR`, `COMMENT` (Description), `GENRE`, `SERIES`, `SERIES-PART`, `ASIN`, `ISBN`, and cover art.
* **Automatic Organization:** Moves and renames tagged files into `[ALBUM] ([YEAR]) - [ALBUMARTIST]/[ALBUM] - [ALBUMARTIST].ext`.
* **Run Summary Report:** Displays a summary of succeeded and failed files on screen and saves it to `results-YYYY-MM-DD.txt`.

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/raviwarrier/audiobook-tagger.git
   cd audiobook-tagger
   ```

2. **Create and activate a virtual environment:**
   * **Windows:**
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   * **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install requests mutagen
   ```
   *(Note: If you use the GUI folder picker on Linux, make sure `tkinter` is installed via your package manager, e.g., `sudo apt install python3-tk`.)*

## How to Run

* **Windows:**
  ```bash
  python tagger.py
  # Or pass the folder path directly:
  python tagger.py "C:\Path\To\Audiobooks"
  ```

* **Linux / macOS:**
  ```bash
  python3 tagger.py
  # Or pass the folder path directly:
  python3 tagger.py "/path/to/audiobooks"
  ```

## Credits

The Audible and Audnex metadata fetching and normalization logic in this script is derived and adapted from [Audiobookshelf](https://github.com/advplyr/audiobookshelf).

## License

Licensed under the MIT License.
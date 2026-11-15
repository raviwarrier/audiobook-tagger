# Audiobook Tagger

A lightweight Python utility to automatically fetch audiobook metadata, embed tags and cover art, and organize local `.mp3` and `.m4b` files into a clean folder structure.

## What It Does

* **Metadata & Cover Art Fetching:** Processes a single `.mp3`/`.m4b` file or scans a top-level directory, queries Audible, Audnex, and Open Library based on the filename (`[Title] - [Author]` or `[Author] - [Title]`), verifies title and author matches, and prompts you if manual input is needed.

* **MP3Tag & Audiobookshelf Compatible Tagging:** Embeds `ALBUM`, `TITLE`, `SUBTITLE`, `ALBUMARTIST`, `ARTIST`, `NARRATOR` (while purging legacy `COMPOSER` frames to prevent duplicates), `PUBLISHER`, `YEAR`, `COMMENT` (Description), `GENRE`, `SERIES`, `SERIES-PART`, `ASIN`, `ISBN`, and cover art.

* **Automatic Organization:** Moves and renames tagged files into `[ALBUM] ([YEAR]) - [ALBUMARTIST]/[ALBUM] - [ALBUMARTIST].ext`.

* **Run Summary Report:** Displays a summary of succeeded and failed files on screen and saves it to `results-YYYY-MM-DD.txt`.

* **Windows Context Menu Integration:** Includes PowerShell scripts to add or remove a **"Tag this"** right-click option in Windows Explorer for folders, `.m4b`, and `.mp3` files.

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/raviwarrier/audiobook-tagger.git
   cd audiobook-tagger
   ```

2. **Create and activate a virtual environment:**

   * **Windows:**

     ```powershell
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

### CLI & Interactive Usage

When run without arguments, `tagger.py` opens a folder picker dialog and prompts you for the Audible region. When passed a file or folder path directly, it skips the prompt and defaults to the `us` region unless overridden with `-r` / `--region`.

* **Supported regions:** `us` (default), `uk`, `ca`, `au`, `in`, `de`, `fr`, `it`, `es`, `jp`

* **Windows:**

  ```powershell
  # Interactive folder picker (prompts for region)
  python tagger.py

  # Pass a folder path directly (defaults to 'us' region)
  python tagger.py "C:\Path\To\Audiobooks"

  # Pass a single audiobook file with a specific Audible region
  python tagger.py "C:\Path\To\Audiobooks\Book Title - Author.m4b" --region uk
  ```

* **Linux / macOS:**

  ```bash
  # Interactive folder picker (prompts for region)
  python3 tagger.py

  # Pass a folder or single file path directly
  python3 tagger.py "/path/to/audiobooks"
  python3 tagger.py "/path/to/audiobooks/Book Title - Author.m4b" -r in
  ```

### Windows Right-Click Context Menu (Optional)

To add a **"Tag this"** option when right-clicking folders, `.m4b`, or `.mp3` files in Windows Explorer:

```powershell
.\install_context_menu_windows.ps1
```

This runs `tagger.py` silently using the `us` region by default and closes the terminal window automatically upon completion (unless a book requires manual input). To change the default region used by the context menu, append `-r <region>` (e.g., `-r uk`) to `$CommandValue` in `install_context_menu.ps1` and re-run it.

To remove the context menu entries later:

```powershell
.\uninstall_context_menu_windows.ps1
```

## Credits

The Audible and Audnex metadata fetching and normalization logic in this script is derived and adapted from [Audiobookshelf](https://github.com/advplyr/audiobookshelf).

## License

Licensed under the MIT License.

# PDF Form Studio

Turn a PDF into a fillable form on your own computer. Detect common checkboxes and underscore blanks, then place text, long-answer, and checkbox fields visually. Original page artwork is preserved. Checked boxes use a vector checkmark.

## Setup and launch

1. Install Python if it is not already installed.
2. Download and extract this project, or clone the repository.
3. Open the `pdf-form-studio` folder in VS Code.
4. Open **Terminal > New Terminal**. Make sure the terminal is in the folder containing `make_fillable.py` and `requirements.txt`.
5. Install the required packages (only needed the first time):

   ```bash
   py -m pip install -r requirements.txt
   ```

6. Start the app:

   ```bash
   py make_fillable.py
   ```

On macOS/Linux, use `python3` instead of `py`. Tkinter must be available; some Linux installations need their distribution's `python3-tk` package.

## Create a fillable PDF

1. Click **Open PDF** and select your original form.
2. Click **Detect fields**. Green outlines are checkboxes; blue outlines are single-line fields.
3. Click **+ Text box**, **+ Long answer**, or **+ Checkbox** to place a ready-made field on the visible page.
4. Click a field to select it. Drag inside the box to move it; drag any of its four corner squares to resize it. Keep printed labels outside text fields. **Delete selected** (or Delete key) removes it. **Undo** (Ctrl+Z) reverses additions, moves, resizes, deletion, detection, and layout loading.
5. Use Previous/Next page for multipage PDFs.
6. Click **Save PDF**, choose a folder, and enter a new filename ending in `.pdf`. This creates your finished fillable document.
7. Open the saved PDF in a form-capable reader. Type in a field, check a box, save, and reopen to confirm your entries remain.

### Save PDF versus Save layout

| Button | File type | What it saves |
| --- | --- | --- |
| **Save PDF** | `.pdf` | The finished form with clickable checkboxes and typeable fields. |
| **Save layout** | `.json` | Field positions so you can continue editing or reuse the same form layout later. |

Saving a layout is optional. To reuse one, open the original PDF, click **Load layout**, and select its JSON file. Load it only onto the same form and layout; page-size validation cannot identify different documents of the same size.

Existing PDF fields are preserved; detection avoids overlapping them. Layouts can be edited in a text editor to give fields descriptive names and optional `label` values. Names must be unique across the document.

## Repeat a known layout without the editor

```bash
py make_fillable.py "My Form.pdf" --layout "my_layout.json" --output "My Form Fillable.pdf"
```

Without `--layout`, command-line mode only adds automatically detected fields. It does not infer every possible answer area. The GUI save dialog asks before replacing an existing output; command-line mode refuses to overwrite one.

## Try the included neutral example

Open `examples/sample_form.pdf`, click Detect fields, then add a Long answer field in the large empty rectangle. Or use:

```bash
py make_fillable.py examples/sample_form.pdf --layout examples/sample_layout.json --output sample_fillable.pdf
```

## Limits

Detection supports small drawn boxes, the Unicode empty checkbox character, and underscore blanks. Empty table cells and large writing areas require manual placement. Decorative shapes may be detected incorrectly. Scans can be displayed and given manually placed fields, but this project does not run OCR. Rotated/cropped forms require careful review; detection is intended for ordinary upright pages. Password-protected PDFs are unsupported. A typed signature field is not a cryptographic digital signature. PDF viewers may differ in form rendering and long-answer scrolling/printing.

This project processes documents locally and does not upload them. Keep private PDFs and completed forms out of a public repository. The included `.gitignore` excludes PDFs except the neutral sample. Review staged files before committing.

## Public GitHub setup

Create a public repository named `pdf-form-studio`. Upload this folder's contents, including `.gitignore`, `README.md`, requirements, and examples. Do not include workplace or completed forms. No personal paths are stored in the code.

## License

Project source and the neutral sample are MIT licensed; see LICENSE. PyMuPDF is a third-party dependency with AGPL/commercial licensing. This project's MIT license does not change dependency obligations. Review upstream licensing before distributing a bundled application or using it commercially: https://pymupdf.readthedocs.io/en/latest/about.html#license

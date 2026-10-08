"""Local PDF field editor. Run with Python; no web service required."""
from pathlib import Path
import argparse
import json
import pymupdf as fitz


def detect_fields(doc):
    """Conservative proposals: drawn boxes, checkbox glyphs, underscore blanks."""
    fields = []
    def add(page, kind, rect):
        r = fitz.Rect(rect)
        if any(f['page'] == page and r.intersects(fitz.Rect(f['rect'])) for f in fields):
            return
        fields.append({'page': page, 'type': kind, 'rect': list(r),
                       'name': f'{kind}_p{page+1}_{len(fields)+1}'})
    for n, page in enumerate(doc):
        existing = [w.rect for w in (page.widgets() or [])]
        def proposal(kind, rect):
            if not any(fitz.Rect(rect).intersects(r) for r in existing):
                add(n, kind, rect)
        for d in page.get_drawings():
            r = d['rect']
            if 8 <= r.width <= 20 and 8 <= r.height <= 20 and abs(r.width-r.height) <= 3:
                proposal('checkbox', r)
        for b in page.get_text('rawdict')['blocks']:
            for line in b.get('lines', []):
                chars = [c for s in line['spans'] for c in s['chars']]
                run = []
                def flush():
                    if len(run) >= 3:
                        r = fitz.Rect(run[0]['bbox'])
                        for c in run[1:]:
                            r.include_rect(fitz.Rect(c['bbox']))
                        if r.width >= 20:
                            proposal('text', fitz.Rect(r.x0, r.y0+1, r.x1, r.y1-3))
                    run.clear()
                for c in chars:
                    if c['c'] == '☐':
                        r = fitz.Rect(c['bbox'])
                        # Glyph ink is smaller than the font's full line box.
                        size = r.width
                        proposal('checkbox', fitz.Rect(r.x0, r.y0+r.height*.28,
                                                       r.x1, r.y0+r.height*.28+size))
                    if c['c'] == '_':
                        run.append(c)
                    else:
                        flush()
                flush()
    return fields


def validate_fields(doc, fields):
    names = {w.field_name for p in doc for w in (p.widgets() or [])}
    for f in fields:
        if f['type'] not in ('checkbox', 'text', 'multiline'):
            raise ValueError('Unknown field type.')
        if not 0 <= f['page'] < len(doc):
            raise ValueError('Field page is outside this PDF.')
        r = fitz.Rect(f['rect'])
        if r.is_empty or r.is_infinite or not doc[f['page']].rect.contains(r):
            raise ValueError('A field rectangle is invalid or outside its page.')
        if not f['name'] or f['name'] in names:
            raise ValueError('Every field must have a unique, nonempty name.')
        names.add(f['name'])


def export_pdf(source, destination, fields):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Save to a new file; do not overwrite the source PDF.')
    with fitz.open(source) as doc:
        if doc.needs_pass:
            raise ValueError('Password-protected PDFs are not supported.')
        validate_fields(doc, fields)
        for f in fields:
            page = doc[f['page']]
            r = fitz.Rect(f['rect'])
            w = fitz.Widget()
            w.field_name = f['name']
            w.field_label = f.get('label', f['name'])
            w.rect = r
            w.border_width = 0
            w.text_color = (0, 0, 0)
            if f['type'] == 'checkbox':
                w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                w.field_value = 'Off'
                w.text_font = 'ZaDb'
                a = page.add_widget(w)
                doc.xref_set_key(a.xref, 'MK/CA', '(4)')
                kind, ref = doc.xref_get_key(a.xref, 'AP/N/Yes')
                if kind != 'xref':
                    raise ValueError('Could not construct checkbox appearance.')
                # Vector checkmark: independent of symbol fonts.
                x, y = r.width, r.height
                stream = (f'q 0 0 0 RG {min(x,y)*.13} w 1 J 1 j '
                          f'{x*.16} {y*.50} m {x*.39} {y*.24} l '
                          f'{x*.84} {y*.82} l S Q').encode('ascii')
                doc.update_stream(int(ref.split()[0]), stream)
            else:
                w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                w.field_value = ''
                w.text_font = 'Helv'
                w.text_fontsize = min(10, r.height*.7)
                if f['type'] == 'multiline':
                    w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                page.add_widget(w)
        doc.save(destination, garbage=4, deflate=True)
    # Reopen and verify that every requested field survived the save.
    with fitz.open(destination) as check:
        found = {w.field_name for p in check for w in (p.widgets() or [])}
        if not {f['name'] for f in fields}.issubset(found):
            raise ValueError('Some form fields did not save correctly.')


def adjust_rect(rect, mode, dx, dy, bounds):
    """Move/resize a rectangle while keeping it inside the page."""
    x0,y0,x1,y1=rect
    if mode == 'move':
        dx=max(bounds.x0-x0,min(dx,bounds.x1-x1))
        dy=max(bounds.y0-y0,min(dy,bounds.y1-y1))
        return [x0+dx,y0+dy,x1+dx,y1+dy]
    minimum=3
    if 'w' in mode: x0=max(bounds.x0,min(x0+dx,x1-minimum))
    if 'e' in mode: x1=min(bounds.x1,max(x1+dx,x0+minimum))
    if 'n' in mode: y0=max(bounds.y0,min(y0+dy,y1-minimum))
    if 's' in mode: y1=min(bounds.y1,max(y1+dy,y0+minimum))
    return [x0,y0,x1,y1]


def launch_editor():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk

    class Editor:
        def __init__(self, root):
            self.root, self.doc, self.source = root, None, None
            self.fields, self.page_index, self.scale = [], 0, 1.25
            self.mode = tk.StringVar(value='select')
            self.selected = None
            self.history = []
            self.action = None
            self.image_key = None
            root.title('PDF Form Studio')
            root.geometry('1050x850')
            bar = ttk.Frame(root, padding=8)
            bar.pack(fill='x')
            for title, action in [('Open PDF', self.open), ('Detect fields', self.detect),
                                  ('Undo', self.undo), ('Save PDF', self.save),
                                  ('Save layout', self.save_layout), ('Load layout', self.load_layout)]:
                ttk.Button(bar, text=title, command=action).pack(side='left', padx=3)
            row = ttk.Frame(root, padding=8)
            row.pack(fill='x')
            ttk.Radiobutton(row, text='Select / move', value='select', variable=self.mode).pack(side='left', padx=6)
            for kind, title in [('text','+ Text box'), ('multiline','+ Long answer'), ('checkbox','+ Checkbox')]:
                ttk.Button(row, text=title, command=lambda k=kind: self.add_ready(k)).pack(side='left', padx=3)
            ttk.Button(row, text='Delete selected', command=self.delete_selected).pack(side='left', padx=3)
            ttk.Button(row, text='Previous page', command=lambda: self.change_page(-1)).pack(side='left', padx=10)
            ttk.Button(row, text='Next page', command=lambda: self.change_page(1)).pack(side='left')
            self.status = tk.StringVar(value='Open a PDF. Choose a field type and drag over an answer area.')
            ttk.Label(root, textvariable=self.status, padding=8).pack(fill='x')
            area = ttk.Frame(root)
            area.pack(fill='both', expand=True)
            self.canvas = tk.Canvas(area, background='#dce1e8')
            ys = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
            xs = ttk.Scrollbar(area, orient='horizontal', command=self.canvas.xview)
            self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
            ys.pack(side='right', fill='y'); xs.pack(side='bottom', fill='x')
            self.canvas.pack(fill='both', expand=True)
            self.canvas.bind('<ButtonPress-1>', self.press)
            self.canvas.bind('<B1-Motion>', self.drag)
            self.canvas.bind('<ButtonRelease-1>', self.release)
            self.root.bind('<Delete>', lambda e: self.delete_selected())
            self.root.bind('<Control-z>', lambda e: self.undo())
            self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(int(-e.delta/120), 'units'))
            self.start, self.preview = None, None
            root.protocol('WM_DELETE_WINDOW', self.close)

        def close(self):
            if self.doc: self.doc.close()
            self.root.destroy()

        def open(self):
            path = filedialog.askopenfilename(filetypes=[('PDF files','*.pdf')])
            if not path: return
            try:
                doc = fitz.open(path)
                if doc.needs_pass or not doc.is_pdf or len(doc) == 0:
                    doc.close()
                    raise ValueError('Choose a nonempty PDF without a password.')
                if self.doc: self.doc.close()
                self.doc, self.source, self.fields, self.page_index = doc, path, [], 0
                self.selected = None; self.history = []; self.image_key = None
                self.render()
            except Exception as e: messagebox.showerror('Open failed', str(e))

        def render(self):
            if not self.doc: return
            p = self.doc[self.page_index]
            key = (self.source, self.page_index, self.scale)
            if self.image_key != key:
                pix = p.get_pixmap(matrix=fitz.Matrix(self.scale,self.scale), alpha=False)
                self.photo = ImageTk.PhotoImage(Image.frombytes('RGB', (pix.width,pix.height), pix.samples))
                self.image_key = key
            self.canvas.delete('all')
            self.canvas.create_image(0,0, image=self.photo, anchor='nw')
            for i, f in enumerate(self.fields):
                if f['page'] != self.page_index: continue
                color = {'text':'#1672bd','multiline':'#7d48ad','checkbox':'#16844a'}[f['type']]
                coords = [v*self.scale for v in f['rect']]
                self.canvas.create_rectangle(*coords, outline='#e77918' if i==self.selected else color, width=2)
                if i == self.selected:
                    x0,y0,x1,y1 = coords
                    for x,y in [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]:
                        self.canvas.create_rectangle(x-5,y-5,x+5,y+5,fill='white',outline='#e77918',width=2)
            self.canvas.configure(scrollregion=(0,0,self.photo.width(),self.photo.height()))
            self.status.set(f'Page {self.page_index+1}/{len(self.doc)} | {len(self.fields)} fields | Click a box, drag inside to move, drag a corner square to resize.')

        def change_page(self, delta):
            if self.doc:
                self.selected = None
                self.page_index = max(0,min(len(self.doc)-1,self.page_index+delta))
                self.render()

        def detect(self):
            if not self.doc: return
            self.remember()
            existing_names = {w.field_name for p in self.doc for w in (p.widgets() or [])}
            existing_names.update(f['name'] for f in self.fields)
            for f in detect_fields(self.doc):
                r = fitz.Rect(f['rect'])
                if any(g['page']==f['page'] and r.intersects(fitz.Rect(g['rect'])) for g in self.fields): continue
                while f['name'] in existing_names: f['name'] += '_new'
                existing_names.add(f['name']); self.fields.append(f)
            self.render()

        def remember(self):
            import copy
            self.history.append(copy.deepcopy(self.fields))
            self.history = self.history[-100:]

        def add_ready(self, kind):
            if not self.doc:
                messagebox.showinfo('Open a PDF', 'Open a PDF first.'); return
            self.remember()
            bounds = self.doc[self.page_index].rect
            width,height = {'text':(160,22),'multiline':(260,100),'checkbox':(12,12)}[kind]
            # Place the box within the visible part of the page.
            x = max(bounds.x0, self.canvas.canvasx(70)/self.scale)
            y = max(bounds.y0, self.canvas.canvasy(80)/self.scale)
            width=min(width,bounds.width); height=min(height,bounds.height)
            x=min(x,bounds.x1-width); y=min(y,bounds.y1-height)
            names = {w.field_name for p in self.doc for w in (p.widgets() or [])}
            names.update(f['name'] for f in self.fields)
            name=f'{kind}_p{self.page_index+1}_{len(self.fields)+1}'
            while name in names: name += '_new'
            self.fields.append({'page':self.page_index,'type':kind,'rect':[x,y,x+width,y+height],'name':name})
            self.selected=len(self.fields)-1
            self.mode.set('select'); self.render()

        def delete_selected(self):
            if self.selected is not None and self.selected < len(self.fields):
                self.remember(); self.fields.pop(self.selected); self.selected=None; self.render()

        def press(self, e):
            if not self.doc: return
            x,y = self.canvas.canvasx(e.x)/self.scale,self.canvas.canvasy(e.y)/self.scale
            handle=None
            if self.selected is not None:
                f=self.fields[self.selected]
                if f['page']==self.page_index:
                    x0,y0,x1,y1=f['rect']
                    for corner, (cx,cy) in {'nw':(x0,y0),'ne':(x1,y0),'sw':(x0,y1),'se':(x1,y1)}.items():
                        if abs(x-cx)<=7/self.scale and abs(y-cy)<=7/self.scale:
                            handle=corner; break
            if not handle:
                self.selected=None
                for i in range(len(self.fields)-1,-1,-1):
                    f=self.fields[i]
                    if f['page']==self.page_index and fitz.Rect(f['rect']).contains(fitz.Point(x,y)):
                        self.selected=i; break
            if self.selected is not None:
                self.remember()
                self.action=(handle or 'move', x,y,list(self.fields[self.selected]['rect']))
            else: self.action=None
            self.render()

        def drag(self, e):
            if not self.action or self.selected is None: return
            mode,x,y,original=self.action
            px=self.canvas.canvasx(e.x)/self.scale
            py=self.canvas.canvasy(e.y)/self.scale
            self.fields[self.selected]['rect']=adjust_rect(original,mode,px-x,py-y,self.doc[self.page_index].rect)
            self.render()

        def release(self, e):
            if self.action: self.drag(e)
            self.action=None

        def undo(self):
            if self.history:
                self.fields=self.history.pop(); self.selected=None; self.action=None; self.render()

        def save_layout(self):
            if not self.doc: return
            path = filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('Layout','*.json')])
            if path:
                data = {'version':1,'page_sizes':[[p.rect.width,p.rect.height] for p in self.doc],'fields':self.fields}
                Path(path).write_text(json.dumps(data,indent=2),encoding='utf-8')

        def load_layout(self):
            if not self.doc: return
            path = filedialog.askopenfilename(filetypes=[('Layout','*.json')])
            if not path: return
            try:
                data=json.loads(Path(path).read_text(encoding='utf-8'))
                if data['page_sizes'] != [[p.rect.width,p.rect.height] for p in self.doc]:
                    raise ValueError('This layout has different page sizes or page count.')
                validate_fields(self.doc,data['fields'])
                self.remember(); self.fields=data['fields']; self.selected=None; self.render()
            except Exception as e: messagebox.showerror('Layout failed',str(e))

        def save(self):
            if not self.doc: return
            if not self.fields:
                messagebox.showinfo('No new fields','Detect fields or drag to add fields first.'); return
            path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=Path(self.source).stem+'_fillable.pdf',filetypes=[('PDF','*.pdf')])
            if not path: return
            try:
                export_pdf(self.source,path,self.fields)
                messagebox.showinfo('Saved','Fillable PDF saved. Open it, fill some fields, save, and reopen to check your entries.')
            except Exception as e: messagebox.showerror('Save failed',str(e))

    root=tk.Tk(); Editor(root); root.mainloop()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',nargs='?',type=Path)
    parser.add_argument('--layout',type=Path,help='Saved field layout for this exact form')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.pdf:
        launch_editor(); return
    try:
        with fitz.open(args.pdf) as doc:
            if doc.needs_pass: raise ValueError('Password-protected PDFs are not supported.')
            if args.layout:
                data=json.loads(args.layout.read_text(encoding='utf-8'))
                if data['page_sizes'] != [[p.rect.width,p.rect.height] for p in doc]:
                    raise ValueError('Layout page sizes do not match this PDF.')
                fields=data['fields']
            else: fields=detect_fields(doc)
        output=args.output or args.pdf.with_name(args.pdf.stem+'_fillable.pdf')
        if output.exists(): raise ValueError('Output already exists; choose a new --output filename.')
        export_pdf(args.pdf,output,fields)
        print(f'Saved {len(fields)} new fields to {output}. Review the result before use.')
    except Exception as e: parser.exit(1,f'Error: {e}\n')

if __name__ == '__main__':
    main()

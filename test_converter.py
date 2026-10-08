import tempfile
import unittest
from pathlib import Path
import pymupdf as fitz
from make_fillable import detect_fields, export_pdf, adjust_rect

class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name)/'source.pdf'
        with fitz.open() as doc:
            p=doc.new_page()
            p.draw_rect(fitz.Rect(40,40,52,52))
            p.insert_text((40,90),'Name: ______________')
            doc.save(self.source)
    def tearDown(self): self.temp.cleanup()
    def test_detection(self):
        with fitz.open(self.source) as d:
            fields=detect_fields(d)
            self.assertEqual(sorted(f['type'] for f in fields),['checkbox','text'])
    def test_export_and_saved_values(self):
        with fitz.open(self.source) as d:fields=detect_fields(d)
        fields.append({'page':0,'type':'multiline','name':'notes','rect':[40,120,300,240]})
        output=Path(self.temp.name)/'fillable.pdf'
        export_pdf(self.source,output,fields)
        with fitz.open(output) as d:
            page=d[0]
            widgets=list(page.widgets())
            self.assertEqual(len(widgets),3)
            for w in widgets:
                if w.field_type==fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    kind,ref=d.xref_get_key(w.xref,'AP/N/Yes')
                    self.assertEqual(kind,'xref')
                    self.assertIn(b' l S Q',d.xref_stream(int(ref.split()[0])))
                    d.xref_set_key(w.xref,'V','/Yes');d.xref_set_key(w.xref,'AS','/Yes')
                else:
                    w.field_value='Test entry';w.update()
            saved=Path(self.temp.name)/'completed.pdf';d.save(saved)
        with fitz.open(saved) as d:
            page=d[0]
            for w in page.widgets():
                self.assertEqual(w.field_value,'Yes' if w.field_type==fitz.PDF_WIDGET_TYPE_CHECKBOX else 'Test entry')
                if w.field_name=='notes':self.assertTrue(w.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
    def test_move_and_resize(self):
        bounds=fitz.Rect(0,0,600,800)
        self.assertEqual(adjust_rect([10,20,110,50],'move',40,30,bounds),[50,50,150,80])
        self.assertEqual(adjust_rect([10,20,110,50],'move',-100,-100,bounds),[0,0,100,30])
        self.assertEqual(adjust_rect([10,20,110,50],'se',20,30,bounds),[10,20,130,80])
        self.assertEqual(adjust_rect([10,20,110,50],'nw',200,200,bounds),[107,47,110,50])

    def test_protect_source(self):
        with self.assertRaises(ValueError):export_pdf(self.source,self.source,[])
    def test_reject_duplicate_names(self):
        fields=[{'page':0,'type':'text','name':'same','rect':[40,120,300,140]}]*2
        with self.assertRaises(ValueError):export_pdf(self.source,Path(self.temp.name)/'out.pdf',fields)

if __name__=='__main__':unittest.main()

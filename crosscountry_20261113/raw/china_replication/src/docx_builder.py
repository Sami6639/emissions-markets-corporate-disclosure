# -*- coding: utf-8 -*-
"""Shared layout helpers for producing documents with a fixed typographic specification.
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BLACK = RGBColor(0, 0, 0)
EN = "Times New Roman"

def _run(run, cn="宋体", size=12, bold=False):
    run.font.name = EN; run.font.size = Pt(size); run.font.bold = bold
    run.font.color.rgb = BLACK
    rF = run._element.get_or_add_rPr().get_or_add_rFonts()
    rF.set(qn("w:eastAsia"), cn); rF.set(qn("w:ascii"), EN); rF.set(qn("w:hAnsi"), EN)
    return run

def _fmt(p, indent=0, line_pt=28, before=0, after=0, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY; pf.line_spacing = Pt(line_pt)
    pf.space_before = Pt(before); pf.space_after = Pt(after); pf.alignment = align
    ind = p._p.get_or_add_pPr().get_or_add_ind()
    if indent: ind.set(qn("w:firstLineChars"), str(indent*100))
    else: ind.set(qn("w:firstLineChars"), "0"); ind.set(qn("w:firstLine"), "0")
    return p

def new_doc():
    doc = Document(); s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.top_margin = s.bottom_margin = Cm(2.54); s.left_margin = s.right_margin = Cm(3.17)
    st = doc.styles["Normal"]; st.font.name = EN; st.font.size = Pt(12)
    st.font.color.rgb = BLACK; st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    return doc

def doc_title(doc, t):
    p = doc.add_paragraph(); _fmt(p,0,28,0,12,WD_ALIGN_PARAGRAPH.CENTER); _run(p.add_run(t),"黑体",22,True); return p
def h1(doc, t):
    p = doc.add_paragraph(); _fmt(p,0,28,12,6,WD_ALIGN_PARAGRAPH.LEFT); _run(p.add_run(t),"黑体",16,True); return p
def h2(doc, t):
    p = doc.add_paragraph(); _fmt(p,0,28,6,6,WD_ALIGN_PARAGRAPH.LEFT); _run(p.add_run(t),"黑体",14,True); return p
def h3(doc, t):
    p = doc.add_paragraph(); _fmt(p,0,28,6,3,WD_ALIGN_PARAGRAPH.LEFT); _run(p.add_run(t),"黑体",12,True); return p
def body(doc, t, indent=2):
    p = doc.add_paragraph(); _fmt(p,indent,28,0,0); _run(p.add_run(t),"宋体",12,False); return p
def caption(doc, t, above=True):
    p = doc.add_paragraph(); _fmt(p,0,20,6 if above else 3,3 if above else 6,WD_ALIGN_PARAGRAPH.CENTER)
    _run(p.add_run(t),"黑体",10.5,False); return p

def _border(tc, edge, sz):
    tcPr = tc._tc.get_or_add_tcPr(); bs = tcPr.find(qn("w:tcBorders"))
    if bs is None: bs = OxmlElement("w:tcBorders"); tcPr.append(bs)
    el = bs.find(qn("w:"+edge))
    if el is None: el = OxmlElement("w:"+edge); bs.append(el)
    if sz == 0: el.set(qn("w:val"), "nil")
    else:
        el.set(qn("w:val"),"single"); el.set(qn("w:sz"),str(sz)); el.set(qn("w:color"),"000000")

def three_line_table(doc, header, rows, widths=None):
    t = doc.add_table(rows=len(rows)+1, cols=len(header))
    t.style = doc.styles["Table Grid"]; t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    data = [header]+rows
    for i,row in enumerate(data):
        for j,val in enumerate(row):
            c = t.cell(i,j); c.text = ""
            p = c.paragraphs[0]
            _fmt(p,0,16,2,2, WD_ALIGN_PARAGRAPH.CENTER if i==0 else WD_ALIGN_PARAGRAPH.LEFT)
            _run(p.add_run(str(val)), "黑体" if i==0 else "宋体", 10.5, i==0)
            for e in ("left","right","insideH","insideV"): _border(c,e,0)
            _border(c,"top", 12 if i==0 else (6 if i==1 else 0))
            _border(c,"bottom", 6 if i==0 else (12 if i==len(data)-1 else 0))
            if widths: c.width = Cm(widths[j])
    if widths:
        for row in t.rows:
            for j,c in enumerate(row.cells): c.width = Cm(widths[j])
    return t

def page_number_footer(doc):
    p = doc.sections[0].footer.paragraphs[0]
    _fmt(p,0,14,0,0,WD_ALIGN_PARAGRAPH.CENTER)
    _run(p.add_run("第 "),"宋体",9)
    r = p.add_run(); _run(r,"宋体",9)
    f = OxmlElement("w:fldSimple"); f.set(qn("w:instr"),"PAGE"); r._element.addnext(f)
    _run(p.add_run(" 页"),"宋体",9)

def scrub(doc):
    cp = doc.core_properties
    for f in ("author","last_modified_by","title","subject","comments","category",
              "keywords","content_status","identifier","language","version"):
        try: setattr(cp,f,"")
        except Exception: pass
    try: cp.revision = 1
    except Exception: pass
    return doc

def strip_thumbnail(path):
    import zipfile, shutil, re
    drop = {"docProps/thumbnail.jpeg","customXml/item1.xml",
            "customXml/_rels/item1.xml.rels","customXml/itemProps1.xml"}
    rel = re.compile(r"<Relationship\b[^>]*?/>"); ct = re.compile(r'<(Override|Default)\b[^>]*?/>')
    tmp = path+".tmp"
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED) as zo:
        for it in zi.infolist():
            if it.filename in drop: continue
            data = zi.read(it.filename)
            if it.filename == "_rels/.rels":
                s = data.decode(); s = rel.sub(lambda m: "" if ("thumbnail" in m.group(0) or "customXml" in m.group(0)) else m.group(0), s); data = s.encode()
            elif it.filename == "word/_rels/document.xml.rels":
                s = data.decode(); s = rel.sub(lambda m: "" if "customXml" in m.group(0) else m.group(0), s); data = s.encode()
            elif it.filename == "[Content_Types].xml":
                s = data.decode(); s = ct.sub(lambda m: "" if ("thumbnail" in m.group(0) or "customXml" in m.group(0)) else m.group(0), s); data = s.encode()
            zo.writestr(it, data)
    shutil.move(tmp, path)

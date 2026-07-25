"""Build minimal, valid PDFs in pure Python -- no third-party dependencies.

The whole point of this project is telling a text PDF apart from an image-only
one, so the test suite needs both. Shipping real sample documents would mean
publishing whatever they contain, so the fixtures are synthesised instead:

  * text_pdf()       -- a real text layer, several hundred characters per page
  * image_only_pdf() -- drawn shapes only, zero extractable text (what a
                        screenshot saved as PDF or a scan actually looks like)
  * sparse_pdf()     -- a text layer too thin to be worth reading, like a
                        certificate whose only real content is a graphic

These are deliberately hand-built rather than generated with reportlab so the
suite runs on a bare CI image with nothing installed but pytest.
"""


def _build(pages_content, with_font=True):
    """Assemble a PDF from per-page content streams, with a correct xref."""
    objects = []          # 1-indexed object bodies, as bytes
    n_pages = len(pages_content)

    # Object numbering: 1 catalog, 2 pages, then per page a page object and a
    # content stream, then optionally the font.
    page_obj_ids = [3 + 2 * i for i in range(n_pages)]
    content_ids = [4 + 2 * i for i in range(n_pages)]
    font_id = 3 + 2 * n_pages

    kids = " ".join("{} 0 R".format(i) for i in page_obj_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        "<< /Type /Pages /Kids [{}] /Count {} >>".format(kids, n_pages).encode()
    )

    for i in range(n_pages):
        res = ("<< /Font << /F1 {} 0 R >> >>".format(font_id) if with_font
               else "<< >>")
        objects.append((
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents {} 0 R /Resources {} >>".format(content_ids[i], res)
        ).encode())
        stream = pages_content[i].encode("latin-1")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"
        )

    if with_font:
        objects.append(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += "{} 0 obj\n".format(idx).encode() + body + b"\nendobj\n"

    xref_at = len(out)
    count = len(objects) + 1
    out += "xref\n0 {}\n".format(count).encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += "{:010d} 00000 n \n".format(off).encode()
    out += (
        "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n"
        .format(count, xref_at).encode()
    )
    return bytes(out)


def _text_stream(lines, size=12, start_y=720):
    parts = ["BT", "/F1 {} Tf".format(size), "72 {} Td".format(start_y),
             "14 TL"]
    for ln in lines:
        safe = ln.replace("\\", "").replace("(", "").replace(")", "")
        parts.append("({}) Tj T*".format(safe))
    parts.append("ET")
    return "\n".join(parts)


def text_pdf(pages=2):
    """A PDF with a genuine text layer: ~700+ characters per page."""
    body = [
        "Quarterly operations review and supporting commentary for the",
        "period under examination, prepared for internal distribution.",
        "Revenue held broadly flat against the prior comparable period,",
        "while operating costs decreased on the back of renegotiated",
        "supplier terms and a reduction in contracted headcount.",
        "Outstanding risks are concentrated in the supply chain, where a",
        "single vendor accounts for a disproportionate share of volume.",
        "Mitigation work is under way and is expected to conclude before",
        "the end of the next reporting period, subject to procurement.",
        "Recommendations follow in the appendix, together with the",
        "detailed figures underpinning each of the statements above.",
    ]
    return _build([_text_stream(body) for _ in range(pages)])


def image_only_pdf(pages=1):
    """A PDF with drawn shapes and no text at all.

    This is what a browser screenshot exported to PDF looks like to a text
    extractor: pdfminer returns zero characters and markitdown still exits 0.
    """
    shapes = "\n".join([
        "0.2 0.3 0.8 rg",
        "72 400 468 300 re f",
        "0.9 0.4 0.1 rg",
        "72 200 200 150 re f",
    ])
    return _build([shapes for _ in range(pages)], with_font=False)


def sparse_pdf():
    """A PDF whose text layer is real but far too thin to be useful."""
    return _build([_text_stream(["Certificate of Completion"])])

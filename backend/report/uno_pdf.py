"""DOCX -> PDF via LibreOffice with index (TOC / List of Figures / List of
Tables) update.

A plain `soffice --convert-to pdf` does NOT refresh Word index fields, so
server-generated PDFs would ship with empty TOC pages. This module drives
LibreOffice through its UNO automation bridge instead: load the document,
update all indexes and fields, export the PDF.

Run standalone (spawned as a subprocess by generate.convert_to_pdf so a hung
office process can never wedge the API):

    python -m report.uno_pdf input.docx output.pdf
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


def _convert(in_path: str, out_path: str) -> None:
    import uno  # provided by python3-uno
    from com.sun.star.beans import PropertyValue

    def prop(name, value):
        p = PropertyValue()
        p.Name, p.Value = name, value
        return p

    port = 2002 + (os.getpid() % 500)
    profile = f"/tmp/lo_profile_{port}"
    soffice = subprocess.Popen([
        "soffice", "--headless", "--invisible", "--norestore", "--nologo",
        f"-env:UserInstallation=file://{profile}",
        f"--accept=socket,host=127.0.0.1,port={port};urp;",
    ])
    try:
        ctx = None
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(60):  # wait up to 30 s for the office to listen
            try:
                ctx = resolver.resolve(
                    f"uno:socket,host=127.0.0.1,port={port};urp;"
                    f"StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        if ctx is None:
            raise RuntimeError("could not connect to LibreOffice")

        desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        url_in = uno.systemPathToFileUrl(os.path.abspath(in_path))
        url_out = uno.systemPathToFileUrl(os.path.abspath(out_path))
        doc = desktop.loadComponentFromURL(
            url_in, "_blank", 0,
            (prop("Hidden", True), prop("UpdateDocMode", 3)))  # FULL_UPDATE
        try:
            # refresh text fields, then every index (TOC, figures, tables) —
            # twice, because page numbers can shift after the first update.
            for _ in range(2):
                doc.refresh()
                if hasattr(doc, "getTextFieldMasters"):
                    try:
                        doc.TextFields.refresh()
                    except Exception:
                        pass
                indexes = doc.getDocumentIndexes()
                for i in range(indexes.getCount()):
                    indexes.getByIndex(i).update()
            doc.storeToURL(url_out, (prop("FilterName", "writer_pdf_Export"),))
        finally:
            doc.close(False)
    finally:
        soffice.terminate()
        try:
            soffice.wait(timeout=10)
        except Exception:
            soffice.kill()


if __name__ == "__main__":
    _convert(sys.argv[1], sys.argv[2])
    print(sys.argv[2])

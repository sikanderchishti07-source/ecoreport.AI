"""DOCX -> PDF with the Table of Contents / List of Figures / List of Tables
populated.

A plain `soffice --convert-to pdf` does not refresh Word index fields, so the
contents pages come out blank. Two strategies are tried, in order:

1. A LibreOffice **Basic macro** installed into a throw-away user profile and
   invoked from the command line. This needs nothing beyond
   `libreoffice-writer`, so it works on hosts where the optional
   `python3-uno` package is unavailable.
2. The Python **UNO bridge**, when `python3-uno` happens to be installed.

If both fail the caller falls back to a plain conversion, which still gives a
valid PDF — just with empty index pages.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

BASIC_MODULE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
Sub ConvertWithIndexes(sIn As String, sOut As String)
    Dim oDoc As Object, oIdx As Object, i As Integer, n As Integer
    Dim aLoad(1) As New com.sun.star.beans.PropertyValue
    Dim aSave(0) As New com.sun.star.beans.PropertyValue
    aLoad(0).Name = "Hidden"
    aLoad(0).Value = True
    aLoad(1).Name = "UpdateDocMode"
    aLoad(1).Value = com.sun.star.document.UpdateDocMode.FULL_UPDATE
    oDoc = StarDesktop.loadComponentFromURL(sIn, "_blank", 0, aLoad())
    For n = 1 To 2
        oDoc.refresh()
        oIdx = oDoc.getDocumentIndexes()
        For i = 0 To oIdx.Count - 1
            oIdx.getByIndex(i).update()
        Next i
    Next n
    aSave(0).Name = "FilterName"
    aSave(0).Value = "writer_pdf_Export"
    oDoc.storeToURL(sOut, aSave())
    oDoc.close(False)
End Sub
</script:module>
"""

SCRIPT_LB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">
<library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false">
 <library:element library:name="Module1"/>
</library:library>
"""

SCRIPT_LC = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:libraries PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "libraries.dtd">
<library:libraries xmlns:library="http://openoffice.org/2000/library" xmlns:xlink="http://www.w3.org/1999/xlink">
 <library:library library:name="Standard" xlink:href="$(USER)/basic/Standard/script.xlb/" xlink:type="simple" library:link="false"/>
</library:libraries>
"""


def _soffice() -> str:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise RuntimeError("LibreOffice not found (install libreoffice-writer)")
    return exe


def _url(path: str) -> str:
    return "file://" + os.path.abspath(path).replace(" ", "%20")


def convert_with_macro(in_path: str, out_path: str, timeout: int = 420) -> str:
    """Strategy 1 — Basic macro in a disposable profile. No python3-uno needed."""
    profile = os.path.join(tempfile.gettempdir(), f"lo_prof_{uuid.uuid4().hex}")
    basic = os.path.join(profile, "user", "basic", "Standard")
    os.makedirs(basic, exist_ok=True)
    with open(os.path.join(basic, "Module1.xba"), "w") as fh:
        fh.write(BASIC_MODULE)
    with open(os.path.join(basic, "script.xlb"), "w") as fh:
        fh.write(SCRIPT_LB)
    with open(os.path.join(profile, "user", "basic", "script.xlc"), "w") as fh:
        fh.write(SCRIPT_LC)

    macro = ("vnd.sun.star.script:Standard.Module1.ConvertWithIndexes"
             "?language=Basic&location=application")
    cmd = [_soffice(), "--headless", "--invisible", "--norestore", "--nologo",
           f"-env:UserInstallation=file://{profile}",
           macro, _url(in_path), _url(out_path)]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=timeout)
        for _ in range(20):          # allow the file to be flushed
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                return out_path
            time.sleep(0.5)
        raise RuntimeError("macro conversion produced no PDF")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def convert_with_uno(in_path: str, out_path: str) -> str:
    """Strategy 2 — Python UNO bridge, when python3-uno is present."""
    import uno
    from com.sun.star.beans import PropertyValue

    def prop(name, value):
        p = PropertyValue()
        p.Name, p.Value = name, value
        return p

    port = 2002 + (os.getpid() % 500)
    profile = os.path.join(tempfile.gettempdir(), f"lo_uno_{port}")
    proc = subprocess.Popen([
        _soffice(), "--headless", "--invisible", "--norestore", "--nologo",
        f"-env:UserInstallation=file://{profile}",
        f"--accept=socket,host=127.0.0.1,port={port};urp;",
    ])
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local)
        ctx = None
        for _ in range(60):
            try:
                ctx = resolver.resolve(
                    f"uno:socket,host=127.0.0.1,port={port};urp;"
                    f"StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        if ctx is None:
            raise RuntimeError("could not reach LibreOffice")
        desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(
            _url(in_path), "_blank", 0,
            (prop("Hidden", True), prop("UpdateDocMode", 3)))
        try:
            for _ in range(2):
                doc.refresh()
                idx = doc.getDocumentIndexes()
                for i in range(idx.getCount()):
                    idx.getByIndex(i).update()
            doc.storeToURL(_url(out_path),
                           (prop("FilterName", "writer_pdf_Export"),))
        finally:
            doc.close(False)
        return out_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def convert(in_path: str, out_path: str) -> str:
    """Try the macro route first, then the UNO bridge."""
    errors = []
    for fn in (convert_with_macro, convert_with_uno):
        try:
            p = fn(in_path, out_path)
            if os.path.exists(p) and os.path.getsize(p) > 1024:
                return p
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn.__name__}: {exc}")
    raise RuntimeError("index-aware PDF conversion failed — " + "; ".join(errors))


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2]))

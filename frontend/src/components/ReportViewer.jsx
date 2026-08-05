import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchReportPage, reportPageCount } from "@/lib/api";

/**
 * Reads a generated report on screen, one rasterised page at a time.
 *
 * Why images rather than the PDF: the whole point of the review workflow is
 * that a field operator reads the report but does not receive the file.
 * Streaming the PDF into an iframe would put Chrome's own download and print
 * buttons on the very screen where the download button was removed. Serving
 * page images means there is no document in the browser to save.
 *
 * Pages load on demand and are kept once loaded, so paging back and forth
 * costs nothing. Object URLs are revoked on unmount — a sixty-page report
 * held open would otherwise sit in memory for the life of the tab.
 */
export default function ReportViewer({ report, onClose }) {
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState({});      // page number -> object URL
  const [loading, setLoading] = useState(true);
  const urlsRef = useRef({});

  useEffect(() => {
    let cancelled = false;
    reportPageCount(report.id)
      .then((d) => { if (!cancelled) setTotal(d.pages || 0); })
      .catch((e) => {
        if (cancelled) return;
        toast.error(e?.response?.data?.detail || "Could not open this report");
        onClose?.();
      });
    return () => { cancelled = true; };
  }, [report.id, onClose]);

  // Revoke every object URL when the reader closes.
  useEffect(() => {
    const held = urlsRef.current;
    return () => {
      Object.values(held).forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  const load = useCallback(async (n) => {
    if (!n || n < 1 || urlsRef.current[n]) return;
    try {
      const blob = await fetchReportPage(report.id, n);
      const url = URL.createObjectURL(blob);
      urlsRef.current[n] = url;
      setPages((p) => ({ ...p, [n]: url }));
    } catch {
      /* a single missing page should not close the reader */
    }
  }, [report.id]);

  // Current page, plus the next one so paging forward feels instant.
  useEffect(() => {
    if (!total) return;
    let alive = true;
    setLoading(!urlsRef.current[page]);
    (async () => {
      await load(page);
      if (alive) setLoading(false);
      if (page < total) load(page + 1);
    })();
    return () => { alive = false; };
  }, [page, total, load]);

  // Arrow keys and Escape, as in any document reader.
  useEffect(() => {
    const key = (e) => {
      if (e.key === "Escape") onClose?.();
      if (e.key === "ArrowRight" || e.key === "PageDown") {
        setPage((p) => Math.min(p + 1, total || p));
      }
      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        setPage((p) => Math.max(p - 1, 1));
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [total, onClose]);

  const src = pages[page];

  return (
    <div className="fixed inset-0 z-50 bg-background/98 backdrop-blur flex flex-col">
      <header className="border-b border-border px-4 h-14 flex items-center gap-3 shrink-0">
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">
            {report.version
              ? `v${String(report.version).padStart(3, "0")}`
              : "Report"}
            <span className="text-muted-foreground font-normal">
              {" · "}{(report.lang || "en").toUpperCase()}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground truncate">
            {report.filename}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline" size="icon" className="rounded-sm h-9 w-9"
            onClick={() => setPage((p) => Math.max(p - 1, 1))}
            disabled={page <= 1}
            title="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-xs font-mono tabular w-[92px] text-center">
            {total ? `${page} / ${total}` : "…"}
          </span>
          <Button
            variant="outline" size="icon" className="rounded-sm h-9 w-9"
            onClick={() => setPage((p) => Math.min(p + 1, total || p))}
            disabled={!total || page >= total}
            title="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
          <Button
            variant="outline" className="rounded-sm h-9 ml-2"
            onClick={onClose}
            data-testid="close-viewer"
          >
            <X className="w-4 h-4 mr-1.5" /> Close
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4 md:p-8">
        <div className="mx-auto max-w-[900px]">
          {loading && !src ? (
            <div className="h-[70vh] flex items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Rendering page {page}…
            </div>
          ) : src ? (
            <img
              src={src}
              alt={`Page ${page}`}
              className="w-full border border-border rounded-sm shadow-sm bg-white"
              draggable={false}
            />
          ) : (
            <p className="text-sm text-muted-foreground text-center py-20">
              This page could not be rendered.
            </p>
          )}
        </div>
      </div>

      <footer className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground shrink-0">
        Reading view — the document itself is released by the reviewing
        engineer.
      </footer>
    </div>
  );
}

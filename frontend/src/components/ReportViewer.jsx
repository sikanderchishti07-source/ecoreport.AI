import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchReportPage, reportPageCount } from "@/lib/api";

/**
 * Reads a generated report on screen: one continuous scroll, as any document
 * reader behaves. Paging with arrows was a slideshow, not a review tool.
 *
 * Why images rather than the PDF: the review workflow exists so that a field
 * operator reads the report without receiving the file. Streaming the PDF
 * into an iframe would put Chrome's own download and print buttons on the
 * screen where the download button was deliberately removed.
 *
 * How it stays quick:
 *
 * * Every page gets a placeholder at the true aspect ratio immediately, so
 *   the scrollbar is correct from the first frame and never jumps.
 * * An IntersectionObserver loads a page shortly before it is reached, with
 *   a generous margin, so scrolling normally never waits.
 * * The server renders the whole document into its cache in the background
 *   the moment the reader opens, so those requests are served from disk.
 *
 * Object URLs are revoked on unmount; a sixty-page report held open would
 * otherwise stay in memory for the life of the tab.
 */
export default function ReportViewer({ report, onClose }) {
  const [total, setTotal] = useState(0);
  const [ratio, setRatio] = useState(842 / 595);   // A4 until told otherwise
  const [pages, setPages] = useState({});
  const [current, setCurrent] = useState(1);
  const [opening, setOpening] = useState(true);

  const urlsRef = useRef({});
  const wantedRef = useRef(new Set());
  const scrollRef = useRef(null);
  const slotsRef = useRef([]);

  useEffect(() => {
    let cancelled = false;
    reportPageCount(report.id)
      .then((d) => {
        if (cancelled) return;
        setTotal(d.pages || 0);
        if (d.page_width && d.page_height) {
          setRatio(d.page_height / d.page_width);
        }
        setOpening(false);
      })
      .catch((e) => {
        if (cancelled) return;
        toast.error(e?.response?.data?.detail || "Could not open this report");
        onClose?.();
      });
    return () => { cancelled = true; };
  }, [report.id, onClose]);

  useEffect(() => {
    const held = urlsRef.current;
    return () => Object.values(held).forEach((u) => URL.revokeObjectURL(u));
  }, []);

  const load = useCallback(async (n) => {
    if (!n || n < 1 || wantedRef.current.has(n)) return;
    wantedRef.current.add(n);
    try {
      const blob = await fetchReportPage(report.id, n);
      const url = URL.createObjectURL(blob);
      urlsRef.current[n] = url;
      setPages((p) => ({ ...p, [n]: url }));
    } catch {
      wantedRef.current.delete(n);   // let it retry if scrolled past again
    }
  }, [report.id]);

  // Load what is on screen or nearly on screen, and track the page number
  // shown in the header.
  useEffect(() => {
    if (!total) return;
    const root = scrollRef.current;
    if (!root) return;

    const near = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          load(Number(e.target.dataset.page));
        }
      });
    }, { root, rootMargin: "1200px 0px" });

    const centre = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) setCurrent(Number(e.target.dataset.page));
      });
    }, { root, rootMargin: "-45% 0px -45% 0px" });

    slotsRef.current.filter(Boolean).forEach((el) => {
      near.observe(el);
      centre.observe(el);
    });
    return () => { near.disconnect(); centre.disconnect(); };
  }, [total, load]);

  const jump = (n) => {
    const el = slotsRef.current[n - 1];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  useEffect(() => {
    const key = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col">
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
          <div className="flex items-center gap-1.5 text-xs">
            <input
              type="number"
              min={1}
              max={total || 1}
              value={current}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (n >= 1 && n <= total) { setCurrent(n); jump(n); }
              }}
              className="w-14 h-9 rounded-sm border border-border bg-background px-2 text-center font-mono tabular"
              aria-label="Go to page"
            />
            <span className="text-muted-foreground font-mono">
              / {total || "…"}
            </span>
          </div>
          <Button
            variant="outline" className="rounded-sm h-9 ml-2"
            onClick={onClose}
            data-testid="close-viewer"
          >
            <X className="w-4 h-4 mr-1.5" /> Close
          </Button>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-auto bg-secondary/30">
        {opening ? (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>Opening the report…</span>
            <span className="text-xs">
              The first time a version is opened it is converted for reading.
              This takes about a minute; afterwards it is instant.
            </span>
          </div>
        ) : (
          <div className="mx-auto max-w-[920px] py-6 px-3 md:px-6 space-y-5">
            {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
              <div
                key={n}
                data-page={n}
                ref={(el) => { slotsRef.current[n - 1] = el; }}
                className="relative w-full bg-white border border-border rounded-sm shadow-sm overflow-hidden"
                style={{ aspectRatio: `1 / ${ratio}` }}
              >
                {pages[n] ? (
                  <img
                    src={pages[n]}
                    alt={`Page ${n}`}
                    className="w-full h-full object-contain"
                    draggable={false}
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" /> {n}
                  </div>
                )}
                <span className="absolute bottom-1 right-2 text-[10px] text-muted-foreground/70 font-mono">
                  {n}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <footer className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground shrink-0">
        Reading view — the document itself is released by the reviewing
        engineer.
      </footer>
    </div>
  );
}

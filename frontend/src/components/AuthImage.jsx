import { useEffect, useState } from "react";
import { fetchAttachmentBlob } from "@/lib/api";

/**
 * Renders an attachment that sits behind authentication.
 *
 * The attachment route requires a Bearer token. A plain <img src="..."> is
 * fetched by the browser with cookies only, never that header, so every
 * thumbnail came back 401 and rendered blank. Here the file is fetched with
 * the app's own client — which carries the token — and handed to the browser
 * as an object URL instead.
 *
 * The object URL is revoked on unmount and whenever the id changes, so
 * scrolling through a long list of certificates does not leak memory.
 */
export default function AuthImage({ attachmentId, fetcher, alt, className }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = null;

    setUrl(null);
    setFailed(false);

    // Attachments by default, but anything else behind the same token can
    // pass its own fetcher — a sample photograph lives on its own route.
    (fetcher ? fetcher(attachmentId) : fetchAttachmentBlob(attachmentId))
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attachmentId, fetcher]);

  if (failed) {
    return (
      <span className="text-[10px] text-muted-foreground px-2 text-center">
        Preview unavailable
      </span>
    );
  }
  if (!url) {
    return <span className="text-[10px] text-muted-foreground">Loading…</span>;
  }
  return <img src={url} alt={alt} className={className} />;
}

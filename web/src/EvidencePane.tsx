import type { EvidenceRole, FragmentView, Point } from "./evidence";
import { confidenceChip, zoomTransform } from "./bands";
import { bboxFromPolygon, formatBBox, formatPolygon, svgPointYDown } from "./evidence";

const PAGE_W = 100;
const PAGE_H = 140;

function svgPoints(polygon: Point[]): string {
  return polygon.map(([x, y]) => svgPointYDown(x, y, PAGE_W, PAGE_H)).join(" ");
}

type PaneProps = {
  title: string;
  role: EvidenceRole;
  fragment: FragmentView | undefined;
  pageImageUrl?: string;
  zoomed?: boolean;
};

function overlayPoints(polygon: Point[]): string {
  return polygon.map(([x, y]) => svgPointYDown(x, y)).join(" ");
}

export function EvidencePane({ title, role, fragment, pageImageUrl, zoomed = false }: PaneProps) {
  const polygon = fragment?.polygon_norm;
  const bbox = polygon && polygon.length >= 3 ? bboxFromPolygon(polygon) : null;
  const missing = fragment === undefined;
  const zoom = zoomed && bbox ? zoomTransform(bbox) : null;
  const zoomStyle = zoom
    ? {
        transform: `scale(${zoom.scale}) translate(${zoom.txPct}%, ${zoom.tyPct}%)`,
        transformOrigin: "0 0",
      }
    : undefined;
  return (
    <section className="pane evidence-pane" aria-label={title} data-role={role}>
      <h2>{title}</h2>
      {missing ? (
        <p className="missing-hint">Нет фрагмента: отсутствие доказательства, не нарушение.</p>
      ) : (
        <>
          {pageImageUrl ? (
            <div className={zoom ? "page-frame page-frame--zoomed" : "page-frame"}>
              <div className="page-zoom" style={zoomStyle}>
              <img src={pageImageUrl} alt={`страница ${fragment.page}`} />
              <svg
                className="page-overlay page-overlay--bitmap"
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <polygon
                  points={overlayPoints(fragment.polygon_norm)}
                  fill="rgba(163, 21, 21, 0.28)"
                  stroke="#a31515"
                  strokeWidth="0.008"
                />
              </svg>
              </div>
            </div>
          ) : (
          <svg
            className="page-overlay"
            viewBox={
              zoom
                ? `${(-zoom.txPct / 100) * PAGE_W} ${(-zoom.tyPct / 100) * PAGE_H} ${PAGE_W / zoom.scale} ${PAGE_H / zoom.scale}`
                : `0 0 ${PAGE_W} ${PAGE_H}`
            }
            role="img"
            aria-label={`страница ${fragment.page}, polygon_norm`}
          >
            <rect
              x="0"
              y="0"
              width={PAGE_W}
              height={PAGE_H}
              fill="#f7f3ea"
              stroke="#d7d0c4"
            />
            <polygon
              points={svgPoints(fragment.polygon_norm)}
              fill="rgba(163, 21, 21, 0.22)"
              stroke="#a31515"
              strokeWidth="0.8"
            />
          </svg>
          )}
          <dl className="meta">
            <div>
              <dt>Документ</dt>
              <dd>
                {fragment.document.doc_stage} {fragment.document.document_code} rev{" "}
                {fragment.document.revision}
              </dd>
            </div>
            <div>
              <dt>Утверждение</dt>
              <dd>
                {fragment.document.approval_status}
                {fragment.document.approval_basis
                  ? ` / ${fragment.document.approval_basis}`
                  : ""}
                {fragment.document.approval_basis === "SOLE_HEAD"
                  ? " — утверждение не подтверждено"
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Лист / страница</dt>
              <dd>
                {fragment.document.sheet ?? "—"} / {fragment.page}
              </dd>
            </div>
            <div>
              <dt>file_id</dt>
              <dd>
                <code>{fragment.document.file_id}</code>
              </dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd>
                <code className="hash">{fragment.document.file_hash}</code>
              </dd>
            </div>
            <div>
              <dt>raw</dt>
              <dd>{fragment.extracted.raw_token}</dd>
            </div>
            <div>
              <dt>normalized / unit</dt>
              <dd>
                {String(fragment.extracted.normalized_value ?? "—")}{" "}
                {fragment.extracted.unit ?? ""}
              </dd>
            </div>
            <div>
              <dt>polygon_norm</dt>
              <dd>
                <code>{formatPolygon(fragment.polygon_norm)}</code>
              </dd>
            </div>
            <div>
              <dt>bbox (производный)</dt>
              <dd>
                <code>{bbox ? formatBBox(bbox) : "—"}</code>
              </dd>
            </div>
            <div>
              <dt>engine</dt>
              <dd>
                {fragment.extracted.engine} {fragment.extracted.engine_version}{" "}
                {(() => {
                  const chip = confidenceChip(fragment.extracted.confidence);
                  return (
                    <span className={`conf-chip conf-chip--${chip.bucket}`}>{chip.label}</span>
                  );
                })()}
              </dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

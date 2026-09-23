export type EvidenceRole = "expected" | "actual" | "context";

export type Point = [number, number];

export type DocumentRefView = {
  file_id: string;
  file_hash: string;
  doc_stage: "PD" | "RD" | "ID";
  document_code: string;
  revision: string;
  approval_status: "APPROVED" | "NOT_APPROVED" | "UNKNOWN";
  approval_basis?: string;
  sheet?: string;
};

export type ExtractionView = {
  raw_token: string;
  normalized_value?: string | number | boolean | null;
  unit?: string | null;
  engine: string;
  engine_version: string;
  confidence: number;
  grounded_in_source_tokens?: boolean;
  second_read?: { agrees?: boolean; engine?: string; raw_token?: string };
};

export type FragmentView = {
  fragment_id: string;
  role: EvidenceRole;
  document: DocumentRefView;
  page: number;
  polygon_source: Point[];
  polygon_norm: Point[];
  extracted: ExtractionView;
};

export type FindingView = {
  finding_id: string;
  evidence_group_id?: string | null;
  rule_code: string;
  finding_status: string;
  expected_value?: string | number | boolean | null;
  actual_value?: string | number | boolean | null;
  delta?: string | number | null;
  disagreement_kind?: string | null;
  inspector_decision?: {
    inspector_id: string;
    action: string;
    reason_code?: string | null;
    comment?: string | null;
    timestamp: string;
  } | null;
  rationale?: string;
};

export type EvidenceCard = {
  schema_version: "kontur.evidence_card.v1";
  process_id: string;
  finding: FindingView;
  evidence_group: {
    evidence_group_id: string;
    object_id: string;
    rule_code: string;
    matrix_version: string;
    fragments: FragmentView[];
  } | null;
  rule: {
    code: string;
    name?: string;
    unit?: string | null;
    comparator?: {
      operator?: string;
      tolerance_abs?: number | null;
      tolerance_rel?: number | null;
      rounding?: string;
      unit_target?: string | null;
    };
  };
  audit: Array<{
    actor_id: string;
    action: string;
    payload: Record<string, unknown>;
  }>;
  closes_gate_k: false;
};

export type BBox = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export function bboxFromPolygon(polygon: Point[]): BBox {
  if (polygon.length < 3) {
    throw new Error("polygon должен содержать не меньше трёх точек");
  }
  const xs = polygon.map((point) => point[0]);
  const ys = polygon.map((point) => point[1]);
  return {
    x0: Math.min(...xs),
    y0: Math.min(...ys),
    x1: Math.max(...xs),
    y1: Math.max(...ys),
  };
}

export function fragmentByRole(
  card: EvidenceCard,
  role: EvidenceRole,
): FragmentView | undefined {
  return card.evidence_group?.fragments.find((item) => item.role === role);
}

export const STAGE_PANES = ["PD", "RD", "ID"] as const;

export type StagePane = (typeof STAGE_PANES)[number];

export function fragmentByStage(
  card: EvidenceCard,
  stage: StagePane,
): FragmentView | undefined {
  return card.evidence_group?.fragments.find(
    (item) => item.document.doc_stage === stage,
  );
}

export function formatBBox(bbox: BBox): string {
  const fmt = (value: number) => value.toFixed(3);
  return `${fmt(bbox.x0)}, ${fmt(bbox.y0)} → ${fmt(bbox.x1)}, ${fmt(bbox.y1)}`;
}

export function formatPolygon(polygon: Point[]): string {
  return polygon.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(" · ");
}

export function toleranceLabel(card: EvidenceCard): string {
  const comparator = card.rule.comparator;
  if (comparator === undefined) {
    return "допуск не задан";
  }
  const parts = [`оператор ${comparator.operator ?? "—"}`];
  if (comparator.tolerance_abs !== undefined && comparator.tolerance_abs !== null) {
    parts.push(`abs ${comparator.tolerance_abs}`);
  }
  if (comparator.tolerance_rel !== undefined && comparator.tolerance_rel !== null) {
    parts.push(`rel ${comparator.tolerance_rel}`);
  }
  if (comparator.unit_target) {
    parts.push(comparator.unit_target);
  }
  return parts.join(", ");
}

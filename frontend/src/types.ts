export type ReportKind = "roadmap" | "paper_map" | "paper_lens";

export type ResourceLink = {
  title?: string;
  label?: string;
  url?: string;
  href?: string;
  local_href?: string;
  source?: string;
  type?: string;
  language?: string;
  status?: string;
  score?: number;
  trust_score?: number;
  why_recommended?: string;
  concepts?: string[];
  learning_key_points?: string[];
  focus_areas?: string[];
  critical_path_role?: string;
  metadata?: Record<string, unknown>;
};

export type Evidence = {
  source_title?: string;
  resource_title?: string;
  file_name?: string;
  snippet?: string;
  note?: string;
  text?: string;
  local_href?: string;
  href?: string;
  url?: string;
  detail_anchor?: string;
  score?: number;
};

export type PaperMapNode = {
  id: string;
  kind?: string;
  role?: string;
  label?: string;
  kind_label?: string;
  plain_explanation?: string;
  why_it_matters?: string;
  connection?: string;
  talking_point?: string;
  confidence?: number | string;
  evidence?: Evidence[];
  related_resources?: ResourceLink[];
  layout?: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  };
};

export type PaperMapEdge = {
  id?: string;
  from: string;
  to: string;
  label?: string;
  localized_label?: string;
};

export type PaperLensSegment = {
  id: string;
  section_kind?: string;
  section_title?: string;
  original_text?: string;
  unit?: string;
  paragraph_index?: number;
  sentence_count?: number;
  importance_score?: number;
};

export type PaperLensExplanation = {
  id?: string;
  segment_id?: string;
  plain_meaning?: string;
  why_it_matters?: string;
  method_note?: string;
  related_resources?: ResourceLink[] | string[];
  evidence_refs?: Evidence[];
  detail_anchor?: string;
  confidence?: number;
};

export type StudyTask = {
  id?: string;
  type?: string;
  title?: string;
  estimated_minutes?: number;
  evidence?: string;
  acceptance?: string;
  resource_titles?: string[];
  evidence_chunks?: Evidence[];
};

export type PaperSet = {
  mode?: string;
  summary?: {
    paper_count?: number;
    selected_paper_count?: number;
    shared_concept_count?: number;
    purpose?: string;
  };
  papers?: Array<{
    id?: string;
    title?: string;
    selected?: boolean;
    role?: string;
    concepts?: string[];
  }>;
  shared_concepts?: Array<{
    label?: string;
    paper_count?: number;
    paper_ids?: string[];
  }>;
  reading_order?: Array<{
    position?: number;
    paper_id?: string;
    title?: string;
    role?: string;
    reason?: string;
  }>;
  comparison_axes?: Array<{
    id?: string;
    label?: string;
    prompt?: string;
  }>;
  synthesis_tasks?: Array<{
    type?: string;
    title?: string;
    evidence?: string[];
  }>;
};

export type Roadmap = {
  title?: string;
  profile?: {
    goal?: string;
    output_language?: string;
    route_depth?: string;
    learning_style?: string;
  };
  path_strategy?: {
    mode?: string;
    estimated_total_time?: string;
    selected_resources?: number;
    candidate_resources?: number;
  };
  paper_map?: {
    target?: ResourceLink;
    nodes?: PaperMapNode[];
    edges?: PaperMapEdge[];
    source_links?: ResourceLink[];
  };
  paper_lens?: {
    title?: string;
    target?: { title?: string; local_href?: string; url?: string };
    target_papers?: ResourceLink[];
    segments?: PaperLensSegment[];
    inline_explanations?: PaperLensExplanation[];
    sections?: Array<{ kind?: string; title?: string; summary?: string }>;
    reading_recommendations?: Array<{ section_title?: string; summary?: string; resources?: ResourceLink[] }>;
    explanation_summary?: { language?: string; density?: string; granularity?: string };
    latex_export?: { pdf_file?: string; tex_file?: string; compile_status?: string };
  };
  paper_set?: PaperSet;
  phases?: Array<{
    name?: string;
    objective?: string;
    estimated_time?: string;
    resources?: ResourceLink[];
  }>;
  study_tasks?: StudyTask[];
  study_bundle?: {
    manifest_file?: string;
    links_file?: string;
    readme_file?: string;
    manifest_href?: string;
    links_href?: string;
    readme_href?: string;
    retry_href?: string;
    download_queue_href?: string;
    download_manager?: {
      download_queue_file?: string;
      retry_file?: string;
      completed?: number;
      retryable?: number;
      failed?: number;
      total?: number;
      retry_note?: string;
    };
    summary?: Record<string, number | string>;
    resources?: ResourceLink[];
  };
  resource_library?: ResourceLink[];
  outputs?: string[];
};

export type ReportPayload = {
  reportKind?: ReportKind;
  roadmap?: Roadmap;
};

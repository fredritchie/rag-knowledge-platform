export type Page<T> = { items: T[]; page: { limit: number; offset: number; total: number } };

export type Document = {
  id: string;
  filename: string;
  source: string;
  status: string;
  owner_id: string;
  current_version_id?: string;
  content_type: string;
  created_at: string;
  updated_at: string;
};

export type Source = {
  document_id: string;
  filename: string;
  page: number;
  chunk_id: string;
  score: number;
};

export type Answer = {
  answer: string;
  sources: Source[];
  model: string;
  prompt_version: string;
  latency_ms: number;
};

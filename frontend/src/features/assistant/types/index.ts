// Response shape from POST /api/v1/ai/coo
export interface CooResponse {
  answer: string;
  tools_used: string[];
  data: Record<string, unknown>;
}

export interface CooMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolsUsed?: string[];
  data?: Record<string, unknown>;
  error?: boolean;
}

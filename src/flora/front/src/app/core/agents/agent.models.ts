import { OperatorArtifact, PendingApproval } from '../llm/llm.models';

export type AgentId = 'analyst' | 'qc' | 'taxonomist' | 'reporter';

export interface AgentDefinition {
  id: AgentId;
  name: string;
  icon: string;
  role: string;
  description: string;
  tools: string[];
  starters: string[];
}

export interface AgentStep {
  tool: string;
  label: string;
  detail: string;
  status: 'running' | 'done' | 'error';
  ms: number;
}

/** A change the agent proposes; nothing is applied until the researcher confirms. */
export interface AgentAction {
  id: string;
  label: string;
  icon: string;
  path: string;
  queryParams?: Record<string, string | number>;
  applied: boolean;
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'agent';
  agentId?: AgentId;
  text: string;
  steps?: AgentStep[];
  actions?: AgentAction[];
  pending?: boolean;
  /** Written by the tool-calling LLM operator (not the deterministic agents). */
  operator?: boolean;
  /** Charts, tables, maps and shortcuts the operator's tools produced. Not persisted (they can be large). */
  artifacts?: OperatorArtifact[];
  /** Actions waiting for the researcher; `decided` records the answer per call id. */
  approvals?: PendingApproval[];
  decided?: Record<string, 'approved' | 'rejected'>;
  /** Optional LLM reading of the deterministic result. Never counted as evidence. */
  llm?: { status: 'pending' | 'ok' | 'error'; model?: string; text?: string; error?: string; ms?: number };
  at: Date;
}

export interface AgentRun {
  id: string;
  agentId: AgentId;
  prompt: string;
  startedAt: Date;
  status: 'running' | 'done' | 'failed';
  steps: AgentStep[];
  summary: string;
  actions: AgentAction[];
}

export interface AgentReply {
  agentId: AgentId;
  text: string;
  steps: AgentStep[];
  actions: AgentAction[];
}

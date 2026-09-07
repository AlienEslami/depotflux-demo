'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRightLeft,
  BatteryCharging,
  BusFront,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  FileCheck2,
  Menu,
  Play,
  ShieldCheck,
  Waypoints,
  Zap,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

type DemoInput = {
  reference: string;
  sha256: string;
  fleet_size: number;
  charger_count: number;
  trip_count: number;
  horizon_intervals: number;
  interval_minutes: number;
};

type Run = {
  id: string;
  status: string;
  run_type: 'day_ahead' | 'real_time';
  input_reference: string;
  scenario_ids: string[];
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  recovery_count: number;
  last_recovered_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
};

type RunResult = {
  run_id: string;
  status: string;
  solver_name: string | null;
  result_sha256: string | null;
  result: {
    validation?: { passed?: boolean; checks?: string[] };
    optimized_steps?: number;
    current_timestep?: number;
    pto_daily_cost?: number;
    aggregator_revenue?: number;
    total_kwh_bought?: number;
    total_kwh_sold?: number;
    w_buy?: number[];
    w_sell?: number[];
    service_unmet_count?: number;
    soc_violation_count?: number;
    comparison?: {
      baseline_run_id: string;
      changed_intervals: number;
      baseline: ComparisonMetrics;
      candidate: ComparisonMetrics;
      delta: ComparisonMetrics;
    };
  } | null;
  failure_code: string | null;
  failure_message: string | null;
};

type Approval = {
  id: string;
  decision: 'approved' | 'rejected';
  decided_by: string;
  result_sha256: string;
  note: string | null;
  created_at: string;
};

type ControlPolicyCheck = {
  code: string;
  label: string;
  passed: boolean;
  detail: string;
};

type ControlSimulation = {
  id: string;
  run_id: string | null;
  interval_index: number | null;
  command_id: string;
  correlation_id: string;
  action: 'dispatch' | 'safe_state';
  decision: 'accepted' | 'rejected' | 'failed';
  reason_code: string;
  reason_message: string;
  setpoint_kw: number | null;
  modbus_frame_hex: string | null;
  response_frame_hex: string | null;
  policy_checks: ControlPolicyCheck[];
  controller_response: {
    measured_site_power_kw?: number;
    controller_state?: string;
    alarm_state?: number;
    heartbeat?: number;
    transport_attempts?: number;
  } | null;
  simulated_only: true;
  requested_by: string;
  completed_at: string;
};

type ControlPolicyRejection = {
  reason_code: string;
  reason_message: string;
  policy_checks: ControlPolicyCheck[];
  interval_index: number | null;
  run_id: string | null;
  correlation_id: string;
};

type SecurityEvent = {
  id: string;
  event_type: string;
  severity: string;
  correlation_id: string;
  outcome: string;
  reason_code: string;
  occurred_at: string;
};

type AuditEvent = {
  event_type: string;
  occurred_at: string;
  actor: string;
  detail: string;
};

type ComparisonMetrics = {
  remaining_cost: number;
  grid_purchase_kwh: number;
  v2g_export_kwh: number;
  peak_import_kwh: number;
};

type NoticeScenario =
  | 'late_return'
  | 'charger_derating'
  | 'combined_disruption'
  | 'site_power_isolation';

type FailureDrillType = 'infeasible' | 'solver_timeout';

type OperationalNotice = {
  id: string;
  baseline_run_id: string;
  candidate_run_id: string;
  scenario: NoticeScenario;
  source: 'simulator';
  raw_notice: string;
  structured_facts: {
    observed_at_timestep?: number;
    late_returns?: Array<{ bus_id: number; delay_minutes: number }>;
    charger_deratings?: Array<{
      charger_id: number;
      from_kw: number;
      to_kw: number;
      start_timestep: number;
      end_timestep: number;
    }>;
  };
  interpretation_backend: 'rule';
  confidence: number;
  replan_recommended: boolean;
  rationale: string;
  created_by: string;
  created_at: string;
};

type WebMcpDocument = Document & {
  modelContext?: {
    registerTool: (
      tool: {
        name: string;
        title: string;
        description: string;
        inputSchema: object;
        annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
        execute: (input: unknown) => Promise<unknown>;
      },
      options: { signal: AbortSignal },
    ) => void | Promise<void>;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';
const TERMINAL_STATUSES = new Set([
  'succeeded',
  'failed',
  'infeasible',
  'timed_out',
  'cancelled',
  'degraded',
]);

const navigation = [
  { label: 'Operations', icon: CircleGauge, active: true },
  { label: 'Disruption desk', icon: AlertTriangle },
  { label: 'OT security', icon: ShieldCheck },
  { label: 'Run queue', icon: Waypoints },
  { label: 'Data sets', icon: Database },
  { label: 'Audit', icon: FileCheck2 },
];

function shortRunId(id: string) {
  return id.slice(0, 8).toUpperCase();
}

function displayStatus(status: string) {
  return status.replaceAll('_', ' ');
}

function statusBadgeClass(status: string) {
  if (status === 'succeeded') return 'border-emerald-400/25 text-emerald-300';
  if (status === 'running') return 'border-cyan-400/25 text-cyan-300';
  if (status === 'queued') return 'border-blue-400/25 text-blue-300';
  if (status === 'cancel_requested') return 'border-amber-400/25 text-amber-200';
  if (status === 'degraded') return 'border-orange-400/25 text-orange-200';
  if (status === 'cancelled') return 'border-slate-400/25 text-slate-300';
  return 'border-rose-400/25 text-rose-200';
}

function formatNumber(value: number | undefined, digits = 1) {
  return value === undefined
    ? '—'
    : new Intl.NumberFormat('en-CA', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value);
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat('en-CA', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value));
}

function formatModbusFrame(value: string) {
  return value.match(/.{1,2}/g)?.join(' ') ?? value;
}

export default function Home() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [inputs, setInputs] = useState<DemoInput[]>([]);
  const [selectedReference, setSelectedReference] = useState('');
  const [v2gEnabled, setV2gEnabled] = useState(true);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [knownApprovals, setKnownApprovals] = useState<Record<string, Approval | null>>({});
  const [notice, setNotice] = useState<OperationalNotice | null>(null);
  const [noticeScenario, setNoticeScenario] = useState<NoticeScenario>('combined_disruption');
  const [failureDrill, setFailureDrill] = useState<FailureDrillType>('infeasible');
  const [timeline, setTimeline] = useState<AuditEvent[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [decisionNote, setDecisionNote] = useState('');
  const [deciding, setDeciding] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [drilling, setDrilling] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [controlKey, setControlKey] = useState('');
  const [controlInterval, setControlInterval] = useState('1');
  const [controlRecords, setControlRecords] = useState<ControlSimulation[]>([]);
  const [controlRejection, setControlRejection] = useState<ControlPolicyRejection | null>(null);
  const [securityEvents, setSecurityEvents] = useState<SecurityEvent[]>([]);
  const [dispatching, setDispatching] = useState<'accepted' | 'rejected' | null>(null);
  const [message, setMessage] = useState('');

  const selectedInput = useMemo(
    () => inputs.find((item) => item.reference === selectedReference),
    [inputs, selectedReference],
  );
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );
  const chartData = useMemo(() => {
    const buy = runResult?.result?.w_buy ?? [];
    const sell = runResult?.result?.w_sell ?? [];
    const startStep = runResult?.result?.current_timestep ?? 1;
    return buy.map((value, index) => ({
      time: `${String(Math.floor(((startStep - 1 + index) * 30) / 60)).padStart(2, '0')}:${(startStep - 1 + index) % 2 ? '30' : '00'}`,
      charging: Number(value.toFixed(2)),
      v2g: Number((sell[index] ?? 0).toFixed(2)),
    }));
  }, [runResult]);
  const validationPassed = runResult?.result?.validation?.passed === true;
  const approvedRuns = useMemo(
    () => runs.filter(
      (run) => run.status === 'succeeded' && knownApprovals[run.id]?.decision === 'approved',
    ),
    [knownApprovals, runs],
  );
  const controlIntervals = useMemo(
    () => (runResult?.result?.w_buy ?? []).map((_, index) => index + 1),
    [runResult],
  );
  const controlEligible =
    selectedRun?.status === 'succeeded'
    && approval?.decision === 'approved'
    && validationPassed;
  const selectedRunControlRecords = controlRecords.filter(
    (record) => record.run_id === selectedRunId,
  );
  const selectedControlRecord =
    selectedRunControlRecords.find(
      (record) => record.interval_index === Number(controlInterval) && record.decision === 'accepted',
    )
    ?? selectedRunControlRecords.find((record) => record.decision === 'accepted')
    ?? null;
  const selectedControlRejection =
    controlRejection?.run_id === selectedRunId ? controlRejection : null;
  const refreshWorkspace = useCallback(async () => {
    try {
      const [healthResponse, inputResponse, runResponse] = await Promise.all([
        fetch(`${API_BASE}/health/ready`),
        fetch(`${API_BASE}/api/v1/inputs`),
        fetch(`${API_BASE}/api/v1/runs?limit=5&offset=0`),
      ]);
      if (!healthResponse.ok || !inputResponse.ok || !runResponse.ok) {
        throw new Error('The application service is not ready.');
      }
      const inputBody = (await inputResponse.json()) as { items: DemoInput[] };
      const runBody = (await runResponse.json()) as { items: Run[] };
      const approvalEntries = await Promise.all(
        runBody.items.map(async (run): Promise<[string, Approval | null]> => {
          if (run.status !== 'succeeded') return [run.id, null];
          try {
            const response = await fetch(`${API_BASE}/api/v1/runs/${run.id}/approval`);
            return [run.id, response.ok ? ((await response.json()) as Approval) : null];
          } catch {
            return [run.id, null];
          }
        }),
      );
      setInputs(inputBody.items);
      setRuns(runBody.items);
      setKnownApprovals(Object.fromEntries(approvalEntries));
      setSelectedReference((current) => current || inputBody.items[0]?.reference || '');
      setSelectedRunId((current) => current || runBody.items[0]?.id || '');
      setConnected(true);
      setMessage('');
    } catch {
      setConnected(false);
      setMessage('Start the API and worker to enable live optimization.');
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refreshWorkspace(), 0);
    return () => window.clearTimeout(initialRefresh);
  }, [refreshWorkspace]);

  const loadRun = useCallback(async (runId: string) => {
    try {
      const runResponse = await fetch(`${API_BASE}/api/v1/runs/${runId}`);
      if (!runResponse.ok) throw new Error('Run could not be refreshed.');
      const run = (await runResponse.json()) as Run;
      setRuns((current) => [
        run,
        ...current.filter((item) => item.id !== run.id),
      ]);

      const timelineResponse = await fetch(`${API_BASE}/api/v1/runs/${runId}/timeline`);
      if (timelineResponse.ok) {
        const body = (await timelineResponse.json()) as { events: AuditEvent[] };
        setTimeline(body.events);
      }
      const noticeResponse = await fetch(`${API_BASE}/api/v1/runs/${runId}/notice`);
      setNotice(
        noticeResponse.ok
          ? ((await noticeResponse.json()) as OperationalNotice)
          : null,
      );

      if (TERMINAL_STATUSES.has(run.status)) {
        const [resultResponse, approvalResponse] = await Promise.all([
          fetch(`${API_BASE}/api/v1/runs/${runId}/result`),
          fetch(`${API_BASE}/api/v1/runs/${runId}/approval`),
        ]);
        const loadedApproval = approvalResponse.ok
          ? ((await approvalResponse.json()) as Approval)
          : null;
        setRunResult(resultResponse.ok ? ((await resultResponse.json()) as RunResult) : null);
        setApproval(loadedApproval);
        setKnownApprovals((current) => ({ ...current, [runId]: loadedApproval }));
      } else {
        setRunResult(null);
        setApproval(null);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Run refresh failed.');
    }
  }, []);

  useEffect(() => {
    if (!selectedRunId || !connected) return;
    const initialRefresh = window.setTimeout(() => void loadRun(selectedRunId), 0);
    const poller = window.setInterval(() => void loadRun(selectedRunId), 2500);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(poller);
    };
  }, [selectedRunId, connected, loadRun]);

  const queueRun = useCallback(async (input: DemoInput, allowV2g: boolean) => {
    const response = await fetch(`${API_BASE}/api/v1/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        'X-Operator-ID': 'demonstrator-operator',
      },
      body: JSON.stringify({
        run_type: 'day_ahead',
        optimization_mode: 'selfish',
        input_reference: input.reference,
        input_sha256: input.sha256,
        v2g_enabled: allowV2g,
        agent_backend: 'rule',
        scenario_ids: ['nominal'],
      }),
    });
    if (!response.ok) {
      const error = (await response.json()) as { message?: string };
      throw new Error(error.message ?? 'The run could not be submitted.');
    }
    const created = (await response.json()) as Run;
    setRuns((current) => [created, ...current.filter((run) => run.id !== created.id)]);
    setSelectedRunId(created.id);
    return created;
  }, []);

  const queueFailureDrill = useCallback(async (
    input: DemoInput,
    drillType: FailureDrillType,
  ) => {
    const response = await fetch(`${API_BASE}/api/v1/failure-drills`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        'X-Operator-ID': 'demonstrator-operator',
      },
      body: JSON.stringify({
        input_reference: input.reference,
        input_sha256: input.sha256,
        drill_type: drillType,
      }),
    });
    if (!response.ok) {
      const error = (await response.json()) as { message?: string };
      throw new Error(error.message ?? 'The failure drill could not be queued.');
    }
    const created = (await response.json()) as Run;
    setRuns((current) => [created, ...current.filter((run) => run.id !== created.id)]);
    setSelectedRunId(created.id);
    return created;
  }, []);

  const queueReplan = useCallback(async (
    baselineRunId: string,
    scenario: NoticeScenario,
  ) => {
    const response = await fetch(`${API_BASE}/api/v1/notices/simulate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        'X-Operator-ID': 'demonstrator-operator',
      },
      body: JSON.stringify({ baseline_run_id: baselineRunId, scenario }),
    });
    if (!response.ok) {
      const error = (await response.json()) as { message?: string };
      throw new Error(error.message ?? 'The operational notice could not be submitted.');
    }
    const createdNotice = (await response.json()) as OperationalNotice;
    const runResponse = await fetch(
      `${API_BASE}/api/v1/runs/${createdNotice.candidate_run_id}`,
    );
    if (!runResponse.ok) throw new Error('The replanning run could not be loaded.');
    const candidate = (await runResponse.json()) as Run;
    setNotice(createdNotice);
    setRuns((current) => [candidate, ...current.filter((run) => run.id !== candidate.id)]);
    setSelectedRunId(candidate.id);
    return createdNotice;
  }, []);

  async function submitRun() {
    if (!selectedInput) return;
    setSubmitting(true);
    setMessage('');
    try {
      const created = await queueRun(selectedInput, v2gEnabled);
      setMessage(`Run ${shortRunId(created.id)} entered the durable queue.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Submission failed.');
    } finally {
      setSubmitting(false);
    }
  }

  async function submitDecision(decision: 'approved' | 'rejected') {
    if (!selectedRunId) return;
    setDeciding(true);
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/runs/${selectedRunId}/approval`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Operator-ID': 'demonstrator-operator',
        },
        body: JSON.stringify({ decision, note: decisionNote || null }),
      });
      if (!response.ok) {
        const error = (await response.json()) as { message?: string };
        throw new Error(error.message ?? 'The decision could not be recorded.');
      }
      const recorded = (await response.json()) as Approval;
      setApproval(recorded);
      setDecisionOpen(false);
      setMessage(`Candidate ${recorded.decision}; immutable audit record created.`);
      await loadRun(selectedRunId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Decision failed.');
    } finally {
      setDeciding(false);
    }
  }

  async function simulateDisruption() {
    if (!selectedRunId || approval?.decision !== 'approved') return;
    setSimulating(true);
    setMessage('');
    try {
      const createdNotice = await queueReplan(selectedRunId, noticeScenario);
      setMessage(
        `Operational notice preserved; run ${shortRunId(createdNotice.candidate_run_id)} entered the queue.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Simulation failed.');
    } finally {
      setSimulating(false);
    }
  }

  async function submitFailureDrill() {
    if (!selectedInput) return;
    setDrilling(true);
    setMessage('');
    try {
      const created = await queueFailureDrill(selectedInput, failureDrill);
      setMessage(
        `Controlled ${displayStatus(failureDrill)} drill ${shortRunId(created.id)} entered the queue.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Failure drill submission failed.');
    } finally {
      setDrilling(false);
    }
  }

  async function cancelSelectedRun() {
    if (!selectedRunId) return;
    setCancelling(true);
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/runs/${selectedRunId}/cancel`, {
        method: 'POST',
        headers: { 'X-Operator-ID': 'demonstrator-operator' },
      });
      if (!response.ok) {
        const error = (await response.json()) as { message?: string };
        throw new Error(error.message ?? 'The run could not be cancelled.');
      }
      const cancelled = (await response.json()) as Run;
      setRuns((current) => [
        cancelled,
        ...current.filter((run) => run.id !== cancelled.id),
      ]);
      setMessage(
        cancelled.status === 'cancel_requested'
          ? 'Cancellation recorded; the worker will discard any late solver result.'
          : 'Run cancelled before optimization began.',
      );
      await loadRun(selectedRunId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Cancellation failed.');
    } finally {
      setCancelling(false);
    }
  }

  async function simulateControlCommand(expectRejection: boolean) {
    if (!selectedRunId || !controlEligible || !controlKey || !controlIntervals.length) return;
    const intervalIndex = expectRejection
      ? controlIntervals.length + 1
      : Number(controlInterval);
    setDispatching(expectRejection ? 'rejected' : 'accepted');
    setControlRejection(null);
    setMessage('');
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/runs/${selectedRunId}/dispatch-simulations`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Control-Key': controlKey,
            'X-Operator-ID': 'ot-supervisor-demo',
          },
          body: JSON.stringify({ interval_index: intervalIndex }),
        },
      );
      const body = (await response.json()) as ControlSimulation | { message?: string };
      if (expectRejection) {
        if (response.status !== 409) {
          throw new Error(
            response.ok
              ? 'The negative test was unexpectedly accepted.'
              : ('message' in body ? body.message : undefined) ?? 'The negative test failed unexpectedly.',
          );
        }
        const rejected = body as ControlSimulation;
        setControlRejection({
          reason_code: rejected.reason_code,
          reason_message: rejected.reason_message,
          policy_checks: rejected.policy_checks,
          correlation_id: rejected.correlation_id,
          interval_index: intervalIndex,
          run_id: selectedRunId,
        });
        setMessage(`Policy correctly rejected interval ${intervalIndex}; no Modbus frame reached the controller.`);
        return;
      }
      if (!response.ok) {
        throw new Error(('message' in body ? body.message : undefined) ?? 'Control simulation failed.');
      }
      const created = body as ControlSimulation;
      const listResponse = await fetch(
        `${API_BASE}/api/v1/runs/${selectedRunId}/dispatch-simulations`,
        { headers: { 'X-Control-Key': controlKey } },
      );
      if (listResponse.ok) {
        const list = (await listResponse.json()) as { items: ControlSimulation[] };
        setControlRecords(list.items);
      } else {
        setControlRecords((current) => [
          ...current.filter((item) => item.id !== created.id),
          created,
        ]);
      }
      const eventResponse = await fetch(`${API_BASE}/api/v1/security/events?limit=8`);
      if (eventResponse.ok) {
        const events = (await eventResponse.json()) as { items: SecurityEvent[] };
        setSecurityEvents(events.items);
      }
      setMessage(
        `Interval ${created.interval_index} traversed the software-only gateway and synthetic Modbus/TCP controller.`,
      );
      await loadRun(selectedRunId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Control simulation failed.');
    } finally {
      setDispatching(null);
    }
  }

  useEffect(() => {
    const context = (document as WebMcpDocument).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'queue_optimization_run',
          title: 'Queue optimization run',
          description: 'Queue a nominal day-ahead optimization for one registered demo input.',
          inputSchema: {
            type: 'object',
            properties: {
              input_reference: { type: 'string' },
              v2g_enabled: { type: 'boolean' },
            },
            required: ['input_reference', 'v2g_enabled'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          async execute(value) {
            const input = value as { input_reference?: unknown; v2g_enabled?: unknown };
            if (typeof input.input_reference !== 'string' || typeof input.v2g_enabled !== 'boolean') {
              throw new Error('input_reference and v2g_enabled are required.');
            }
            const demoInput = inputs.find((item) => item.reference === input.input_reference);
            if (!demoInput) throw new Error('The requested demo input is not registered.');
            const created = await queueRun(demoInput, input.v2g_enabled);
            return { run_id: created.id, status: created.status };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [inputs, queueRun]);

  useEffect(() => {
    const context = (document as WebMcpDocument).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'queue_failure_drill',
          title: 'Queue failure drill',
          description: 'Queue a controlled infeasible-model or solver-timeout drill using a registered demo input.',
          inputSchema: {
            type: 'object',
            properties: {
              input_reference: { type: 'string' },
              drill_type: {
                type: 'string',
                enum: ['infeasible', 'solver_timeout'],
              },
            },
            required: ['input_reference', 'drill_type'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          async execute(value) {
            const input = value as { input_reference?: unknown; drill_type?: unknown };
            const drillTypes = new Set(['infeasible', 'solver_timeout']);
            if (
              typeof input.input_reference !== 'string'
              || typeof input.drill_type !== 'string'
              || !drillTypes.has(input.drill_type)
            ) {
              throw new Error('A registered input_reference and supported drill_type are required.');
            }
            const demoInput = inputs.find((item) => item.reference === input.input_reference);
            if (!demoInput) throw new Error('The requested demo input is not registered.');
            const created = await queueFailureDrill(
              demoInput,
              input.drill_type as FailureDrillType,
            );
            return { run_id: created.id, status: created.status, drill_type: input.drill_type };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [inputs, queueFailureDrill]);

  useEffect(() => {
    const context = (document as WebMcpDocument).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'cancel_optimization_run',
          title: 'Cancel optimization run',
          description: 'Cancel a queued run or request cancellation of a running optimization.',
          inputSchema: {
            type: 'object',
            properties: { run_id: { type: 'string' } },
            required: ['run_id'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          async execute(value) {
            const input = value as { run_id?: unknown };
            if (typeof input.run_id !== 'string' || !input.run_id) {
              throw new Error('run_id is required.');
            }
            const response = await fetch(`${API_BASE}/api/v1/runs/${input.run_id}/cancel`, {
              method: 'POST',
              headers: { 'X-Operator-ID': 'demonstrator-operator' },
            });
            if (!response.ok) {
              const error = (await response.json()) as { message?: string };
              throw new Error(error.message ?? 'The run could not be cancelled.');
            }
            const cancelled = (await response.json()) as Run;
            setRuns((current) => [
              cancelled,
              ...current.filter((run) => run.id !== cancelled.id),
            ]);
            setSelectedRunId(cancelled.id);
            return { run_id: cancelled.id, status: cancelled.status };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  useEffect(() => {
    const context = (document as WebMcpDocument).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'simulate_operational_notice',
          title: 'Simulate operational notice',
          description: 'Preserve a frozen depot disruption and queue a remaining-horizon optimization from an approved baseline.',
          inputSchema: {
            type: 'object',
            properties: {
              baseline_run_id: { type: 'string' },
              scenario: {
                type: 'string',
                enum: ['late_return', 'charger_derating', 'combined_disruption', 'site_power_isolation'],
              },
            },
            required: ['baseline_run_id', 'scenario'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          async execute(value) {
            const input = value as { baseline_run_id?: unknown; scenario?: unknown };
            const scenarios = new Set(['late_return', 'charger_derating', 'combined_disruption', 'site_power_isolation']);
            if (typeof input.baseline_run_id !== 'string' || typeof input.scenario !== 'string' || !scenarios.has(input.scenario)) {
              throw new Error('A baseline_run_id and supported scenario are required.');
            }
            const created = await queueReplan(
              input.baseline_run_id,
              input.scenario as NoticeScenario,
            );
            return {
              notice_id: created.id,
              candidate_run_id: created.candidate_run_id,
              replan_recommended: created.replan_recommended,
            };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [queueReplan]);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 flex h-16 items-center border-b border-white/8 bg-background/92 px-4 backdrop-blur-xl lg:px-7">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
            <Menu />
          </Button>
          <div className="grid size-9 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10 text-cyan-300">
            <Zap className="size-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold tracking-[-0.02em]">DepotFlux</p>
            <p className="text-xs text-muted-foreground">Electric fleet energy operations</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={
              connected
                ? 'border-emerald-400/25 bg-emerald-400/8 text-emerald-300'
                : 'border-amber-400/25 bg-amber-400/8 text-amber-300'
            }
          >
            <span className={`mr-1.5 size-1.5 rounded-full ${connected ? 'bg-emerald-300' : 'bg-amber-300'}`} />
            {connected === null ? 'Checking service' : connected ? 'Service ready' : 'Local service offline'}
          </Badge>
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium">Demo operator</p>
            <p className="text-xs text-muted-foreground">Temporary identity</p>
          </div>
          <div className="grid size-9 place-items-center rounded-full bg-slate-700 text-sm font-semibold">DO</div>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-[1600px] lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-white/8 px-4 py-6 lg:block">
          <nav aria-label="Primary navigation" className="space-y-1">
            {navigation.map(({ label, icon: Icon, active }) => (
              <button
                key={label}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                  active
                    ? 'bg-cyan-300/10 font-medium text-cyan-100'
                    : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                }`}
                type="button"
              >
                <Icon className="size-4" />
                {label}
              </button>
            ))}
          </nav>
          <div className="mt-10 border-t border-white/8 pt-5">
            <p className="px-3 text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">Operating boundary</p>
            <div className="mt-3 flex gap-3 rounded-xl border border-white/8 bg-white/[0.025] p-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-cyan-300" />
              <p className="text-xs leading-5 text-slate-400">Human approval only. No direct control of buses or chargers.</p>
            </div>
          </div>
        </aside>

        <div className="grid min-w-0 gap-5 p-4 xl:grid-cols-[minmax(0,1fr)_340px] xl:p-7">
          <section className="min-w-0 space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm text-cyan-300">Depot A · Operations desk</p>
                <h1 className="mt-1 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">Plan, respond, and approve</h1>
              </div>
              <p className="font-mono text-xs text-muted-foreground">48 × 30 MIN · RULE BACKEND</p>
            </div>

            <Card className="border-white/10 bg-card/80 shadow-2xl shadow-black/15">
              <CardHeader className="border-b border-white/8 pb-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan-300">New optimization run</p>
                    <CardTitle className="mt-1 text-lg">Frozen operational scenario</CardTitle>
                  </div>
                  <Badge variant="outline" className="border-white/10 text-muted-foreground">Selfish objective</Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-5 pt-5 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-end">
                <div className="grid gap-2 text-sm font-medium">
                  <label htmlFor="fleet-data-set">Fleet data set</label>
                  <Select
                    value={selectedReference}
                    onValueChange={(value) => {
                      if (value) setSelectedReference(value);
                    }}
                    disabled={!inputs.length}
                  >
                    <SelectTrigger id="fleet-data-set" className="w-full border-white/10 bg-background/60">
                      <SelectValue placeholder="Waiting for registered inputs" />
                    </SelectTrigger>
                    <SelectContent>
                      {inputs.map((input) => (
                        <SelectItem key={input.reference} value={input.reference}>
                          Depot A · {input.fleet_size} buses
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex h-9 items-center justify-between rounded-lg border border-white/10 bg-background/60 px-3">
                  <span className="text-sm font-medium">V2G enabled</span>
                  <Switch checked={v2gEnabled} onCheckedChange={setV2gEnabled} aria-label="Enable vehicle-to-grid discharge" />
                </div>
                <Button
                  className="bg-cyan-300 font-semibold text-slate-950 hover:bg-cyan-200"
                  disabled={!connected || !selectedInput || submitting}
                  onClick={submitRun}
                >
                  <Play className="size-4 fill-current" />
                  {submitting ? 'Submitting…' : 'Queue run'}
                </Button>
              </CardContent>
              <div className="grid border-t border-white/8 sm:grid-cols-3">
                {[
                  { label: 'Buses', value: selectedInput?.fleet_size ?? '—', Icon: BusFront },
                  { label: 'Chargers', value: selectedInput?.charger_count ?? '—', Icon: BatteryCharging },
                  { label: 'Service trips', value: selectedInput?.trip_count ?? '—', Icon: Waypoints },
                ].map(({ label, value, Icon }, index) => (
                  <div key={label} className={`flex items-center gap-3 px-5 py-4 ${index ? 'border-t border-white/8 sm:border-l sm:border-t-0' : ''}`}>
                    <Icon className="size-4 text-cyan-300" />
                    <div>
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="font-mono text-lg font-semibold">{value}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="border-rose-300/15 bg-card/80 shadow-2xl shadow-black/15">
              <CardHeader className="border-b border-white/8 pb-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-rose-300">Resilience verification</p>
                    <CardTitle className="mt-1 text-lg">Run a controlled failure drill</CardTitle>
                  </div>
                  <Badge variant="outline" className="border-rose-300/20 text-rose-200">
                    Never approvable
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-5 pt-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <div className="grid gap-2 text-sm font-medium">
                  <label htmlFor="failure-drill">Expected terminal state</label>
                  <Select
                    value={failureDrill}
                    onValueChange={(value) => {
                      if (value) setFailureDrill(value as FailureDrillType);
                    }}
                  >
                    <SelectTrigger id="failure-drill" className="w-full border-white/10 bg-background/60">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="infeasible">Infeasible · initial SOC below hard minimum</SelectItem>
                      <SelectItem value="solver_timeout">Timed out · 1 ms solver budget</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs font-normal leading-5 text-muted-foreground">
                    These frozen drills exercise the real mathematical model and durable failure states. No result can reach operator approval.
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="border-rose-300/25 text-rose-100 hover:bg-rose-300/10"
                  disabled={!connected || !selectedInput || drilling}
                  onClick={submitFailureDrill}
                >
                  <AlertTriangle className="size-4" />
                  {drilling ? 'Submitting…' : 'Queue failure drill'}
                </Button>
              </CardContent>
            </Card>

            <Card className="border-amber-300/15 bg-card/80 shadow-2xl shadow-black/15">
              <CardHeader className="border-b border-white/8 pb-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-300">Operational replanning</p>
                    <CardTitle className="mt-1 text-lg">Simulate a depot disruption</CardTitle>
                  </div>
                  <Badge variant="outline" className="border-amber-300/20 text-amber-200">
                    Approved baseline required
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-5 pt-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <div className="grid gap-2 text-sm font-medium">
                  <label htmlFor="notice-scenario">Frozen operational notice</label>
                  <Select
                    value={noticeScenario}
                    onValueChange={(value) => {
                      if (value) setNoticeScenario(value as NoticeScenario);
                    }}
                  >
                    <SelectTrigger id="notice-scenario" className="w-full border-white/10 bg-background/60">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="late_return">Bus 1 · 30-minute late return</SelectItem>
                      <SelectItem value="charger_derating">Charger 1 · temporary 150 kW limit</SelectItem>
                      <SelectItem value="combined_disruption">Combined late return + charger derating</SelectItem>
                      <SelectItem value="site_power_isolation">Failure drill · all charging power unavailable</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs font-normal leading-5 text-muted-foreground">
                    The simulator preserves the source notice, applies deterministic interpretation, and queues a real remaining-horizon solve.
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="border-amber-300/25 text-amber-100 hover:bg-amber-300/10"
                  disabled={!connected || approval?.decision !== 'approved' || simulating}
                  onClick={simulateDisruption}
                >
                  <AlertTriangle className="size-4" />
                  {simulating ? 'Submitting…' : 'Simulate and replan'}
                </Button>
              </CardContent>
              <div className="border-t border-white/8 px-5 py-3 text-xs text-muted-foreground">
                {approval?.decision === 'approved'
                  ? `Baseline RUN-${shortRunId(selectedRunId)} is approved and eligible for replanning.`
                  : 'Select and approve a successful candidate to establish the operating baseline.'}
              </div>
            </Card>

            <Card className="overflow-hidden border-cyan-300/20 bg-gradient-to-br from-cyan-300/[0.065] via-card/90 to-card/80 shadow-2xl shadow-black/20">
              <CardHeader className="border-b border-white/8 pb-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-300/10">
                      <ShieldCheck className="size-5 text-cyan-300" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan-300">OT security evidence</p>
                      <CardTitle className="mt-1 text-lg">Secure dispatch simulation</CardTitle>
                    </div>
                  </div>
                  <Badge variant="outline" className="border-emerald-300/20 text-emerald-200">
                    Software-only TCP path
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-6 pt-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
                <div className="space-y-4">
                  <div className="grid gap-2 text-sm font-medium">
                    <label htmlFor="control-run">Approved run</label>
                    <Select
                      value={approvedRuns.some((run) => run.id === selectedRunId) ? selectedRunId : ''}
                      onValueChange={(value) => {
                        if (value) setSelectedRunId(value);
                      }}
                    >
                      <SelectTrigger id="control-run" className="w-full border-white/10 bg-background/60">
                        <SelectValue placeholder="Select an approved run" />
                      </SelectTrigger>
                      <SelectContent>
                        {approvedRuns.map((run) => (
                          <SelectItem key={run.id} value={run.id}>
                            RUN-{shortRunId(run.id)} · {displayStatus(run.run_type)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2 text-sm font-medium">
                    <label htmlFor="control-interval">Schedule interval</label>
                    <Select
                      value={controlInterval}
                      onValueChange={(value) => {
                        if (value) setControlInterval(value);
                      }}
                      disabled={!controlEligible || !controlIntervals.length}
                    >
                      <SelectTrigger id="control-interval" className="w-full border-white/10 bg-background/60">
                        <SelectValue placeholder="Select an interval" />
                      </SelectTrigger>
                      <SelectContent>
                        {controlIntervals.map((interval) => (
                          <SelectItem key={interval} value={String(interval)}>
                            Interval {interval} · {String(Math.floor(((interval - 1) * 30) / 60)).padStart(2, '0')}:{(interval - 1) % 2 ? '30' : '00'}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2 text-sm font-medium">
                    <label htmlFor="control-key">Session-only control key</label>
                    <input
                      id="control-key"
                      type="password"
                      autoComplete="off"
                      value={controlKey}
                      onChange={(event) => setControlKey(event.target.value)}
                      placeholder="Enter the locally configured key"
                      className="h-9 w-full rounded-lg border border-white/10 bg-background/60 px-3 text-sm outline-none transition placeholder:text-muted-foreground focus:border-cyan-300/45 focus:ring-2 focus:ring-cyan-300/15"
                    />
                    <p className="text-xs font-normal leading-5 text-muted-foreground">
                      Kept only in this page session. It is never stored in the dashboard or audit record.
                    </p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Button
                      disabled={!controlEligible || !controlKey || dispatching !== null}
                      onClick={() => void simulateControlCommand(false)}
                    >
                      <ShieldCheck className="size-4" />
                      {dispatching === 'accepted' ? 'Dispatching…' : 'Dispatch to simulator'}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={!controlEligible || !controlKey || dispatching !== null}
                      className="border-rose-300/25 text-rose-100 hover:bg-rose-300/10"
                      onClick={() => void simulateControlCommand(true)}
                    >
                      <AlertTriangle className="size-4" />
                      {dispatching === 'rejected' ? 'Testing…' : 'Demonstrate rejection'}
                    </Button>
                  </div>
                  <p className="rounded-lg border border-white/8 bg-black/10 px-3 py-2.5 text-xs leading-5 text-slate-400">
                    The rejection test requests interval {controlIntervals.length ? controlIntervals.length + 1 : '—'}, outside the optimized horizon. The API must refuse it before encoding.
                  </p>
                </div>

                <div className="min-w-0 rounded-xl border border-white/8 bg-[#07101a]/75 p-4">
                  {selectedControlRejection ? (
                    <div className="rounded-lg border border-rose-300/20 bg-rose-300/[0.055] p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-rose-100">Command rejected by policy</p>
                        <Badge variant="outline" className="border-rose-300/25 text-rose-200">BLOCKED</Badge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-300">{selectedControlRejection.reason_message}</p>
                      <div className="mt-3 grid gap-2 font-mono text-xs text-rose-200/75 sm:grid-cols-2">
                        <span>CHECK {selectedControlRejection.reason_code}</span>
                        <span>INTERVAL {selectedControlRejection.interval_index}</span>
                      </div>
                      <p className="mt-2 break-all font-mono text-[11px] text-slate-500">CORRELATION {selectedControlRejection.correlation_id}</p>
                    </div>
                  ) : selectedControlRecord ? (
                    <div className="space-y-5">
                      <div className="flex flex-wrap items-end justify-between gap-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Encoded setpoint</p>
                          <p className="mt-1 font-mono text-3xl font-semibold text-cyan-200">
                            {formatNumber(selectedControlRecord.setpoint_kw ?? undefined, 1)} <span className="text-base text-muted-foreground">kW</span>
                          </p>
                        </div>
                        <p className="font-mono text-xs text-slate-500">OT-DISPATCH-POLICY-V1</p>
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Policy checks</p>
                        <ul className="mt-3 space-y-3">
                          {selectedControlRecord.policy_checks.map((check) => (
                            <li key={check.code} className="flex gap-3">
                              {check.passed
                                ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-300" />
                                : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-300" />}
                              <div>
                                <p className="text-sm font-medium text-slate-200">{check.label}</p>
                                <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{check.detail}</p>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Generated Modbus/TCP frame</p>
                          <Badge variant="outline" className="border-white/10 text-slate-400">SIMULATED</Badge>
                        </div>
                        <code className="mt-3 block break-all rounded-lg border border-cyan-300/10 bg-cyan-300/[0.04] p-3 font-mono text-sm leading-6 text-cyan-100">
                          {selectedControlRecord.modbus_frame_hex
                            ? formatModbusFrame(selectedControlRecord.modbus_frame_hex)
                            : 'No frame generated'}
                        </code>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Controller {displayStatus(selectedControlRecord.controller_response?.controller_state ?? 'unknown')}
                          {' · '}measured {formatNumber(selectedControlRecord.controller_response?.measured_site_power_kw, 1)} kW
                          {' · '}heartbeat {selectedControlRecord.controller_response?.heartbeat ?? '—'}
                        </p>
                        <p className="mt-2 break-all font-mono text-[11px] text-slate-500">CORRELATION {selectedControlRecord.correlation_id}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="grid min-h-72 place-items-center text-center">
                      <div className="max-w-sm">
                        <FileCheck2 className="mx-auto size-7 text-slate-500" />
                        <p className="mt-3 text-sm font-medium">No control evidence selected</p>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">
                          Select an approved run, choose an interval, and evaluate it against the OT policy gate.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
              <div className="border-t border-white/8 px-5 py-3 text-xs text-muted-foreground">
                {controlEligible
                  ? `RUN-${shortRunId(selectedRunId)} is approved, hash-bound, and eligible for software-only dispatch.`
                  : 'Only a successful, validated, operator-approved run can reach the supervisory gateway.'}
              </div>
            </Card>

            {securityEvents.length ? (
              <Card className="border-white/10 bg-card/80">
                <CardHeader className="border-b border-white/8 pb-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Structured monitoring evidence</p>
                  <CardTitle className="mt-1 text-lg">Recent OT security events</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-white/8">
                    {securityEvents.map((event) => (
                      <div key={event.id} className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_auto]">
                        <div>
                          <p className="text-sm font-medium capitalize">{displayStatus(event.event_type)}</p>
                          <p className="mt-1 font-mono text-xs text-muted-foreground">{event.reason_code} · {event.correlation_id.slice(0, 12)}</p>
                        </div>
                        <Badge variant="outline" className={event.outcome === 'accepted' ? 'border-emerald-300/20 text-emerald-200' : 'border-rose-300/20 text-rose-200'}>
                          {event.severity} · {event.outcome}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {message ? (
              <output className="block rounded-lg border border-cyan-300/15 bg-cyan-300/5 px-4 py-3 text-sm text-cyan-100">
                {message}
              </output>
            ) : null}

            {notice ? (
              <Card className="border-amber-300/15 bg-gradient-to-br from-amber-300/[0.055] to-card/80">
                <CardHeader className="border-b border-white/8 pb-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-300">Preserved source notice</p>
                      <CardTitle className="mt-1 text-lg capitalize">{displayStatus(notice.scenario)}</CardTitle>
                    </div>
                    <Badge variant="outline" className="border-emerald-300/20 text-emerald-200">
                      Rule confidence {Math.round(notice.confidence * 100)}%
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-5 pt-5 lg:grid-cols-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Original message</p>
                    <blockquote className="mt-2 border-l-2 border-amber-300/35 pl-4 text-sm leading-6 text-slate-200">
                      {notice.raw_notice}
                    </blockquote>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Decision rationale</p>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{notice.rationale}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(notice.structured_facts.late_returns ?? []).map((item) => (
                        <Badge key={`bus-${item.bus_id}`} variant="outline" className="border-white/10 text-slate-300">
                          Bus {item.bus_id} +{item.delay_minutes} min
                        </Badge>
                      ))}
                      {(notice.structured_facts.charger_deratings ?? []).map((item) => (
                        <Badge key={`charger-${item.charger_id}`} variant="outline" className="border-white/10 text-slate-300">
                          Charger {item.charger_id} {item.from_kw}→{item.to_kw} kW
                        </Badge>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {runResult?.result?.comparison ? (
              <Card className="border-cyan-300/15 bg-card/80">
                <CardHeader className="border-b border-white/8 pb-4">
                  <div className="flex items-center gap-3">
                    <ArrowRightLeft className="size-5 text-cyan-300" />
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Candidate versus approved baseline</p>
                      <CardTitle className="mt-1 text-lg">
                        {runResult.result.comparison.changed_intervals} intervals revised
                      </CardTitle>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-px overflow-hidden p-0 sm:grid-cols-4">
                  {[
                    ['Remaining cost', runResult.result.comparison.delta.remaining_cost, '$'],
                    ['Grid purchase', runResult.result.comparison.delta.grid_purchase_kwh, ' kWh'],
                    ['V2G export', runResult.result.comparison.delta.v2g_export_kwh, ' kWh'],
                    ['Peak import', runResult.result.comparison.delta.peak_import_kwh, ' kWh'],
                  ].map(([label, value, unit], index) => {
                    const numericValue = value as number;
                    return (
                      <div key={label as string} className={`p-5 ${index ? 'border-t border-white/8 sm:border-l sm:border-t-0' : ''}`}>
                        <p className="text-xs text-muted-foreground">{label as string} delta</p>
                        <p className={`mt-2 font-mono text-lg font-semibold ${numericValue > 0 ? 'text-amber-200' : numericValue < 0 ? 'text-emerald-300' : 'text-slate-200'}`}>
                          {unit === '$' ? `${numericValue >= 0 ? '+' : ''}$${formatNumber(numericValue, 2)}` : `${numericValue >= 0 ? '+' : ''}${formatNumber(numericValue, 1)}${unit as string}`}
                        </p>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            ) : null}

            <Card className="border-white/10 bg-card/80">
              <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-white/8 pb-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Durable queue</p>
                  <CardTitle className="mt-1 text-lg">Recent runs</CardTitle>
                </div>
                <Button variant="ghost" size="sm" onClick={() => void refreshWorkspace()}>
                  <Activity className="size-4" /> Refresh
                </Button>
              </CardHeader>
              <CardContent className="p-0">
                {runs.length ? (
                  <div className="divide-y divide-white/8">
                    {runs.map((run) => (
                      <button
                        key={run.id}
                        type="button"
                        onClick={() => setSelectedRunId(run.id)}
                        aria-pressed={run.id === selectedRunId}
                        className={`grid w-full grid-cols-[1fr_auto_auto] items-center gap-4 px-5 py-4 text-left transition ${
                          run.id === selectedRunId
                            ? 'bg-cyan-300/[0.065]'
                            : 'hover:bg-white/[0.025]'
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="font-mono text-sm font-semibold">RUN-{shortRunId(run.id)}</p>
                          <p className="truncate text-xs capitalize text-muted-foreground">{displayStatus(run.run_type)} · {run.input_reference}</p>
                        </div>
                        <Badge
                          variant="outline"
                          className={`capitalize ${statusBadgeClass(run.status)}`}
                        >
                          {displayStatus(run.status)}
                        </Badge>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="grid min-h-44 place-items-center px-6 py-10 text-center">
                    <div>
                      <Clock3 className="mx-auto size-6 text-slate-500" />
                      <p className="mt-3 text-sm font-medium">No recorded runs</p>
                      <p className="mt-1 text-sm text-muted-foreground">Connect the service and queue the first frozen scenario.</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {timeline.length ? (
              <Card className="border-white/10 bg-card/80">
                <CardHeader className="border-b border-white/8 pb-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Audit trail</p>
                  <CardTitle className="mt-1 text-lg">Run timeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-5">
                  <ol className="space-y-5">
                    {timeline.map((event, index) => (
                      <li key={`${event.event_type}-${event.occurred_at}`} className="grid grid-cols-[18px_1fr_auto] gap-3">
                        <div className="relative flex justify-center">
                          <span className="mt-1.5 size-2 rounded-full bg-cyan-300" />
                          {index < timeline.length - 1 ? <span className="absolute top-4 h-[calc(100%+0.7rem)] w-px bg-white/10" /> : null}
                        </div>
                        <div>
                          <p className="text-sm font-medium capitalize">{displayStatus(event.event_type)}</p>
                          <p className="mt-0.5 text-sm text-muted-foreground">{event.detail}</p>
                          <p className="mt-1 font-mono text-xs text-slate-500">{event.actor}</p>
                        </div>
                        <time className="font-mono text-xs text-muted-foreground">{formatTimestamp(event.occurred_at)}</time>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>
            ) : null}
          </section>

          <aside className="space-y-5">
            <Card className="border-white/10 bg-gradient-to-b from-slate-800/90 to-slate-900/90">
              <CardHeader>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Candidate readiness</p>
                <CardTitle className="text-lg">
                  {approval
                    ? `Candidate ${approval.decision}`
                    : validationPassed
                      ? 'Ready for operator review'
                      : selectedRun
                        ? `Run ${displayStatus(selectedRun.status)}`
                        : 'Awaiting a solved run'}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative mb-5 h-44 overflow-hidden rounded-xl border border-white/8 bg-[#07101a] p-2">
                  {chartData.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 8, right: 5, left: -25, bottom: 0 }}>
                        <defs>
                          <linearGradient id="charging-fill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#67e8f9" stopOpacity={0.34} />
                            <stop offset="100%" stopColor="#67e8f9" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="rgba(148,163,184,.11)" vertical={false} />
                        <XAxis dataKey="time" tick={{ fill: '#718996', fontSize: 10 }} interval={11} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fill: '#718996', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          contentStyle={{ background: '#0d1a26', border: '1px solid rgba(255,255,255,.1)', borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: '#8ca2ad' }}
                        />
                        <Area type="monotone" dataKey="charging" name="Charge kWh" stroke="#67e8f9" fill="url(#charging-fill)" strokeWidth={2} />
                        <Area type="monotone" dataKey="v2g" name="V2G kWh" stroke="#fbbf24" fill="transparent" strokeWidth={1.5} />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <svg viewBox="0 0 300 140" className="h-full w-full" aria-hidden="true">
                      {[28, 56, 84, 112].map((y) => <line key={y} x1="0" x2="300" y1={y} y2={y} stroke="rgba(148,163,184,.12)" />)}
                      <path d="M0 105 C36 102 45 90 78 93 S128 44 162 54 208 90 240 59 276 37 300 41" fill="none" stroke="rgba(103,232,249,.35)" strokeWidth="2" strokeDasharray="5 6" />
                    </svg>
                  )}
                </div>
                {runResult?.result ? (
                  <div className="mb-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/8 bg-white/8">
                    {[
                      [selectedRun?.run_type === 'real_time' ? 'Remaining cost' : 'PTO cost', `$${formatNumber(runResult.result.pto_daily_cost, 2)}`],
                      ['Aggregator value', `$${formatNumber(runResult.result.aggregator_revenue, 2)}`],
                      ['Grid purchase', `${formatNumber(runResult.result.total_kwh_bought)} kWh`],
                      ['V2G export', `${formatNumber(runResult.result.total_kwh_sold)} kWh`],
                    ].map(([label, value]) => (
                      <div key={label} className="bg-[#0d1a26] p-3">
                        <p className="text-xs text-muted-foreground">{label}</p>
                        <p className="mt-1 font-mono text-sm font-semibold">{value}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="space-y-3 text-sm">
                  {[
                    ['Input hash verified', Boolean(selectedRun)],
                    ['Deterministic validation', validationPassed],
                    ['Human decision recorded', Boolean(approval)],
                  ].map(([label, ready]) => (
                    <div key={label as string} className="flex items-center justify-between gap-4">
                      <span className="text-slate-300">{label as string}</span>
                      {ready ? <CheckCircle2 className="size-4 text-emerald-300" /> : <span className="font-mono text-xs text-slate-500">PENDING</span>}
                    </div>
                  ))}
                </div>
                {runResult?.failure_message ? (
                  <div className="mt-5 rounded-lg border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">
                    <p>{runResult.failure_message}</p>
                    {runResult.failure_code ? (
                      <p className="mt-1 font-mono text-xs text-rose-300/70">{runResult.failure_code}</p>
                    ) : null}
                  </div>
                ) : null}
                {selectedRun?.recovery_count ? (
                  <p className="mt-5 rounded-lg border border-blue-400/20 bg-blue-400/5 p-3 text-sm text-blue-200">
                    Worker recovery completed {selectedRun.recovery_count} time{selectedRun.recovery_count === 1 ? '' : 's'}; the run remained durable.
                  </p>
                ) : null}
                {selectedRun && ['queued', 'running', 'cancel_requested'].includes(selectedRun.status) ? (
                  <Button
                    variant="outline"
                    disabled={cancelling || selectedRun.status === 'cancel_requested'}
                    className="mt-6 w-full border-amber-300/25 text-amber-100 hover:bg-amber-300/10"
                    onClick={cancelSelectedRun}
                  >
                    {selectedRun.status === 'cancel_requested'
                      ? 'Cancellation pending'
                      : cancelling
                        ? 'Cancelling…'
                        : 'Cancel run'}
                  </Button>
                ) : null}
                <Button
                  disabled={!validationPassed || Boolean(approval)}
                  className="mt-3 w-full"
                  onClick={() => setDecisionOpen(true)}
                >
                  {approval ? 'Decision recorded' : 'Review candidate'}
                </Button>
              </CardContent>
            </Card>

            {approval ? (
              <Card className={approval.decision === 'approved' ? 'border-emerald-300/20 bg-emerald-300/[0.04]' : 'border-rose-300/20 bg-rose-300/[0.04]'}>
                <CardContent className="pt-5">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className={`mt-0.5 size-5 ${approval.decision === 'approved' ? 'text-emerald-300' : 'text-rose-300'}`} />
                    <div>
                      <p className="text-sm font-semibold capitalize">Candidate {approval.decision}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{approval.note || 'No operator note supplied.'}</p>
                      <p className="mt-3 font-mono text-xs text-slate-500">{approval.decided_by} · {formatTimestamp(approval.created_at)}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            <Card className="border-amber-300/15 bg-amber-300/[0.035]">
              <CardContent className="flex gap-3 pt-5">
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-amber-300" />
                <div>
                  <p className="text-sm font-semibold text-amber-100">Decision support, not control</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">Approval creates an audit record. It never dispatches commands to physical assets.</p>
                </div>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>

      <Dialog open={decisionOpen} onOpenChange={setDecisionOpen}>
        <DialogContent className="border-white/10 bg-[#0d1a26] sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Record operator decision</DialogTitle>
            <DialogDescription>
              This decision is immutable and bound to result hash {runResult?.result_sha256?.slice(0, 12) ?? '—'}.
              It does not dispatch a charger command.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="decision-note">
              Decision note <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <Textarea
              id="decision-note"
              value={decisionNote}
              onChange={(event) => setDecisionNote(event.target.value)}
              placeholder="Record the operational reason for this decision."
              maxLength={1000}
              className="min-h-24 border-white/10 bg-background/60"
            />
          </div>
          <DialogFooter className="gap-2 sm:justify-between">
            <Button variant="outline" disabled={deciding} onClick={() => void submitDecision('rejected')}>
              Reject candidate
            </Button>
            <Button disabled={deciding} onClick={() => void submitDecision('approved')}>
              {deciding ? 'Recording…' : 'Approve candidate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

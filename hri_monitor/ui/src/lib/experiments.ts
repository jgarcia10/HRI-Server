import { useCallback, useEffect, useRef, useState } from "react";

export type Condition = { id: number; name: string; order_index: number };
export type MarkerLabel = { id: number; label: string };
export type Experiment = {
  id: number; name: string; description: string;
  conditions: Condition[]; marker_labels: MarkerLabel[];
};
export type Participant = { id: number; code: string; notes: string };
export type Marker = { id: number; t_offset: number; label: string; source: string };
export type Recording = {
  id: number; condition_id: number; started_at: number; stopped_at: number | null;
  sample_count: number; status: string; marker_count?: number;
};
export type Session = {
  id: number; participant_id: number; started_at: number; recordings: Recording[];
};
export type ActiveStatus = {
  recording_id: number; session_id: number; condition: string;
  elapsed: number; sample_count: number; markers: Marker[];
} | null;

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  return r.json();
}
const post = (url: string, body?: unknown) =>
  j(url, { method: "POST", headers: { "Content-Type": "application/json" },
           body: body ? JSON.stringify(body) : undefined });

export const api = {
  listExperiments: () => j<Experiment[]>("/api/experiments"),
  getExperiment: (id: number) => j<Experiment>(`/api/experiments/${id}`),
  createExperiment: (name: string, description = "") =>
    post("/api/experiments", { name, description }) as Promise<{ id: number }>,
  deleteExperiment: (id: number) => fetch(`/api/experiments/${id}`, { method: "DELETE" }),
  setConditions: (id: number, conditions: string[]) =>
    fetch(`/api/experiments/${id}/conditions`, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conditions }) }),
  setMarkerLabels: (id: number, labels: string[]) =>
    fetch(`/api/experiments/${id}/marker-labels`, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ labels }) }),
  listParticipants: (id: number) => j<Participant[]>(`/api/experiments/${id}/participants`),
  createParticipant: (id: number, code: string, notes = "") =>
    post(`/api/experiments/${id}/participants`, { code, notes }) as Promise<{ id: number }>,
  deleteParticipant: (pid: number) => fetch(`/api/participants/${pid}`, { method: "DELETE" }),
  listSessions: (id: number) => j<Session[]>(`/api/experiments/${id}/sessions`),
  deleteSession: (sid: number) => fetch(`/api/sessions/${sid}`, { method: "DELETE" }),
  deleteRecording: (rid: number) => fetch(`/api/recordings/${rid}`, { method: "DELETE" }),
  start: (body: { condition_id: number; experiment_id?: number; participant_id?: number; session_id?: number }) =>
    post("/api/recordings/start", body),
  marker: (recId: number, label: string, source: string) =>
    post(`/api/recordings/${recId}/marker`, { label, source }),
  stop: (recId: number) => post(`/api/recordings/${recId}/stop`),
};

export function useExperiments() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const refresh = useCallback(async () => setExperiments(await api.listExperiments()), []);
  useEffect(() => { refresh(); }, [refresh]);
  return { experiments, refresh };
}

export function useExperiment(id: number | null) {
  const [exp, setExp] = useState<Experiment | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const refresh = useCallback(async () => {
    if (id == null) { setExp(null); setParticipants([]); return; }
    setExp(await api.getExperiment(id));
    setParticipants(await api.listParticipants(id));
  }, [id]);
  useEffect(() => { refresh(); }, [refresh]);
  return { exp, participants, refresh };
}

export function useActiveRecording() {
  const [active, setActive] = useState<ActiveStatus>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    let stopped = false;
    const loop = async () => {
      try { setActive(await j<ActiveStatus>("/api/recordings/active")); } catch { /* keep */ }
      if (!stopped) timer.current = setTimeout(loop, 1000);
    };
    loop();
    return () => { stopped = true; if (timer.current) clearTimeout(timer.current); };
  }, []);
  return active;
}

export type Mode = "4stems" | "6stems";

export interface Job {
  id: string;
  name: string;
  mode: Mode;
  status: "queued" | "extracting" | "processing" | "encoding" | "analyzing" | "done" | "error";
  progress: number;
  error: string | null;
  stems: string[];
  analysis: { bpm: number | null; time_signature: string | null } | null;
}

/** Upload with XHR so we get upload progress events. */
export function createJob(
  file: File,
  mode: Mode,
  onUpload: (fraction: number) => void,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.upload.onprogress = (e) => e.lengthComputable && onUpload(e.loaded / e.total);
    xhr.onload = () => {
      const body = safeJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
      else reject(new Error(body?.detail ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Can't reach the server. Is the backend running?"));
    xhr.send(form);
  });
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${id}`);
  if (!res.ok) throw new Error(`Job lookup failed (${res.status})`);
  return res.json();
}

export async function waitForJob(
  id: string,
  onUpdate: (job: Job) => void,
): Promise<Job> {
  for (;;) {
    const job = await getJob(id);
    onUpdate(job);
    if (job.status === "done") return job;
    if (job.status === "error") throw new Error(job.error ?? "Separation failed");
    await new Promise((r) => setTimeout(r, 1000));
  }
}

export const stemUrl = (jobId: string, stem: string) =>
  `/api/jobs/${jobId}/stems/${stem}.mp3`;

function safeJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const incoming = await request.formData();
    const resume = incoming.get("resume") as File;
    const jobId = incoming.get("job_id") as string;
    if (!resume || !jobId) {
      return NextResponse.json({ error: "resume and job_id are required" }, { status: 400 });
    }

    const form = new FormData();
    form.append("resume", resume, resume.name);
    form.append("job_id", jobId);

    const response = await fetch(`${BACKEND_URL}/api/v1/outreach/draft`, {
      method: "POST",
      body: form,
    });
    const data = await response.json().catch(() => ({ detail: "Backend error" }));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Failed to draft outreach email" },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error("Outreach draft API error:", error);
    return NextResponse.json({ error: "Cannot connect to outreach backend" }, { status: 502 });
  }
}

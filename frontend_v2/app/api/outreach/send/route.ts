import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const incoming = await request.formData();
    const resume = incoming.get("resume") as File;
    if (!resume) {
      return NextResponse.json({ error: "resume is required" }, { status: 400 });
    }

    const form = new FormData();
    for (const key of ["job_id", "recipient", "subject", "body", "approved"]) {
      const value = incoming.get(key);
      if (value !== null) form.append(key, String(value));
    }
    form.append("resume", resume, resume.name);

    const response = await fetch(`${BACKEND_URL}/api/v1/outreach/send`, {
      method: "POST",
      body: form,
    });
    const data = await response.json().catch(() => ({ detail: "Backend error" }));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Failed to send outreach email" },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error("Outreach send API error:", error);
    return NextResponse.json({ error: "Cannot connect to outreach backend" }, { status: 502 });
  }
}

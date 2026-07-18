import { NextRequest, NextResponse } from "next/server";

/**
 * API Route: /api/advise
 * ======================
 * Accepts a PDF resume upload + job_id, forwards both to the Python
 * FastAPI backend, and returns AI-powered resume improvement advice.
 *
 * Environment:
 *   BACKEND_URL — Python backend base URL (default: http://localhost:8000)
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("resume") as File;
    const jobId = formData.get("job_id") as string;

    if (!file) {
      return NextResponse.json(
        { error: "Resume file is required" },
        { status: 400 }
      );
    }

    if (!jobId) {
      return NextResponse.json(
        { error: "job_id is required" },
        { status: 400 }
      );
    }

    // Forward to Python backend
    const pythonForm = new FormData();
    pythonForm.append("resume", file, file.name);
    pythonForm.append("job_id", jobId);

    const res = await fetch(`${BACKEND_URL}/api/v1/advise`, {
      method: "POST",
      body: pythonForm,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Backend error" }));
      return NextResponse.json(
        { error: errorData.detail || `Backend returned ${res.status}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Advice API error:", error);
    const message =
      error instanceof TypeError && error.message.includes("fetch")
        ? "Cannot connect to backend. Is the Python API running on port 8000?"
        : "Internal server error";
    return NextResponse.json(
      { error: message },
      { status: 502 }
    );
  }
}

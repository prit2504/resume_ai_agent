import { NextRequest, NextResponse } from "next/server";

/**
 * API Route: /api/match
 * =====================
 * Accepts a PDF resume upload from the frontend, forwards it to
 * the Python FastAPI backend, and returns matched jobs + resume profile.
 *
 * Environment:
 *   BACKEND_URL — Python backend base URL (default: http://localhost:8000)
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("resume") as File;
    const topK = formData.get("top_k") as string || "10";
    const filters = formData.get("filters") as string | null;

    if (!file || file.type !== "application/pdf") {
      return NextResponse.json(
        { error: "Please upload a valid PDF resume" },
        { status: 400 }
      );
    }

    // Forward to Python backend
    const pythonForm = new FormData();
    pythonForm.append("resume", file, file.name);
    pythonForm.append("top_k", topK);
    if (filters) {
      pythonForm.append("filters", filters);
    }

    const res = await fetch(`${BACKEND_URL}/api/v1/match`, {
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
    console.error("Match API error:", error);
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

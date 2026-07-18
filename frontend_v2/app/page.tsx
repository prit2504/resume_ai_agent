"use client";

/**
 * LinkedIn Job Matcher — Next.js Frontend
 * ========================================
 * Interactive dashboard for resume upload, job matching,
 * and AI-powered resume improvement suggestions.
 *
 * Tech Stack:
 *   - Next.js 16 (App Router)
 *   - React 19
 *   - TypeScript
 *   - Tailwind CSS v4
 *   - shadcn/ui components
 *   - Framer Motion animations
 *   - Recharts for analytics
 *
 * Setup:
 *   npx create-next-app@latest job-matcher-ui --typescript --tailwind --app
 *   cd job-matcher-ui
 *   npx shadcn@latest init
 *   npx shadcn add button card badge tabs dialog input textarea separator scroll-area avatar skeleton
 *   npm install framer-motion lucide-react recharts
 */

import React, { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase,
  MapPin,
  DollarSign,
  Users,
  Clock,
  ExternalLink,
  Upload,
  FileText,
  Sparkles,
  TrendingUp,
  Award,
  BookOpen,
  Code,
  Zap,
  ChevronRight,
  Star,
  Target,
  Lightbulb,
  AlertTriangle,
  CheckCircle2,
  X,
  Search,
  Filter,
  Building2,
  Globe,
  GraduationCap,
  Wrench,
  BarChart3,
  ArrowUpRight,
  Download,
  RefreshCw,
  Brain,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Cell,
} from "recharts";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

interface JobPosting {
  job_id: string;
  company: string | null;
  title: string | null;
  location: string | null;
  work_type: string | null;
  employment_type: string | null;
  easy_apply: boolean;
  posted_at: string | null;
  applicants_count: number | null;
  skills: string[];
  tools_technologies: string[];
  required_experience: string | null;
  seniority_level: string | null;
  salary_range: string | null;
  description: string;
  linkedin_url: string;
}

interface MatchedJob {
  job: JobPosting;
  similarity_score: number;
  match_reasons: string[];
}

interface ResumeAdvice {
  job_id: string;
  job_title: string | null;
  company: string | null;
  overall_score: number;
  summary_suggestions: string[];
  skills_to_add: string[];
  skills_to_emphasize: string[];
  project_suggestions: string[];
  experience_gaps: string[];
  certification_suggestions: string[];
  tailored_summary: string | null;
}

interface ResumeProfile {
  name: string | null;
  email: string | null;
  skills: string[];
  tools_technologies: string[];
  experience_years: number | null;
  seniority_level: string | null;
  target_roles: string[];
  summary: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Mock Data (Replace with API calls in production)
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_JOBS: MatchedJob[] = [
  {
    job: {
      job_id: "4172359372",
      company: "OpenAI",
      title: "Senior Machine Learning Engineer",
      location: "San Francisco, CA (Remote)",
      work_type: "hybrid",
      employment_type: "full-time",
      easy_apply: false,
      posted_at: "2026-07-17T10:00:00Z",
      applicants_count: 234,
      skills: ["Python", "PyTorch", "Transformers", "MLOps", "CUDA"],
      tools_technologies: ["Kubernetes", "AWS", "Weights & Biases", "Ray"],
      required_experience: "5-8 years",
      seniority_level: "mid_senior",
      salary_range: "$180k - $250k",
      description:
        "We are seeking a Senior ML Engineer to lead training infrastructure for large language models. You will optimize distributed training pipelines, implement novel architectures, and collaborate with research teams to productionize cutting-edge AI.",
      linkedin_url: "https://www.linkedin.com/jobs/view/4172359372",
    },
    similarity_score: 0.94,
    match_reasons: ["Strong PyTorch experience", "MLOps background", "Distributed systems"],
  },
  {
    job: {
      job_id: "4172359380",
      company: "Anthropic",
      title: "AI Safety Research Engineer",
      location: "Remote",
      work_type: "remote",
      employment_type: "full-time",
      easy_apply: true,
      posted_at: "2026-07-16T14:30:00Z",
      applicants_count: 89,
      skills: ["Python", "Machine Learning", "RLHF", "Interpretability", "PyTorch"],
      tools_technologies: ["JAX", "TPU", "HuggingFace", "Modal"],
      required_experience: "3-5 years",
      seniority_level: "mid_senior",
      salary_range: "$200k - $300k",
      description:
        "Join our AI safety team to develop robust evaluation frameworks and alignment techniques for Claude. Work on mechanistic interpretability, red-teaming, and scalable oversight.",
      linkedin_url: "https://www.linkedin.com/jobs/view/4172359380",
    },
    similarity_score: 0.91,
    match_reasons: ["AI safety interest", "PyTorch expertise", "Research background"],
  },
  {
    job: {
      job_id: "4172359401",
      company: "Stripe",
      title: "Staff Machine Learning Engineer — Fraud",
      location: "Seattle, WA",
      work_type: "onsite",
      employment_type: "full-time",
      easy_apply: false,
      posted_at: "2026-07-15T09:00:00Z",
      applicants_count: 156,
      skills: ["Python", "Scala", "Spark", "Fraud Detection", "Real-time Systems"],
      tools_technologies: ["Kafka", "Flink", "Snowflake", "Airflow"],
      required_experience: "7+ years",
      seniority_level: "director",
      salary_range: "$220k - $320k",
      description:
        "Lead the ML platform for fraud detection processing billions of transactions. Build real-time inference pipelines, mentor junior engineers, and drive cross-functional strategy.",
      linkedin_url: "https://www.linkedin.com/jobs/view/4172359401",
    },
    similarity_score: 0.87,
    match_reasons: ["Real-time systems experience", "Fraud domain knowledge", "Staff-level readiness"],
  },
  {
    job: {
      job_id: "4172359422",
      company: "Databricks",
      title: "Principal ML Platform Engineer",
      location: "Remote",
      work_type: "remote",
      employment_type: "full-time",
      easy_apply: true,
      posted_at: "2026-07-14T16:00:00Z",
      applicants_count: 312,
      skills: ["Python", "Spark", "MLflow", "Kubernetes", "Terraform"],
      tools_technologies: ["Azure", "Delta Lake", "Ray", "Kubeflow"],
      required_experience: "8+ years",
      seniority_level: "executive",
      salary_range: "$250k - $400k + equity",
      description:
        "Define the future of ML infrastructure on the Databricks platform. Design APIs for model serving, feature stores, and experiment tracking used by thousands of enterprises.",
      linkedin_url: "https://www.linkedin.com/jobs/view/4172359422",
    },
    similarity_score: 0.85,
    match_reasons: ["Platform engineering", "Kubernetes deep-dive", "ML infrastructure"],
  },
  {
    job: {
      job_id: "4172359455",
      company: "Hugging Face",
      title: "Open Source ML Engineer",
      location: "Paris, France (Remote EU)",
      work_type: "remote",
      employment_type: "full-time",
      easy_apply: true,
      posted_at: "2026-07-18T08:00:00Z",
      applicants_count: 445,
      skills: ["Python", "Transformers", "Open Source", "Community", "NLP"],
      tools_technologies: ["Git", "GitHub Actions", "Docker", "Gradio"],
      required_experience: "2-4 years",
      seniority_level: "mid_senior",
      salary_range: "€90k - €140k",
      description:
        "Build and maintain the Transformers library. Work with the open-source community, implement SOTA models, and create educational content for ML practitioners worldwide.",
      linkedin_url: "https://www.linkedin.com/jobs/view/4172359455",
    },
    similarity_score: 0.82,
    match_reasons: ["Open source contributions", "Transformers library", "Community engagement"],
  },
];

const MOCK_ADVICE: ResumeAdvice = {
  job_id: "4172359372",
  job_title: "Senior Machine Learning Engineer",
  company: "OpenAI",
  overall_score: 0.72,
  summary_suggestions: [
    "Lead with your LLM training experience instead of general ML background",
    "Quantify model size and throughput improvements (e.g., 'optimized 70B parameter model training')",
    "Mention specific distributed training frameworks (DeepSpeed, FSDP, Megatron)",
  ],
  skills_to_add: [
    "Mixed Precision Training (BF16/FP8)",
    "Model Parallelism (Tensor/Pipeline)",
    "Triton Kernel Optimization",
    "RLHF / DPO / PPO",
    "vLLM / TensorRT-LLM",
  ],
  skills_to_emphasize: [
    "PyTorch (highlight custom CUDA ops)",
    "Kubernetes (mention GPU scheduling)",
    "MLOps (CI/CD for model training)",
    "Python (asyncio for high-throughput serving)",
  ],
  project_suggestions: [
    "Build a mini GPT from scratch with distributed training on 4 GPUs",
    "Create a LoRA fine-tuning pipeline with automatic hyperparameter search",
    "Implement KV-cache optimization for inference speedup benchmarking",
    "Contribute to an open-source inference engine (vLLM, llama.cpp)",
  ],
  experience_gaps: [
    "No explicit mention of large-scale distributed training (100+ GPUs)",
    "Missing production model serving at scale (>10k QPS)",
    "No experience with model quantization or distillation",
  ],
  certification_suggestions: [
    "NVIDIA DLI: Fundamentals of Deep Learning",
    "AWS Machine Learning Specialty",
    "Kubernetes CKA/CKAD (for MLOps)",
  ],
  tailored_summary:
    "Senior Machine Learning Engineer with 6+ years architecting distributed training pipelines for large language models. Specialized in PyTorch optimization, GPU cluster orchestration, and production ML systems serving 10M+ daily inference requests. Proven track record reducing training costs by 40% through mixed-precision and model-parallel strategies. Seeking to advance frontier AI training infrastructure at OpenAI.",
};

const MOCK_RESUME: ResumeProfile = {
  name: "Alex Chen",
  email: "alex.chen@email.com",
  skills: [
    "Python",
    "PyTorch",
    "TensorFlow",
    "Kubernetes",
    "Docker",
    "AWS",
    "SQL",
    "Machine Learning",
    "Deep Learning",
    "MLOps",
  ],
  tools_technologies: [
    "Git",
    "Jenkins",
    "Terraform",
    "Prometheus",
    "Grafana",
    "MLflow",
    "Kubeflow",
  ],
  experience_years: 6,
  seniority_level: "mid_senior",
  target_roles: ["ML Engineer", "MLOps Engineer", "AI Infrastructure"],
  summary:
    "Experienced ML Engineer with strong background in building and deploying machine learning models. Proficient in Python, PyTorch, and cloud infrastructure. Passionate about AI and looking for challenging opportunities.",
};

// ═══════════════════════════════════════════════════════════════════════════════
// UI Components
// ═══════════════════════════════════════════════════════════════════════════════

function Badge({
  children,
  variant = "default",
  className = "",
}: {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "info" | "purple";
  className?: string;
}) {
  const variants = {
    default: "bg-slate-100 text-slate-700 border-slate-200",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warning: "bg-amber-50 text-amber-700 border-amber-200",
    info: "bg-sky-50 text-sky-700 border-sky-200",
    purple: "bg-violet-50 text-violet-700 border-violet-200",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

function Card({
  children,
  className = "",
  hover = false,
}: {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={`bg-white rounded-2xl border border-slate-200/60 shadow-sm ${
        hover ? "hover:shadow-md hover:border-slate-300/80 transition-all duration-300" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

function Button({
  children,
  onClick,
  variant = "primary",
  size = "md",
  disabled = false,
  className = "",
  icon,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "outline";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  className?: string;
  icon?: React.ReactNode;
}) {
  const variants = {
    primary:
      "bg-slate-900 text-white hover:bg-slate-800 active:bg-slate-950 shadow-sm",
    secondary:
      "bg-slate-100 text-slate-900 hover:bg-slate-200 active:bg-slate-300",
    ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
    outline:
      "border border-slate-300 text-slate-700 hover:bg-slate-50 hover:border-slate-400",
  };
  const sizes = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2.5 text-sm",
    lg: "px-6 py-3 text-base",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-xl font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}

function ProgressBar({ value, max = 1, className = "" }: { value: number; max?: number; className?: string }) {
  const pct = Math.min((value / max) * 100, 100);
  const color =
    pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className={`w-full bg-slate-100 rounded-full h-2.5 overflow-hidden ${className}`}>
      <motion.div
        className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 1, ease: "easeOut" }}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Sections
// ═══════════════════════════════════════════════════════════════════════════════

function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-br from-slate-900 to-slate-700 rounded-xl flex items-center justify-center shadow-lg">
            <Briefcase className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 tracking-tight">
              JobMatcher
            </h1>
            <p className="text-xs text-slate-500 -mt-0.5">AI-Powered Career Intelligence</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="info" className="hidden sm:flex">
            <Zap className="w-3 h-3 mr-1" />
            Local AI
          </Badge>
          <div className="w-8 h-8 bg-gradient-to-br from-violet-500 to-purple-600 rounded-full flex items-center justify-center text-white text-xs font-bold">
            AC
          </div>
        </div>
      </div>
    </header>
  );
}

function ResumeUploadSection({
  onUpload,
  resume,
  onReset,
}: {
  onUpload: (file: File) => void;
  resume: ResumeProfile | null;
  onReset?: () => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") {
        onUpload(file);
      }
    },
    [onUpload]
  );

  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <Card className="overflow-hidden">
          <div className="p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-violet-50 rounded-xl flex items-center justify-center">
                <Upload className="w-5 h-5 text-violet-600" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-900">Upload Your Resume</h2>
                <p className="text-sm text-slate-500">
                  We will parse your resume and find the best matching jobs using AI
                </p>
              </div>
            </div>

            {!resume ? (
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-300 ${
                  isDragging
                    ? "border-violet-400 bg-violet-50/50"
                    : "border-slate-300 hover:border-slate-400 bg-slate-50/50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) onUpload(file);
                  }}
                />
                <div className="w-16 h-16 bg-white rounded-2xl shadow-sm border border-slate-200 flex items-center justify-center mx-auto mb-4">
                  <FileText className="w-8 h-8 text-slate-400" />
                </div>
                <p className="text-lg font-semibold text-slate-700 mb-1">
                  Drop your resume here
                </p>
                <p className="text-sm text-slate-500">
                  or click to browse • PDF files only
                </p>
              </div>
            ) : (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-slate-50 rounded-2xl p-6 border border-slate-200/60"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl flex items-center justify-center text-white font-bold text-lg">
                      {resume.name?.charAt(0) || "U"}
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-slate-900">
                        {resume.name}
                      </h3>
                      <p className="text-sm text-slate-500">{resume.email}</p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onReset}
                    icon={<RefreshCw className="w-4 h-4" />}
                  >
                    Re-upload
                  </Button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div className="bg-white rounded-xl p-4 border border-slate-200/60">
                    <div className="flex items-center gap-2 text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">
                      <Clock className="w-3.5 h-3.5" />
                      Experience
                    </div>
                    <p className="text-2xl font-bold text-slate-900">
                      {resume.experience_years}+ years
                    </p>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-slate-200/60">
                    <div className="flex items-center gap-2 text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">
                      <Target className="w-3.5 h-3.5" />
                      Seniority
                    </div>
                    <p className="text-2xl font-bold text-slate-900 capitalize">
                      {resume.seniority_level?.replace("_", "-")}
                    </p>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-slate-200/60">
                    <div className="flex items-center gap-2 text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">
                      <Briefcase className="w-3.5 h-3.5" />
                      Target Roles
                    </div>
                    <p className="text-lg font-bold text-slate-900 truncate">
                      {resume.target_roles.slice(0, 2).join(", ")}
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                      Skills ({resume.skills.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {resume.skills.map((skill) => (
                        <Badge key={skill} variant="purple">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                      Tools & Technologies ({resume.tools_technologies.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {resume.tools_technologies.map((tool) => (
                        <Badge key={tool} variant="info">
                          {tool}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        </Card>
      </motion.div>
    </section>
  );
}

function MatchScoreCard({ score }: { score: number }) {
  const data = [
    { subject: "Skills", A: Math.min(score * 100 + 5, 100), fullMark: 100 },
    { subject: "Experience", A: Math.min(score * 100 - 5, 95), fullMark: 100 },
    { subject: "Tools", A: Math.min(score * 100 + 10, 100), fullMark: 100 },
    { subject: "Seniority", A: Math.min(score * 100, 90), fullMark: 100 },
    { subject: "Location", A: Math.min(score * 100 + 15, 100), fullMark: 100 },
    { subject: "Domain", A: Math.min(score * 100 - 10, 85), fullMark: 100 },
  ];

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: "#64748b", fontSize: 12 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            name="Match"
            dataKey="A"
            stroke="#8b5cf6"
            strokeWidth={2}
            fill="#8b5cf6"
            fillOpacity={0.15}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

function JobCard({
  match,
  index,
  onGetAdvice,
  isAdvising,
}: {
  match: MatchedJob;
  index: number;
  onGetAdvice: (jobId: string) => void;
  isAdvising: boolean;
}) {
  const { job, similarity_score } = match;
  const [expanded, setExpanded] = useState(false);

  const scoreColor =
    similarity_score >= 0.9
      ? "text-emerald-600 bg-emerald-50 border-emerald-200"
      : similarity_score >= 0.8
      ? "text-sky-600 bg-sky-50 border-sky-200"
      : "text-amber-600 bg-amber-50 border-amber-200";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.08 }}
    >
      <Card hover className="overflow-hidden">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-gradient-to-br from-slate-100 to-slate-200 rounded-xl flex items-center justify-center text-xl font-bold text-slate-400 border border-slate-200">
                {job.company?.charAt(0) || "J"}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-bold text-slate-900 leading-tight mb-1">
                  {job.title}
                </h3>
                <div className="flex items-center gap-3 text-sm text-slate-500 flex-wrap">
                  <span className="flex items-center gap-1">
                    <Building2 className="w-3.5 h-3.5" />
                    {job.company}
                  </span>
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5" />
                    {job.location}
                  </span>
                </div>
              </div>
            </div>
            <div className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${scoreColor}`}>
              {(similarity_score * 100).toFixed(0)}% Match
            </div>
          </div>

          {/* Meta */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <Badge variant="default">
              <Globe className="w-3 h-3 mr-1" />
              {job.work_type}
            </Badge>
            <Badge variant="default">
              <Briefcase className="w-3 h-3 mr-1" />
              {job.employment_type}
            </Badge>
            {job.easy_apply && (
              <Badge variant="success">
                <Zap className="w-3 h-3 mr-1" />
                Easy Apply
              </Badge>
            )}
            {job.salary_range && (
              <Badge variant="info">
                <DollarSign className="w-3 h-3 mr-1" />
                {job.salary_range}
              </Badge>
            )}
            <Badge variant="default">
              <Users className="w-3 h-3 mr-1" />
              {job.applicants_count} applicants
            </Badge>
          </div>

          {/* Skills */}
          <div className="mb-4">
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((skill) => (
                <span
                  key={skill}
                  className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>

          {/* Match Reasons */}
          {match.match_reasons.length > 0 && (
            <div className="mb-4 p-3 bg-violet-50/50 rounded-xl border border-violet-100">
              <p className="text-xs font-semibold text-violet-700 uppercase tracking-wider mb-2">
                Why this matches you
              </p>
              <div className="flex flex-wrap gap-2">
                {match.match_reasons.map((reason) => (
                  <span
                    key={reason}
                    className="flex items-center gap-1 text-xs text-violet-700"
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    {reason}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Description */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="overflow-hidden"
              >
                <p className="text-sm text-slate-600 leading-relaxed mb-4">
                  {job.description}
                </p>
                {job.tools_technologies.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                      Tech Stack
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {job.tools_technologies.map((tool) => (
                        <span
                          key={tool}
                          className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-md text-xs"
                        >
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Actions */}
          <div className="flex items-center gap-3 pt-4 border-t border-slate-100">
            <a
              href={job.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#0a66c2] hover:bg-[#084e96] text-white rounded-xl text-sm font-medium transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              Apply on LinkedIn
            </a>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              icon={<ChevronRight className={`w-4 h-4 transition-transform ${expanded ? "rotate-90" : ""}`} />}
            >
              {expanded ? "Less" : "More"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onGetAdvice(job.job_id)}
              disabled={isAdvising}
              icon={<Sparkles className="w-4 h-4" />}
            >
              {isAdvising ? "Analyzing..." : "Get Advice"}
            </Button>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

function AdvicePanel({
  advice,
  onClose,
}: {
  advice: ResumeAdvice;
  onClose: () => void;
}) {
  const sections = [
    {
      icon: <Sparkles className="w-5 h-5 text-violet-600" />,
      title: "Tailored Professional Summary",
      color: "violet",
      content: advice.tailored_summary,
      type: "text",
    },
    {
      icon: <TrendingUp className="w-5 h-5 text-emerald-600" />,
      title: "Summary Improvements",
      color: "emerald",
      items: advice.summary_suggestions,
    },
    {
      icon: <Code className="w-5 h-5 text-sky-600" />,
      title: "Skills to Add",
      color: "sky",
      items: advice.skills_to_add,
    },
    {
      icon: <Star className="w-5 h-5 text-amber-600" />,
      title: "Skills to Emphasize",
      color: "amber",
      items: advice.skills_to_emphasize,
    },
    {
      icon: <Lightbulb className="w-5 h-5 text-purple-600" />,
      title: "Project Suggestions",
      color: "purple",
      items: advice.project_suggestions,
    },
    {
      icon: <AlertTriangle className="w-5 h-5 text-rose-600" />,
      title: "Experience Gaps",
      color: "rose",
      items: advice.experience_gaps,
    },
    {
      icon: <Award className="w-5 h-5 text-indigo-600" />,
      title: "Certifications to Consider",
      color: "indigo",
      items: advice.certification_suggestions,
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, x: 300 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 300 }}
      transition={{ type: "spring", damping: 25, stiffness: 200 }}
      className="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-2xl border-l border-slate-200 z-50 overflow-y-auto"
    >
      <div className="sticky top-0 bg-white/80 backdrop-blur-xl border-b border-slate-200 px-6 py-4 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl flex items-center justify-center">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">AI Resume Advisor</h2>
            <p className="text-sm text-slate-500">
              {advice.job_title} @ {advice.company}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-slate-100 rounded-xl transition-colors"
        >
          <X className="w-5 h-5 text-slate-500" />
        </button>
      </div>

      <div className="p-6 space-y-6">
        {/* Score */}
        <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200/60">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-700">Match Score</span>
            <span className="text-2xl font-bold text-slate-900">
              {(advice.overall_score * 100).toFixed(0)}%
            </span>
          </div>
          <ProgressBar value={advice.overall_score} />
          <p className="text-xs text-slate-500 mt-2">
            {advice.overall_score >= 0.8
              ? "Strong match! Minor tweaks will make you competitive."
              : advice.overall_score >= 0.6
              ? "Good foundation. Focus on the gaps below to improve your chances."
              : "Significant gaps detected. Consider the recommendations below to strengthen your profile."}
          </p>
        </div>

        {/* Sections */}
        {sections.map((section) => {
          if (section.type === "text" && section.content) {
            return (
              <motion.div
                key={section.title}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="bg-gradient-to-br from-violet-50 to-purple-50 rounded-2xl p-6 border border-violet-100"
              >
                <div className="flex items-center gap-2 mb-3">
                  {section.icon}
                  <h3 className="font-bold text-violet-900">{section.title}</h3>
                </div>
                <p className="text-sm text-violet-800 leading-relaxed bg-white/60 rounded-xl p-4">
                  {section.content}
                </p>
                <div className="mt-3">
                  <CopyButton text={section.content} />
                </div>
              </motion.div>
            );
          }

          if (!section.items || section.items.length === 0) return null;

          const colorMap: Record<string, string> = {
            emerald: "from-emerald-50 to-teal-50 border-emerald-100",
            sky: "from-sky-50 to-blue-50 border-sky-100",
            amber: "from-amber-50 to-orange-50 border-amber-100",
            purple: "from-purple-50 to-fuchsia-50 border-purple-100",
            rose: "from-rose-50 to-pink-50 border-rose-100",
            indigo: "from-indigo-50 to-blue-50 border-indigo-100",
          };

          return (
            <motion.div
              key={section.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className={`bg-gradient-to-br ${colorMap[section.color]} rounded-2xl p-6 border`}
            >
              <div className="flex items-center gap-2 mb-4">
                {section.icon}
                <h3 className="font-bold text-slate-900">{section.title}</h3>
                <span className="ml-auto text-xs font-medium text-slate-500 bg-white/80 px-2 py-1 rounded-lg">
                  {section.items.length}
                </span>
              </div>
              <ul className="space-y-3">
                {section.items.map((item, i) => (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-start gap-3 text-sm text-slate-700"
                  >
                    <ArrowUpRight className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
                    <span className="leading-relaxed">{item}</span>
                  </motion.li>
                ))}
              </ul>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-violet-600 hover:text-violet-800"
    >
      {copied ? (
        <>
          <CheckCircle2 className="w-3.5 h-3.5" />
          Copied!
        </>
      ) : (
        <>
          <Download className="w-3.5 h-3.5" />
          Copy to clipboard
        </>
      )}
    </button>
  );
}

function StatsOverview({ matches }: { matches: MatchedJob[] }) {
  const avgScore =
    matches.reduce((acc, m) => acc + m.similarity_score, 0) / matches.length;
  const remoteCount = matches.filter(
    (m) => m.job.work_type === "remote" || m.job.work_type === "hybrid"
  ).length;
  const easyApplyCount = matches.filter((m) => m.job.easy_apply).length;
  const salaryRanges = matches
    .map((m) => m.job.salary_range)
    .filter(Boolean) as string[];

  const chartData = matches.slice(0, 5).map((m, i) => ({
    name: m.job.company?.slice(0, 10) || `Job ${i + 1}`,
    score: Math.round(m.similarity_score * 100),
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Match Overview
          </h3>
          <BarChart3 className="w-5 h-5 text-slate-400" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <p className="text-3xl font-bold text-slate-900">
              {(avgScore * 100).toFixed(0)}%
            </p>
            <p className="text-xs text-slate-500 mt-1">Avg Score</p>
          </div>
          <div className="text-center">
            <p className="text-3xl font-bold text-emerald-600">{remoteCount}</p>
            <p className="text-xs text-slate-500 mt-1">Remote</p>
          </div>
          <div className="text-center">
            <p className="text-3xl font-bold text-sky-600">{easyApplyCount}</p>
            <p className="text-xs text-slate-500 mt-1">Easy Apply</p>
          </div>
        </div>
      </Card>

      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Top Matches
          </h3>
          <TrendingUp className="w-5 h-5 text-slate-400" />
        </div>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e293b",
                  border: "none",
                  borderRadius: "12px",
                  color: "#fff",
                  fontSize: "12px",
                }}
              />
              <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={i === 0 ? "#8b5cf6" : i === 1 ? "#06b6d4" : "#cbd5e1"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Skill Demand
          </h3>
          <Wrench className="w-5 h-5 text-slate-400" />
        </div>
        <div className="space-y-3">
          {Array.from(
            matches
              .flatMap((m) => m.job.skills)
              .reduce((acc, skill) => {
                acc.set(skill, (acc.get(skill) || 0) + 1);
                return acc;
              }, new Map<string, number>())
          )
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([skill, count]) => (
              <div key={skill} className="flex items-center gap-3">
                <span className="text-sm text-slate-700 w-24 truncate">{skill}</span>
                <div className="flex-1 bg-slate-100 rounded-full h-2">
                  <div
                    className="h-full bg-violet-500 rounded-full"
                    style={{ width: `${(count / matches.length) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-slate-500 w-8 text-right">{count}</span>
              </div>
            ))}
        </div>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Scraping UI & Streaming
// ═══════════════════════════════════════════════════════════════════════════════

function ScrapeSection({
  resume,
  onScrapeComplete,
}: {
  resume: ResumeProfile;
  onScrapeComplete: () => void;
}) {
  const [keywords, setKeywords] = useState(
    resume.target_roles?.[0] || resume.skills?.[0] || "Software Engineer"
  );
  const [location, setLocation] = useState("Remote");
  const [datePosted, setDatePosted] = useState("");
  const [jobType, setJobType] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("");
  const [workType, setWorkType] = useState("");
  const [easyApply, setEasyApply] = useState(false);
  const [sortBy, setSortBy] = useState("");
  const [isScraping, setIsScraping] = useState(false);
  const [events, setEvents] = useState<any[]>([]);

  const handleStartScrape = async () => {
    setIsScraping(true);
    setEvents([]);
    try {
      const payload: any = {
        keywords,
        location: location || undefined,
        max_pages: 1,
        date_posted: datePosted || undefined,
        job_type: jobType || undefined,
        experience_level: experienceLevel || undefined,
        work_type: workType || undefined,
        easy_apply: easyApply,
        sort_by: sortBy || undefined,
      };

      const res = await fetch("http://localhost:8000/api/v1/scrape/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              setEvents((prev) => [...prev, data]);
              if (data.step === "done") {
                setTimeout(() => {
                  setIsScraping(false);
                  onScrapeComplete();
                }, 2000);
              }
            } catch (e) {
              console.error("Parse error", e);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setIsScraping(false);
    }
  };

  return (
    <Card className="p-6 mb-8 mt-4 mx-auto max-w-7xl border-violet-200 bg-violet-50/30">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 bg-violet-100 rounded-xl flex items-center justify-center">
          <Globe className="w-5 h-5 text-violet-600" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-900">Scrape New Jobs</h3>
          <p className="text-sm text-slate-500">Based on your resume, we recommend this role.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="lg:col-span-2">
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Keywords (Role)</label>
          <input
            type="text"
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-400"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
          />
        </div>
        <div className="lg:col-span-2">
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Location</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-400"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          >
            <option value="">Anywhere</option>
            <option value="Remote">Remote</option>
            <option value="San Francisco, CA">San Francisco, CA</option>
            <option value="New York, NY">New York, NY</option>
            <option value="London, UK">London, UK</option>
            <option value="India">India</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Date Posted</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400"
            value={datePosted}
            onChange={(e) => setDatePosted(e.target.value)}
          >
            <option value="">Any Time</option>
            <option value="past_hour">Past Hour</option>
            <option value="past_24_hours">Past 24 Hours</option>
            <option value="past_week">Past Week</option>
            <option value="past_month">Past Month</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Experience Level</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400"
            value={experienceLevel}
            onChange={(e) => setExperienceLevel(e.target.value)}
          >
            <option value="">Any Level</option>
            <option value="internship">Internship</option>
            <option value="entry">Entry Level</option>
            <option value="associate">Associate</option>
            <option value="mid_senior">Mid-Senior Level</option>
            <option value="director">Director</option>
            <option value="executive">Executive</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Job Type</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400"
            value={jobType}
            onChange={(e) => setJobType(e.target.value)}
          >
            <option value="">Any Type</option>
            <option value="full_time">Full-time</option>
            <option value="part_time">Part-time</option>
            <option value="contract">Contract</option>
            <option value="temporary">Temporary</option>
            <option value="volunteer">Volunteer</option>
            <option value="internship">Internship</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Work Type</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400"
            value={workType}
            onChange={(e) => setWorkType(e.target.value)}
          >
            <option value="">Any Work Type</option>
            <option value="remote">Remote</option>
            <option value="on_site">On-site</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </div>
        
        <div className="flex items-center gap-2 mt-4">
          <input
            type="checkbox"
            id="easyApply"
            checked={easyApply}
            onChange={(e) => setEasyApply(e.target.checked)}
            className="w-4 h-4 rounded text-violet-600 focus:ring-violet-500"
          />
          <label htmlFor="easyApply" className="text-sm font-medium text-slate-700">
            Easy Apply Only
          </label>
        </div>
        
        <div className="mt-2 lg:mt-0">
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Sort By</label>
          <select
            className="w-full px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm outline-none focus:border-violet-400"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="">None (Default)</option>
            <option value="relevance">Relevance</option>
            <option value="date">Date</option>
          </select>
        </div>
      </div>

      {!isScraping && (
        <Button onClick={handleStartScrape} className="w-full bg-violet-600 hover:bg-violet-700">
          Start Live Scraping
        </Button>
      )}

      {isScraping && (
        <div className="bg-slate-900 rounded-xl p-4 mt-4 h-64 overflow-y-auto font-mono text-xs text-emerald-400">
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Connecting to MCP and Scraping...</span>
          </div>
          {events.map((ev, i) => (
            <div key={i} className="mb-1 flex gap-2">
              <span className="text-slate-500">[{ev.step}]</span>
              <span className="text-slate-300">{ev.message}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main App
// ═══════════════════════════════════════════════════════════════════════════════


export default function JobMatcherApp() {
  const [resume, setResume] = useState<ResumeProfile | null>(null);
  const [matches, setMatches] = useState<MatchedJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeAdvice, setActiveAdvice] = useState<ResumeAdvice | null>(null);
  const [advisingJobId, setAdvisingJobId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"matches" | "analytics">("matches");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    setUploadedFile(file);

    try {
      const formData = new FormData();
      formData.append("resume", file);
      formData.append("top_k", "10");

      const res = await fetch("/api/match", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok || !data.success) {
        throw new Error(data.error || "Failed to match resume");
      }

      setResume(data.resume);
      setMatches(data.matches);
    } catch (err) {
      console.error("Upload error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to process resume"
      );
      setUploadedFile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleGetAdvice = useCallback(
    async (jobId: string) => {
      if (!uploadedFile) {
        setError("Please upload your resume first");
        return;
      }

      setAdvisingJobId(jobId);
      setError(null);

      try {
        const formData = new FormData();
        formData.append("resume", uploadedFile);
        formData.append("job_id", jobId);

        const res = await fetch("/api/advise", {
          method: "POST",
          body: formData,
        });

        const data = await res.json();

        if (!res.ok || !data.success) {
          throw new Error(data.error || "Failed to get advice");
        }

        setActiveAdvice(data.advice);
      } catch (err) {
        console.error("Advice error:", err);
        setError(
          err instanceof Error ? err.message : "Failed to get advice"
        );
      } finally {
        setAdvisingJobId(null);
      }
    },
    [uploadedFile]
  );

  const handleReset = useCallback(() => {
    setResume(null);
    setMatches([]);
    setActiveAdvice(null);
    setUploadedFile(null);
    setError(null);
    setActiveTab("matches");
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <Header />

      <main className="pb-20">
        {/* Error Banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4"
            >
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-rose-500 shrink-0" />
                <p className="text-sm text-rose-700 flex-1">{error}</p>
                <button
                  onClick={() => setError(null)}
                  className="p-1 hover:bg-rose-100 rounded-lg transition-colors"
                >
                  <X className="w-4 h-4 text-rose-500" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <ResumeUploadSection onUpload={handleUpload} resume={resume} onReset={handleReset} />

        {resume && !loading && (
          <div className="px-4 sm:px-6 lg:px-8">
            <ScrapeSection 
              resume={resume} 
              onScrapeComplete={() => {
                // We could automatically re-run matching here by re-uploading the file,
                // but for now we just show it's done. 
                if (uploadedFile) handleUpload(uploadedFile);
              }} 
            />
          </div>
        )}

        {loading && (
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
              className="w-12 h-12 border-4 border-violet-200 border-t-violet-600 rounded-full mx-auto mb-4"
            />
            <p className="text-slate-600 font-medium">Analyzing your resume and finding matches...</p>
          </div>
        )}

        {resume && matches.length > 0 && !loading && (
          <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            {/* Tabs */}
            <div className="flex items-center gap-1 mb-6 bg-white p-1 rounded-xl border border-slate-200/60 w-fit">
              <button
                onClick={() => setActiveTab("matches")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === "matches"
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className="flex items-center gap-2">
                  <Briefcase className="w-4 h-4" />
                  Job Matches ({matches.length})
                </span>
              </button>
              <button
                onClick={() => setActiveTab("analytics")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === "analytics"
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" />
                  Analytics
                </span>
              </button>
            </div>

            {activeTab === "analytics" && <StatsOverview matches={matches} />}

            {activeTab === "matches" && (
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                {/* Job List */}
                <div className="xl:col-span-2 space-y-4">
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-lg font-bold text-slate-900">
                      Top Matches
                    </h2>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" icon={<Filter className="w-4 h-4" />}>
                        Filter
                      </Button>
                      <Button variant="ghost" size="sm" icon={<Search className="w-4 h-4" />}>
                        Search
                      </Button>
                    </div>
                  </div>
                  {matches.map((match, i) => (
                    <JobCard
                      key={match.job.job_id}
                      match={match}
                      index={i}
                      onGetAdvice={handleGetAdvice}
                      isAdvising={advisingJobId === match.job.job_id}
                    />
                  ))}
                </div>

                {/* Sidebar */}
                <div className="space-y-6">
                  <Card className="p-6">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
                      <Target className="w-4 h-4 text-violet-600" />
                      Match Breakdown
                    </h3>
                    <MatchScoreCard score={matches[0]?.similarity_score || 0} />
                  </Card>

                  <Card className="p-6">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
                      <GraduationCap className="w-4 h-4 text-sky-600" />
                      Recommended Skills
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {Array.from(
                        new Set(matches.flatMap((m) => m.job.skills))
                      )
                        .filter(
                          (skill) => !resume.skills.includes(skill)
                        )
                        .slice(0, 12)
                        .map((skill) => (
                          <Badge key={skill} variant="warning">
                            {skill}
                          </Badge>
                        ))}
                    </div>
                  </Card>

                  <Card className="p-6">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-emerald-600" />
                      Quick Actions
                    </h3>
                    <div className="space-y-2">
                      <Button variant="secondary" className="w-full justify-start" icon={<Download className="w-4 h-4" />}>
                        Export Match Report
                      </Button>
                      <Button variant="secondary" className="w-full justify-start" icon={<RefreshCw className="w-4 h-4" />}>
                        Refresh Job Feed
                      </Button>
                      <Button variant="secondary" className="w-full justify-start" icon={<Sparkles className="w-4 h-4" />}>
                        Generate Cover Letters
                      </Button>
                    </div>
                  </Card>
                </div>
              </div>
            )}
          </section>
        )}
      </main>

      {/* Advice Panel Overlay */}
      <AnimatePresence>
        {activeAdvice && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40"
              onClick={() => setActiveAdvice(null)}
            />
            <AdvicePanel
              advice={activeAdvice}
              onClose={() => setActiveAdvice(null)}
            />
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

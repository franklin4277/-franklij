"use client";

import { useEffect, useRef, useState } from "react";
import { api, Datasource, QueryResp, SessionInfo } from "../../lib/api";

// ---------- 消息模型 ----------
type Role = "user" | "assistant" | "system";
interface Msg {
  id: string;
  role: Role;
  text?: string;
  query?: QueryResp;
  loading?: boolean;
  error?: string;
}

// ---------- 主页面 ----------
export default function ChatPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [datasets, setDatasets] = useState<Datasource[]>([]);
  const [dsId, setDsId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [initErr, setInitErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 初始化：拉数据源 + 创建会话
  useEffect(() => {
    (async () => {
      try {
        const [ds, sess] = await Promise.all([
          api.listDatasets(),
          api.createSession(),
        ]);
        setDatasets(ds);
        setSession(sess);
      } catch (e: unknown) {
        setInitErr(`初始化失败: ${e instanceof Error ? e.message : String(e)}`);
      }
    })();
  }, []);

  // 自动滚动
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!session || !input.trim() || busy) return;
    const q = input.trim();
    const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", text: q };
    const aiMsg: Msg = { id: `a-${Date.now()}`, role: "assistant", loading: true };
    setMessages((m) => [...m, userMsg, aiMsg]);
    setInput("");
    setBusy(true);
    try {
      const resp = await api.query(session.id, {
        question: q,
        datasource_id: dsId ?? undefined,
        lang: "zh-CN",
      });
      setMessages((m) => m.map((x) => (x.id === aiMsg.id ? { ...x, query: resp, loading: false } : x)));
    } catch (e: unknown) {
      setMessages((m) =>
        m.map((x) => (x.id === aiMsg.id ? { ...x, loading: false, error: e instanceof Error ? e.message : String(e) } : x))
      );
    } finally {
      setBusy(false);
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="border-b bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">问数 Agent</h1>
            <p className="text-xs text-slate-500">基于 SQLBot · 自然语言查询</p>
          </div>
          <div className="flex items-center gap-3">
            <DatasetSelector datasets={datasets} value={dsId} onChange={setDsId} disabled={busy} />
            <button
              onClick={async () => {
                if (!confirm("销毁当前会话？历史将清空。")) return;
                if (session) await api.destroySession(session.id);
                const s = await api.createSession();
                setSession(s);
                setMessages([]);
              }}
              className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              disabled={busy || !session}
            >
              新会话
            </button>
          </div>
        </div>
        {session && (
          <div className="mt-1 text-[11px] text-slate-400">
            会话 {session.id} · 创建于 {new Date(session.created_at).toLocaleString()}
          </div>
        )}
      </header>

      {initErr && (
        <div className="bg-amber-50 px-6 py-2 text-sm text-amber-800">{initErr}</div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="mx-auto max-w-2xl text-center text-slate-500 mt-12">
            <p className="text-base">开始问数吧。</p>
            <p className="mt-2 text-xs">
              例如：上海虹桥各品牌销售额、上月客流对比、订单 TOP5 商品...
            </p>
          </div>
        )}
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((m) => (
            <MessageBubble key={m.id} msg={m} />
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="border-t bg-white px-6 py-3">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            rows={2}
            placeholder={busy ? "等待 SQLBot 回答中..." : "输入你的问题，Enter 发送，Shift+Enter 换行"}
            className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            disabled={busy || !session}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim() || !session}
            className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:bg-slate-300"
          >
            {busy ? "发送中..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- 数据源选择 ----------
function DatasetSelector({
  datasets,
  value,
  onChange,
  disabled,
}: {
  datasets: Datasource[];
  value: number | null;
  onChange: (v: number | null) => void;
  disabled?: boolean;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      disabled={disabled || datasets.length === 0}
      className="rounded border border-slate-200 px-2 py-1.5 text-xs text-slate-700 focus:border-brand-500 focus:outline-none"
    >
      <option value="">自动选择</option>
      {datasets.map((d) => (
        <option key={d.id} value={d.id}>
          {d.name} ({d.type_name ?? d.type})
        </option>
      ))}
    </select>
  );
}

// ---------- 消息气泡 ----------
function MessageBubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-brand-600 px-4 py-2 text-sm text-white">
          {msg.text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-2xl bg-white px-4 py-3 shadow-sm border border-slate-100">
        {msg.loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand-500" />
            正在生成回答…
          </div>
        )}
        {msg.error && <div className="text-sm text-red-600">{msg.error}</div>}
        {msg.query && <QueryResult q={msg.query} />}
      </div>
    </div>
  );
}

// ---------- 查询结果渲染 ----------
function QueryResult({ q }: { q: QueryResp }) {
  if (!q.success) {
    return (
      <div className="text-sm">
        <div className="font-medium text-red-600">未能生成查询</div>
        {q.message && <div className="mt-1 text-slate-600">{q.message}</div>}
      </div>
    );
  }
  return (
    <div className="space-y-3 text-sm">
      {q.title && <div className="font-medium text-slate-900">{q.title}</div>}

      {/* 数据表格 */}
      {q.data.fields.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {q.data.fields.map((f) => (
                  <th key={f} className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-left font-medium text-slate-700">
                    {f}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0">
                  {q.data.fields.map((f) => (
                    <td key={f} className="px-3 py-2 text-slate-700">
                      {formatCell(row[f])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-1 text-[11px] text-slate-400">共 {q.data.row_count} 行</div>
        </div>
      )}

      {/* 图表 */}
      {q.chart_image_url && (
        <div className="rounded border border-slate-100 bg-slate-50 p-2">
          <img src={q.chart_image_url} alt={q.chart?.title ?? "chart"} className="max-w-full" />
        </div>
      )}
      {q.chart && !q.chart_image_url && (
        <div className="text-xs text-slate-500">
          {q.chart.type} · {q.chart.axis_x ?? ""} → {q.chart.axis_y?.join("/") ?? ""}
        </div>
      )}

      {/* SQL 折叠 */}
      {q.sql && (
        <details className="text-xs">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-700">查看 SQL</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-slate-900 px-3 py-2 text-[11px] text-slate-100">
            {q.sql}
          </pre>
        </details>
      )}

      {q.message && <div className="text-xs text-slate-500">{q.message}</div>}
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}
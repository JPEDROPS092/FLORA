"""LLM operator loop: the model picks tools, FLORA runs them, the researcher approves anything that changes data.

Stateless: the browser keeps the OpenAI-style history and sends it back with each turn. A tool that needs approval is
not run; the turn returns ``pending`` and the next request carries ``approved`` / ``rejected`` call ids.
"""

from __future__ import annotations

import json
from typing import Any

from flora.llm import LlmError
from flora.ui import agent_tools as at
from flora.ui.http import UiHttpError

MAX_STEPS = 10
MAX_HISTORY = 60
MAX_CHARS = 80_000
MAX_TOOL_CALLS = 6
_SUMMARY_CHARS = 3500

SYSTEM = """Você é o operador do FLORA, um app de análise de microbioma 16S. Você opera o app chamando ferramentas.

Regras:
1. NUNCA invente números, códigos de estudos ou nomes de colunas. Use as ferramentas e cite os valores que elas devolvem.
2. Se não souber o estado, chame get_workspace primeiro. Use só colunas de agrupamento que existem (group_columns) e só códigos de estudo que vierem das ferramentas (source_studies, search_catalog); nunca invente um código.
3. Sem dados carregados: sugira o caminho search_catalog -> download_study -> ingest_dataset (list_datasets mostra o que já está no disco). Estudos só com metadados (sem tabela de abundância) não podem ser analisados.
4. Ferramentas que alteram dados exigem aprovação do usuário: chame-as normalmente; o app pede a aprovação. Se o usuário recusar, não insista.
5. Para uma pergunta de pesquisa, combine ferramentas: gráfico + teste estatístico, e interprete com ressalvas (n pequeno, p sem correção, dados sintéticos).
6. Responda em português, direto e curto. Descreva gráficos pelos números devolvidos; os gráficos e tabelas aparecem para o usuário automaticamente.
7. Não há outras capacidades: não execute código, não leia arquivos fora das ferramentas, não acesse a internet.
"""


def _context(state) -> str:
    try:
        out = at.TOOLS["get_workspace"].run(state, {}).summary
        project = (out.get("project") or {}).get("name") or "nenhum"
        groups = ", ".join(f"{c['name']} ({len(c['values'])} grupos)" for c in out["group_columns"]) or "nenhuma"
        c = out["counts"]
        return f"Estado agora: projeto ativo = {project}; {c['samples']} amostras, {c['asvs']} ASVs, {c['taxa']} táxons; colunas de agrupamento: {groups}."
    except Exception:  # noqa: BLE001 - the context line is a convenience, never a failure
        return "Estado agora: desconhecido (chame get_workspace)."


def _clean_history(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_HISTORY:
        raise UiHttpError("`messages` deve ser uma lista não vazia (até 60 mensagens).", code="invalid_messages")
    out: list[dict[str, Any]] = []
    total = 0
    for item in raw:
        role = (item or {}).get("role")
        content = (item or {}).get("content")
        if role == "user" and isinstance(content, str):
            msg: dict[str, Any] = {"role": "user", "content": content}
        elif role == "assistant":
            msg = {"role": "assistant", "content": content if isinstance(content, str) else ""}
            calls = item.get("tool_calls")
            if calls:
                if not isinstance(calls, list) or len(calls) > MAX_TOOL_CALLS:
                    raise UiHttpError("tool_calls inválido.", code="invalid_messages")
                msg["tool_calls"] = [{"id": str(c["id"]), "type": "function", "function": {"name": str(c["function"]["name"]), "arguments": str(c["function"].get("arguments") or "{}")}} for c in calls]
        elif role == "tool" and isinstance(content, str) and item.get("tool_call_id"):
            msg = {"role": "tool", "tool_call_id": str(item["tool_call_id"]), "content": content}
        else:
            raise UiHttpError("Mensagem inválida no histórico.", code="invalid_messages")
        total += len(msg.get("content") or "")
        out.append(msg)
    if total > MAX_CHARS:
        raise UiHttpError("Conversa longa demais; limpe e recomece.", status=413, code="payload_too_large")
    return out


def _unresolved(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool calls of the last assistant message that have no tool answer yet."""
    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        if msg["role"] == "assistant":
            done = {m["tool_call_id"] for m in history[i + 1:] if m["role"] == "tool"}
            return [c for c in msg.get("tool_calls", []) if c["id"] not in done]
        if msg["role"] == "user":
            return []
    return []


def _process(state, calls: list[dict[str, Any]], approved: set[str], rejected: set[str], out: dict[str, Any]) -> list[dict[str, Any]]:
    """Run or answer each call. Returns the calls that still need approval (processing stops at the first)."""
    for index, call in enumerate(calls):
        name = call["function"]["name"]
        tool = at.TOOLS.get(name)
        if tool is not None and tool.confirm and call["id"] not in approved and call["id"] not in rejected:
            return [c for c in calls[index:] if (at.TOOLS.get(c["function"]["name"]) and at.TOOLS[c["function"]["name"]].confirm)]
        if call["id"] in rejected:
            out["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"error": "O usuário recusou esta ação."}, ensure_ascii=False)})
            out["steps"].append({"tool": name, "ok": False, "ms": 0, "detail": "recusado pelo usuário", "call_id": call["id"]})
            continue
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except ValueError:
            args = None
        result, trace = at.execute(state, name, args)
        text = json.dumps(result.summary, ensure_ascii=False, default=str)
        if len(text) > _SUMMARY_CHARS:
            text = text[:_SUMMARY_CHARS] + '…"(resumo truncado)"'
        out["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": text})
        out["steps"].append({**trace, "call_id": call["id"]})
        out["artifacts"].extend({**a, "tool": name, "call_id": call["id"]} for a in result.artifacts)
    return []


def run_turn(state, settings, client, body: dict[str, Any]) -> dict[str, Any]:
    history = _clean_history(body.get("messages"))
    approved = {str(x) for x in body.get("approved") or []}
    rejected = {str(x) for x in body.get("rejected") or []}
    out: dict[str, Any] = {"messages": [], "artifacts": [], "steps": [], "pending": [], "text": "", "usage": {}, "model": settings.model}
    specs = [t.spec() for t in at.TOOLS.values()]
    system = {"role": "system", "content": SYSTEM + "\n" + _context(state)}

    # 1) finish tool calls left over from the previous turn (approved, rejected or not needing approval)
    pending = _process(state, _unresolved(history), approved, rejected, out)
    for _ in range(MAX_STEPS):
        if pending:
            break
        try:
            reply = client.chat_with_tools([system, *history, *out["messages"]], specs, model=settings.model,
                                           max_tokens=max(settings.max_tokens, 1500))
        except LlmError as exc:
            raise UiHttpError(str(exc), status=502, code="llm_error") from exc
        message = reply["message"]
        usage = reply.get("usage") or {}
        out["usage"] = {k: out["usage"].get(k, 0) + (usage.get(k) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        calls = [{"id": str(c["id"]), "type": "function", "function": {"name": str(c["function"]["name"]), "arguments": str(c["function"].get("arguments") or "{}")}}
                 for c in (message.get("tool_calls") or [])[:MAX_TOOL_CALLS]]
        assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
        if calls:
            assistant["tool_calls"] = calls
        out["messages"].append(assistant)
        if not calls:
            out["text"] = assistant["content"]
            break
        pending = _process(state, calls, approved, rejected, out)
    else:
        out["text"] = "Parei depois de várias etapas seguidas. Diga como quer continuar."
        out["messages"].append({"role": "assistant", "content": out["text"]})

    out["pending"] = [{"id": c["id"], "tool": c["function"]["name"], "description": at.TOOLS[c["function"]["name"]].description,
                       "arguments": _safe_args(c["function"].get("arguments"))} for c in pending]
    return out


def _safe_args(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}

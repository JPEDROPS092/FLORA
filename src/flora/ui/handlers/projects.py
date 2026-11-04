"""Projects, data-source sync and example handlers."""

from __future__ import annotations

from typing import Any

from flora.projects import EXAMPLES, ProjectError
from flora.projects.examples import get_example
from flora.ui.http import UiHttpError, json_success


def _wrap(fn):
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProjectError as exc:
            raise UiHttpError(str(exc), status=exc.status, code=exc.code) from exc

    inner.__name__ = fn.__name__
    return inner


def _q(params: dict | None, key: str) -> str:
    return ((params or {}).get(key) or [""])[0]


def _public(project) -> dict[str, Any]:
    return project.model_dump()


@_wrap
def list_projects(state, params=None):
    return json_success(data={"projects": [_public(p) for p in state.projects.list()], "active": state.projects.active_id()})


@_wrap
def get_project(state, params=None):
    pid = _q(params, "id")
    return json_success(data={"project": _public(state.projects.get(pid)), "jobs": state.sync.list(pid)})


@_wrap
def create_project(state, body):
    body = dict(body or {})
    project = state.projects.create(body.pop("name", ""), body.pop("question", ""), **{k: v for k, v in body.items() if k in {"description", "organism", "biome", "marker"}})
    return json_success(data={"project": _public(project)})


@_wrap
def update_project(state, body):
    body = dict(body or {})
    project = state.projects.update(body.pop("id", ""), {k: v for k, v in body.items() if k in {"name", "question", "description", "organism", "biome", "marker"}})
    return json_success(data={"project": _public(project)})


@_wrap
def delete_project(state, body):
    """Delete a project and its DuckDB. Requires ``confirm: true``."""
    body = body or {}
    if body.get("confirm") is not True:
        return json_success(data={
            "applied": False,
            "message": "Nada foi apagado. Envie confirm=true para excluir o projeto e o banco dele.",
        })
    pid = str(body.get("id") or "")
    state.release(pid)
    state.projects.delete(pid)
    return json_success(data={"applied": True, "id": pid})


@_wrap
def activate_project(state, body):
    pid = (body or {}).get("id", "")
    state.projects.set_active(pid)
    return json_success(data={"project": _public(state.projects.get(pid))})


@_wrap
def start_sync(state, body):
    body = body or {}
    job = state.sync.start(body.get("id", ""), body.get("source") or {})
    return json_success(data={"job": job})


@_wrap
def get_job(state, params=None):
    return json_success(data={"job": state.sync.get(_q(params, "id"), _q(params, "project") or None)})


@_wrap
def cancel_job(state, body):
    return json_success(data={"job": state.sync.cancel((body or {}).get("id", ""))})


def list_examples(state, params=None):
    return json_success(data={"examples": EXAMPLES})


@_wrap
def install_example(state, body):
    example = get_example((body or {}).get("id", ""))
    if example is None:
        raise UiHttpError("Unknown example.", status=404, code="not_found")
    if not example["installable"]:
        raise UiHttpError("This template has an unverified accession and cannot be imported yet.", status=409, code="template_unverified")
    project = state.projects.create(
        example["name"], example["question"], description=example["description"], biome=example["biome"], marker=example["marker"],
        kind="example" if example["synthetic"] else "public", synthetic=example["synthetic"], example_id=example["id"])
    job = state.sync.start(project.id, example["source"])
    state.projects.set_active(project.id)
    return json_success(data={"project": _public(project), "job": job})

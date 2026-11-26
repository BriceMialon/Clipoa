#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur MCP ClipRoll (stdio JSON-RPC 2.0, zéro dépendance externe).
Permet à Claude Desktop / Claude Code de piloter ClipRoll directement :
  - cliproll_status : état du serveur et compte actif
  - cliproll_list_videos : liste les vidéos générées / à valider
  - cliproll_make_video : lance la fabrication d'une vidéo 9:16
  - cliproll_generate_week : planifie et met en file 5 vidéos pour la semaine
  - cliproll_channel_audit : audit de rétention sur les 12 derniers Shorts
  - cliproll_optimize_script : optimise un script (hook 1.5s, élagage, boucle >100%)
  - cliproll_sync_stats : lance la mise à jour des statistiques du compte actif

Règle de sécurité : aucun outil MCP ne publie ni ne supprime de vidéo sans accord humain dans l'interface ClipRoll.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict

CLIPROLL_URL = os.environ.get("CLIPROLL_URL", "http://127.0.0.1:8080").rstrip("/")
CLIPROLL_TOKEN = os.environ.get("CLIPROLL_TOKEN", "")


def _http(method: str, path: str, body: Dict[str, Any] = None) -> Any:
    url = f"{CLIPROLL_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if CLIPROLL_TOKEN:
        headers["X-Clipoa-Token"] = CLIPROLL_TOKEN
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return {"error": json.loads(raw).get("error", raw), "status": e.code}
        except Exception:
            return {"error": raw or str(e), "status": e.code}
    except Exception as e:
        return {"error": f"ClipRoll inaccessible sur {CLIPROLL_URL} : {e}"}


TOOLS = [
    {
        "name": "cliproll_status",
        "description": "Vérifie la santé de ClipRoll et les statistiques du compte actif (YouTube ou TikTok).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cliproll_make_video",
        "description": "Lance la fabrication d'une vidéo 9:16 dans ClipRoll (arrive dans Mes vidéos → À valider).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Idée ou script de la vidéo"},
                "duration_sec": {"type": "integer", "description": "Durée cible en secondes (30 à 120)", "default": 60},
                "plugin_id": {"type": "string", "description": "ID optionnel du style DA"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "cliproll_generate_week",
        "description": "Demande à l'équipe d'agents ClipRoll de planifier et lancer 5 vidéos pour la semaine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "niche": {"type": "string", "description": "Niche ou thème des 5 vidéos (optionnel, déduit de la chaîne sinon)"},
                "duration_sec": {"type": "integer", "default": 60},
            },
        },
    },
    {
        "name": "cliproll_channel_audit",
        "description": "Lance l'audit complet de rétention sur les 12 derniers Shorts du compte actif (scorecard, 3 fuites, formule hook 1.5s, plan 7 jours).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cliproll_optimize_script",
        "description": "Optimise un script 9:16 (5 hooks 1.5s Evidence+Betrayal, élagage, rythme voix, boucle >100 % et pattern interrupts 6s).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Texte du script à optimiser"},
                "topic": {"type": "string", "description": "Sujet de la vidéo"},
                "duration_sec": {"type": "integer", "default": 30},
            },
            "required": ["script"],
        },
    },
    {
        "name": "cliproll_sync_stats",
        "description": "Déclenche la mise à jour des statistiques du compte actif (YouTube ou TikTok).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cliproll_agent_mission",
        "description": "Envoie une mission libre à l'équipe d'agents IA ClipRoll (Orchestrateur, Stratège Rétention, Scénariste, Producteur, Vérificateur).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Mission en langage naturel"},
            },
            "required": ["message"],
        },
    },
]


def _call_tool(name: str, args: Dict[str, Any]) -> Any:
    if name == "cliproll_status":
        return {"health": _http("GET", "/api/system/health"), "stats": _http("GET", "/api/channel-stats")}
    if name == "cliproll_make_video":
        return _http("POST", "/api/make", {
            "topic": args.get("topic", ""),
            "target_duration_sec": int(args.get("duration_sec", 60)),
            "plugin_id": args.get("plugin_id") or None,
            "engine": "claude",
            "enable_music": True,
            "enable_sfx": True,
        })
    if name == "cliproll_generate_week":
        niche = (args.get("niche") or "").strip()
        msg = f"Génère mes 5 vidéos pour la semaine sur {niche}" if niche else "Génère mes 5 vidéos pour la semaine"
        return _http("POST", "/api/agent-team/run", {"message": msg, "duration_sec": int(args.get("duration_sec", 60))})
    if name == "cliproll_channel_audit":
        return _http("POST", "/api/channel-stats/audit", {})
    if name == "cliproll_optimize_script":
        return _http("POST", "/api/script/optimize-retention", {
            "script": args.get("script", ""),
            "topic": args.get("topic", ""),
            "duration_sec": int(args.get("duration_sec", 30)),
        })
    if name == "cliproll_sync_stats":
        return _http("POST", "/api/channel-stats/sync", {})
    if name == "cliproll_agent_mission":
        return _http("POST", "/api/agent-team/run", {"message": args.get("message", "")})
    return {"error": f"Outil inconnu : {name}"}


def _send(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "cliproll-mcp", "version": "1.0.0"},
                },
            })
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            tname = params.get("name", "")
            targs = params.get("arguments") or {}
            res = _call_tool(tname, targs)
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]},
            })
        elif req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()

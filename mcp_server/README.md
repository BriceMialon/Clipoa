# Serveur MCP ClipRoll pour Claude (Claude Desktop & Claude Code)

Ce serveur MCP expose ClipRoll (`http://127.0.0.1:8080`) directement comme outils natifs dans Claude, sans dépendance externe (Python standard uniquement).

## Configuration Claude Desktop / Claude Code

Ajoute ce bloc dans `~/.claude.json` ou `~/Library/Application Support/Claude/claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "cliproll": {
      "command": "python3",
      "args": ["/chemin/vers/cliproll/mcp_server/cliproll_mcp.py"],
      "env": {
        "CLIPROLL_URL": "http://127.0.0.1:8080"
      }
    }
  }
}
```

Remplace `/chemin/vers/cliproll` par le dossier où ClipRoll est installé. `CLIPROLL_URL` n'accepte qu'une adresse locale (127.0.0.1, localhost) : toute autre valeur est ignorée.

## Outils disponibles
- `cliproll_status` : état du serveur et stats du compte actif
- `cliproll_make_video` : lance la fabrication d'une vidéo 9:16
- `cliproll_generate_week` : propose 5 sujets ; ne lance les fabrications qu'au second appel avec `confirmed: true`
- `cliproll_channel_audit` : audit rétention sur les 12 derniers Shorts
- `cliproll_optimize_script` : optimise un script (5 hooks 1.5s, élagage, boucle >100 %, pattern interrupts 6s)
- `cliproll_sync_stats` : actualise les stats du compte actif
- `cliproll_agent_mission` : envoie n'importe quelle mission à l'Équipe d'agents IA ClipRoll

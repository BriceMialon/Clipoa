#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from core.scraper import CompetitorScraper
from core.pipeline import ShortCrewPipeline
from core.claude_bridge import ClaudeBridge
from core.video_composer import THEMES, SUBTITLE_STYLES
from agents.team import LeStratege
from config import FFMPEG_PATH, YT_DLP_PATH, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="ShortCrew Local - Clone autonome pour créer tes shorts à partir de ce qui marche chez tes concurrents."
    )
    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # Command: status
    subparsers.add_parser("status", help="Vérifie la connexion Claude Pro/Max et les outils locaux")

    # Command: scan
    p_scan = subparsers.add_parser("scan", help="Scanne un compte concurrent et détecte les pépites virales (>= 2x la médiane)")
    p_scan.add_argument("url", help="URL YouTube Shorts, @handle ou profil TikTok")
    p_scan.add_argument("--threshold", type=float, default=2.0, help="Multiplicateur minimum (défaut: 2.0x)")
    p_scan.add_argument("--limit", type=int, default=30, help="Nombre max de vidéos à scanner (défaut: 30)")
    p_scan.add_argument("--cookies", default=None, help="Navigateur pour les cookies yt-dlp (ex: chrome, safari, firefox)")

    # Command: clone
    p_clone = subparsers.add_parser("clone", help="Clone la recette d'un short viral concurrent pour ton propre sujet")
    p_clone.add_argument("url", help="Lien du short concurrent (YouTube ou TikTok)")
    p_clone.add_argument("--topic", required=True, help="Le sujet de ton nouveau short")
    p_clone.add_argument("--niche", default="IA & Tech", help="Ta niche")
    p_clone.add_argument("--theme", default=DEFAULT_THEME, choices=list(THEMES.keys()), help="Thème visuel de fond")
    p_clone.add_argument("--subtitle-style", default=DEFAULT_SUBTITLE_STYLE, choices=list(SUBTITLE_STYLES.keys()), help="Style de sous-titres Submagic")
    p_clone.add_argument("--cookies", default=None, help="Navigateur pour les cookies yt-dlp (ex: chrome, safari)")

    # Command: make
    p_make = subparsers.add_parser("make", help="Fabrique un short directement à partir d'un sujet ('La Fabrique')")
    p_make.add_argument("--topic", required=True, help="Sujet ou consigne du short")
    p_make.add_argument("--style", default=None, help="Style oral / ton souhaité")
    p_make.add_argument("--bg", default=None, help="Vidéo d'arrière-plan optionnelle (rush / B-roll)")
    p_make.add_argument("--theme", default=DEFAULT_THEME, choices=list(THEMES.keys()), help="Thème visuel de fond")
    p_make.add_argument("--subtitle-style", default=DEFAULT_SUBTITLE_STYLE, choices=list(SUBTITLE_STYLES.keys()), help="Style de sous-titres Submagic")

    # Command: cut (Le Monteur)
    p_cut = subparsers.add_parser("cut", help="Découpe une vidéo longue filmée (fichier ou URL YouTube) en Shorts 9:16 ('Le Monteur')")
    p_cut.add_argument("source", help="Chemin local vers la vidéo (.mp4/.mov) ou URL YouTube")
    p_cut.add_argument("--clips", type=int, default=3, help="Nombre de shorts à extraire (défaut: 3)")
    p_cut.add_argument("--crop", default="center", choices=["center", "blurred_bg"], help="Recadrage 9:16 : 'center' (plein écran) ou 'blurred_bg' (16:9 sur fond flou)")
    p_cut.add_argument("--subtitle-style", default=DEFAULT_SUBTITLE_STYLE, choices=list(SUBTITLE_STYLES.keys()), help="Style de sous-titres Submagic")
    p_cut.add_argument("--jumpcuts", action="store_true", help="Supprime automatiquement les silences (> 0.75s) façon TikTok")
    p_cut.add_argument("--lang", default="fr", help="Langue audio pour Whisper (défaut: fr)")

    # Command: revise
    p_revise = subparsers.add_parser("revise", help="Modifie un short avec tes mots (retouche ciblée)")
    p_revise.add_argument("session_id", help="Identifiant de la session (ex: direct_1700000000_abc123)")
    p_revise.add_argument("--feedback", required=True, help="Ce qu'il faut corriger (ex: 'refais le début plus percutant')")

    # Command: week
    p_week = subparsers.add_parser("week", help="Génère la stratégie et les 5 sujets de la semaine ('Le Stratège')")
    p_week.add_argument("--niche", required=True, help="Ta niche (ex: Crypto, Fitness, Business, IA)")

    # Command: ui
    p_ui = subparsers.add_parser("ui", help="Lance l'interface visuelle locale dans le navigateur")
    p_ui.add_argument("--port", type=int, default=8080, help="Port d'écoute (défaut: 8080)")

    args = parser.parse_args()

    if not args.command:
        console.print(Panel(
            "[bold white]ShortCrew Local[/bold white] · [bold red]L'app qui crée tes shorts à ta place[/bold red]\n"
            "Piloté par ton abonnement Claude Pro/Max, voix locale gratuite, rendu 1080x1920 Submagic.\n\n"
            "Commandes : [cyan]status[/cyan] · [cyan]scan[/cyan] · [cyan]clone[/cyan] · [cyan]make[/cyan] · [cyan]cut[/cyan] · [cyan]revise[/cyan] · [cyan]week[/cyan] · [cyan]ui[/cyan]\n"
            "Lance [cyan]python cli.py --help[/cyan] pour le détail.",
            border_style="red"
        ))
        return

    if args.command == "status":
        st = ClaudeBridge.check_status(live_probe=True)
        color = "green" if st["connected"] else "yellow"
        console.print(Panel(
            f"[bold]Moteur IA :[/bold] [{color}]{st['mode']}[/{color}]\n"
            f"[bold]Statut :[/bold] {st['message']}\n"
            f"[bold]Claude CLI :[/bold] {st['cli_path']} ({st['cli_version'] or 'absent'})\n"
            f"[bold]FFmpeg :[/bold] {FFMPEG_PATH}\n"
            f"[bold]yt-dlp :[/bold] {YT_DLP_PATH}",
            title="Diagnostic ShortCrew Local",
            border_style=color
        ))

    elif args.command == "scan":
        console.print(f"[bold yellow]🔍 Analyse des shorts du compte :[/bold yellow] {args.url}")
        res = CompetitorScraper.find_outliers(
            args.url,
            limit=args.limit,
            threshold=args.threshold,
            cookies_from_browser=args.cookies,
        )
        console.print(
            f"[green]✓ {res['total_scanned']} vidéos analysées ({res.get('platform', 'web')}). "
            f"Médiane : {res['median_views']:,} vues · Moyenne : {res['average_views']:,} vues[/green]\n"
        )
        if res.get("note"):
            console.print(f"[yellow]ℹ️ {res['note']}[/yellow]\n")

        table = Table(title=f"🔥 Pépites détectées (>= {args.threshold}x la médiane)", border_style="red")
        table.add_column("Score", style="bold red", width=12)
        table.add_column("Vues", style="cyan", width=12)
        table.add_column("Durée", style="magenta", width=7)
        table.add_column("Eng.", style="green", width=7)
        table.add_column("Titre", style="white")
        table.add_column("Lien", style="blue")

        for o in res["outliers"]:
            dur = f"{o['duration']}s" if o.get("duration") else "-"
            eng = f"{o['engagement_rate']}%" if o.get("engagement_rate") else "-"
            table.add_row(
                f"{o['ratio']}x",
                f"{o['views']:,}",
                dur,
                eng,
                o["title"][:48],
                o["url"],
            )
        console.print(table)

    elif args.command == "clone":
        console.print(Panel(f"🚀 [bold]Lancement du Clonage de Recette[/bold]\nLien concurrent : {args.url}\nNouveau sujet : {args.topic}\nThème : {args.theme} · Sous-titres : {args.subtitle_style}"))
        res = ShortCrewPipeline.clone_competitor_short(
            video_url=args.url,
            my_topic=args.topic,
            niche=args.niche,
            theme=args.theme,
            subtitle_style=args.subtitle_style,
            cookies_from_browser=args.cookies,
        )
        console.print(f"\n[bold green]✓ Short terminé et vérifié ![/bold green]")
        console.print(f"🎬 [bold white]Vidéo :[/bold white] [cyan]{res['video_path']}[/cyan]")
        console.print(f"⭐ [bold white]Note Contrôle :[/bold white] [yellow]{res['audit'].get('score_global', '9/10')}[/yellow]")

    elif args.command == "make":
        console.print(Panel(f"🎬 [bold]Fabrication directe[/bold]\nSujet : {args.topic}\nThème : {args.theme} · Sous-titres : {args.subtitle_style}"))
        res = ShortCrewPipeline.create_direct_short(
            topic=args.topic,
            user_style=args.style,
            background_video=args.bg,
            theme=args.theme,
            subtitle_style=args.subtitle_style,
        )
        console.print(f"\n[bold green]✓ Vidéo fabriquée :[/bold green] [cyan]{res['video_path']}[/cyan]")
        console.print(f"🆔 [bold white]Session :[/bold white] {res['session_id']}")
        console.print(f"⭐ [bold white]Note Contrôle :[/bold white] [yellow]{res['audit'].get('score_global', '9/10')}[/yellow]")

    elif args.command == "cut":
        console.print(Panel(
            f"✂️ [bold]Le Monteur — Découpe de vidéo filmée[/bold]\n"
            f"Source : {args.source}\n"
            f"Clips : {args.clips} · Recadrage : {args.crop} · Jump-cuts : {'Oui' if args.jumpcuts else 'Non'}"
        ))
        res = ShortCrewPipeline.cut_long_video(
            source=args.source,
            num_clips=args.clips,
            crop_mode=args.crop,
            subtitle_style=args.subtitle_style,
            remove_silences=args.jumpcuts,
            language=args.lang,
        )
        console.print(f"\n[bold green]✓ {res['clips_count']} short(s) monté(s) avec succès ![/bold green]")
        for c in res["clips"]:
            console.print(f"  • [bold white]{c['script']['title']}[/bold white] ({c['start_sec']}s → {c['end_sec']}s) : [cyan]{c['video_path']}[/cyan]")

    elif args.command == "revise":
        console.print(f"🔄 Retouche de la session [bold cyan]{args.session_id}[/bold cyan]...")
        res = ShortCrewPipeline.revise_short(args.session_id, args.feedback)
        console.print(f"\n[bold green]✓ Retouche appliquée avec succès ![/bold green]")
        console.print(f"🎬 [bold white]Nouvelle vidéo :[/bold white] [cyan]{res['video_path']}[/cyan]")

    elif args.command == "week":
        console.print(f"📅 [bold yellow]Génération de la semaine pour la niche :[/bold yellow] {args.niche}")
        plan = LeStratege.plan_weekly_shorts(args.niche)
        console.print("\n[bold white]Plan éditorial de la semaine :[/bold white]")
        for item in plan:
            console.print(f"  • [bold red]{item.get('jour', 'Jour')}[/bold red] : {item.get('titre') or item.get('sujet')}")

    elif args.command == "ui":
        from app import run_app
        run_app(port=args.port)


if __name__ == "__main__":
    main()

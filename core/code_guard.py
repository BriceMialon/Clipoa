"""
Garde-fou sur le code Python Blender écrit par l'IA (moteurs sur mesure).

Le code de l'IA s'exécute dans Blender avec les droits de l'utilisateur. Une consigne dans le prompt
(« interdit : subprocess… ») ne protège de rien : un texte piégé (transcription, titre de vidéo) peut
pousser l'IA à écrire du code qui lit des fichiers privés ou les fait fuiter. On analyse donc le code
AVANT de l'exécuter et on refuse tout ce qui sort de la scène 3D :
- imports limités à une liste blanche (bpy, bmesh, mathutils, math, random, json…) ;
- pas d'exec/eval/open/__import__, pas d'accès aux attributs « dunder » (évasions classiques) ;
- pas d'opérateurs bpy qui lisent/écrivent des fichiers ou ouvrent une URL (wm, script, import/export…) ;
- pas de chargement de fichiers (images.load, texts.load, numpy.fromfile…).

Ce n'est pas un vrai bac à sable (un processus isolé reste la cible), mais ça ferme les chemins évidents.
"""

import ast
from typing import List

ALLOWED_MODULES = {
    "bpy", "bmesh", "mathutils", "math", "random", "json", "colorsys", "itertools", "functools",
    "collections", "re", "string", "time", "typing", "dataclasses", "enum", "statistics", "copy",
    "operator", "textwrap", "heapq", "bisect", "numpy",
}
ALLOWED_PREFIXES = ("mathutils.", "bpy_extras.object_utils", "bpy_extras.view3d_utils")
ALLOWED_FROM_BPY_EXTRAS = {"object_utils", "view3d_utils"}

FORBIDDEN_CALLS = {
    "exec", "eval", "compile", "open", "__import__", "input", "breakpoint", "globals", "locals",
    "vars", "delattr", "memoryview",
}
FORBIDDEN_NAMES = {"__builtins__", "__loader__", "__spec__", "__import__", "__file__"}
# bpy.ops.<module> qui touchent aux fichiers, aux préférences, aux scripts ou au navigateur
FORBIDDEN_OPS_MODULES = {
    "wm", "script", "preferences", "import_scene", "export_scene", "import_mesh", "export_mesh",
    "import_curve", "import_image", "image", "text", "file", "sound", "sequencer", "clip", "buttons",
}
# attributs qui chargent/écrivent des fichiers ou exécutent du code
FORBIDDEN_ATTRS = {
    "load", "execfile", "as_module", "driver_namespace", "addon_install", "addon_enable",
    "fromfile", "tofile", "save", "savez", "savetxt", "loadtxt", "genfromtxt", "memmap",
    "url_open", "system", "popen", "load_scripts", "script_paths", "use_autoexec",
}


class UnsafeCodeError(RuntimeError):
    pass


def _module_ok(name: str) -> bool:
    return name.split(".")[0] in ALLOWED_MODULES or name.startswith(ALLOWED_PREFIXES)


def check_bpy_code(code: str) -> List[str]:
    """Liste des problèmes de sécurité trouvés (vide = code accepté)."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError as e:
        return [f"erreur de syntaxe ligne {e.lineno} : {e.msg}"]
    problems: List[str] = []

    def add(node, msg):
        problems.append(f"ligne {getattr(node, 'lineno', '?')} : {msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _module_ok(a.name):
                    add(node, f"import interdit « {a.name} »")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                add(node, "import relatif interdit")
            elif mod == "bpy_extras":
                for a in node.names:
                    if a.name not in ALLOWED_FROM_BPY_EXTRAS:
                        add(node, f"import interdit « bpy_extras.{a.name} »")
            elif not _module_ok(mod):
                add(node, f"import interdit « {mod} »")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                add(node, f"nom interdit « {node.id} »")
        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                add(node, f"attribut interne interdit « {attr} »")
            elif attr in FORBIDDEN_ATTRS:
                add(node, f"accès interdit « .{attr} »")
            elif attr in FORBIDDEN_OPS_MODULES and isinstance(node.value, ast.Attribute) and node.value.attr == "ops":
                add(node, f"opérateur interdit « bpy.ops.{attr} »")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                add(node, f"fonction interdite « {fn.id}() »")
            if isinstance(fn, ast.Name) and fn.id in ("getattr", "setattr", "hasattr") and len(node.args) >= 2:
                key = node.args[1]
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    add(node, f"{fn.id}() avec un nom calculé interdit")
                else:
                    k = key.value
                    if (k.startswith("__") or k in FORBIDDEN_ATTRS or k in FORBIDDEN_OPS_MODULES):
                        add(node, f"{fn.id}() vers « {k} » interdit")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if "__import__" in v or "__builtins__" in v or "__subclasses__" in v:
                add(node, "texte contenant du code caché interdit")
    return problems


def ensure_safe_bpy_code(code: str) -> None:
    problems = check_bpy_code(code)
    if problems:
        raise UnsafeCodeError("code Blender refusé (sécurité) : " + " ; ".join(problems[:6]))

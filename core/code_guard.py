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
    "textwrap", "heapq", "bisect", "numpy",
}
ALLOWED_SUBMODULES = {
    "mathutils.geometry", "mathutils.noise", "mathutils.kdtree", "mathutils.bvhtree",
    "mathutils.interpolate", "bpy.types", "bpy.data", "bpy.context", "bpy.ops", "bpy.utils",
    "bpy_extras.object_utils", "bpy_extras.view3d_utils",
    "numpy.linalg", "numpy.random", "numpy.fft",
}
ALLOWED_FROM_BPY_EXTRAS = {"object_utils", "view3d_utils"}

FORBIDDEN_CALLS = {
    "exec", "eval", "compile", "open", "__import__", "input", "breakpoint", "globals", "locals",
    "vars", "delattr", "memoryview",
}
FORBIDDEN_NAMES = FORBIDDEN_CALLS | {
    "__builtins__", "__loader__", "__spec__", "__file__",
    "attrgetter", "methodcaller", "itemgetter",
}
_SAFE_REFLECT_FUNCS = {"getattr", "setattr", "hasattr"}
# bpy.ops.<module> qui touchent aux fichiers, aux préférences, aux scripts ou au navigateur
FORBIDDEN_OPS_MODULES = {
    "wm", "script", "preferences", "import_scene", "export_scene", "import_mesh", "export_mesh",
    "import_curve", "import_image", "image", "text", "file", "sound", "sequencer", "clip", "buttons",
}
# attributs qui chargent/écrivent des fichiers ou exécutent du code
FORBIDDEN_ATTRS = {
    "load", "execfile", "as_module", "driver_namespace", "driver_add", "addon_install", "addon_enable",
    "fromfile", "tofile", "save", "savez", "savetxt", "loadtxt", "genfromtxt", "memmap",
    "url_open", "system", "popen", "load_scripts", "script_paths", "use_autoexec",
    "write", "save_render", "save_as_mainfile", "python_file_run",
    "DataSource", "ctypes", "ctypeslib", "modules", "sys", "_os",
    "attrgetter", "methodcaller", "itemgetter",
}


class UnsafeCodeError(RuntimeError):
    pass


def _module_ok(name: str) -> bool:
    return name in ALLOWED_MODULES or name in ALLOWED_SUBMODULES


def check_bpy_code(code: str) -> List[str]:
    """Liste des problèmes de sécurité trouvés (vide = code accepté)."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError as e:
        return [f"erreur de syntaxe ligne {e.lineno} : {e.msg}"]
    problems: List[str] = []

    def add(node, msg):
        problems.append(f"ligne {getattr(node, 'lineno', '?')} : {msg}")

    # Map parent nodes so we can detect aliasing of `getattr`/`bpy.ops` and allow `super().__init__()`.
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

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
            else:
                for a in node.names:
                    if a.name == "*":
                        add(node, f"import générique interdit depuis « {mod} »")
                    elif a.name in FORBIDDEN_NAMES or a.name in FORBIDDEN_ATTRS or (mod == "bpy.ops" and a.name in FORBIDDEN_OPS_MODULES):
                        add(node, f"symbole interdit « {mod}.{a.name} »")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                add(node, f"nom interdit « {node.id} »")
            elif node.id in _SAFE_REFLECT_FUNCS:
                parent = parents.get(node)
                if not (isinstance(parent, ast.Call) and parent.func is node):
                    add(node, f"référence directe interdite « {node.id} »")
        elif isinstance(node, ast.Attribute):
            attr = node.attr
            parent = parents.get(node)
            if attr.startswith("__") and attr.endswith("__"):
                is_super_init = (
                    attr == "__init__"
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "super"
                )
                if not is_super_init:
                    add(node, f"attribut interne interdit « {attr} »")
            elif attr in FORBIDDEN_ATTRS:
                add(node, f"accès interdit « .{attr} »")
            elif attr == "ops":
                # Prevent aliasing `o = bpy.ops; o.wm...`: `.ops` must only be traversed directly.
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    add(node, "alias de bpy.ops interdit")
            elif attr in FORBIDDEN_OPS_MODULES and isinstance(node.value, ast.Attribute) and node.value.attr == "ops":
                add(node, f"opérateur interdit « bpy.ops.{attr} »")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _SAFE_REFLECT_FUNCS:
                has_starred = any(isinstance(arg, ast.Starred) for arg in node.args)
                if has_starred or node.keywords or len(node.args) < 2:
                    add(node, f"{fn.id}() avec arguments dynamiques interdit")
                else:
                    key = node.args[1]
                    if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                        add(node, f"{fn.id}() avec un nom calculé interdit")
                    else:
                        k = key.value
                        if (k.startswith("_") or k in FORBIDDEN_ATTRS or k in FORBIDDEN_OPS_MODULES or k == "ops"):
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

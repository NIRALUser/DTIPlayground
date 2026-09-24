"""Sphinx extension: a reference page per pipeline module, generated from its definition.

Every module of dmriprep and dmrifiberprofile describes itself in a ``<MODULE>.yml`` next to its code: what it does,
what it depends on and every protocol option with its type, default, choices and description. Those files are what
the application reads, so the pages are generated from them at build time rather than written by hand, and a new
module or a new option shows up in the documentation as soon as it is added.

Written into ``docs/modules/`` (a generated folder, not in the repository) when Sphinx starts.
"""

import os
import re
import shutil

import yaml

## the tools whose modules are documented, in the order of the pages
TOOLS = [
    ("dmriprep", "DMRIPrep", "dtiplayground/dmri/preprocessing/modules",
     "Modules of the preprocessing and quality control pipeline. A protocol lists the modules to run and the value of"
     " each of their options; ``dmriprep make-protocols`` writes one with the defaults below."),
    ("dmrifiberprofile", "DMRIFiberProfile", "dtiplayground/dmri/fiberprofile/modules",
     "Modules of the fiber profile pipeline. A protocol lists the modules to run and the value of each of their"
     " options; ``dmrifiberprofile make-protocols`` writes one with the defaults below."),
]
GITHUB = "https://github.com/NIRALUser/DTIPlayground/blob/master"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # the repository
OUT = os.path.join(os.path.dirname(HERE), "modules")   # docs/modules


def esc(text):
    """Text that is safe as RST: the characters that would start inline markup are escaped, so a description may
    contain *, ` or a trailing _ without breaking the page."""
    text = " ".join(str(text).split())
    return re.sub(r"([*`|_\\])", r"\\\1", text)


def literal(value):
    """A default value as inline literal, or 'not set'."""
    if value is None or value == "":
        return "not set"
    if isinstance(value, bool):
        return "``{}``".format(str(value).lower())
    if isinstance(value, (list, tuple)):
        return "empty list" if not value else ", ".join("``{}``".format(v) for v in value)
    if isinstance(value, dict):
        return "" if not value else ", ".join("``{}``: ``{}``".format(k, v) for k, v in value.items())
    return "``{}``".format(value)


def heading(title, char):
    return "{}\n{}\n".format(title, char * len(title))


def option_block(name, spec):
    """One protocol option as a definition list entry with a field list."""
    if not isinstance(spec, dict):
        return "``{}``\n    {}\n\n".format(name, literal(spec))
    out = ["``{}``".format(name)]
    description = spec.get("description") or spec.get("caption") or ""
    if description:
        out.append("    " + esc(description))
        out.append("")
    fields = []
    if spec.get("type"):
        fields.append((":Type:", "``{}``".format(spec["type"])))
    fields.append((":Default:", literal(spec.get("default_value"))))
    condition = spec.get("if")
    if isinstance(condition, dict) and condition:
        fields.append((":Used when:", ", ".join("``{}`` is ``{}``".format(k, v) for k, v in condition.items())))
    if spec.get("hidden"):
        fields.append((":Note:", "not shown in the user interface"))
    if spec.get("disabled"):
        fields.append((":Note:", "disabled"))
    for label, value in fields:
        out.append("    {} {}".format(label, value))
    candidates = spec.get("candidates")
    if isinstance(candidates, list) and candidates:
        out.append("    :Choices:")
        for c in candidates:
            if isinstance(c, dict):
                value = c.get("value")
                value = "``{}``".format("null" if value is None else value)
                text = c.get("description") or c.get("caption") or ""
                out.append("        - {}{}".format(value, " -- " + esc(text) if text else ""))
            else:
                out.append("        - ``{}``".format(c))
    out.append("")
    return "\n".join(out) + "\n"


def module_page(command, definition, source_dir, module):
    """The RST of one module page."""
    name = definition.get("name") or module
    out = [heading(name, "=")]
    description = definition.get("description") or definition.get("caption") or ""
    if description:
        out.append(esc(description) + "\n")

    dependency = definition.get("dependency") or []
    if isinstance(dependency, str):
        dependency = [dependency]
    out.append(":Command: ``{}``".format(command))
    if definition.get("version"):
        out.append(":Module version: {}".format(definition["version"]))
    if definition.get("module_type"):
        out.append(":Module type: ``{}``".format(definition["module_type"]))
    if dependency:
        out.append(":Runs after: {}".format(", ".join("``{}``".format(d) for d in dependency)))
    attributes = definition.get("process_attributes") or []
    if attributes:
        out.append(":Attributes: {}".format(", ".join("``{}``".format(a) for a in attributes)))
    readme = os.path.join(source_dir, module, "README.md")
    if os.path.isfile(readme):
        out.append(":Notes: `{name} README <{gh}/{rel}>`_".format(
            name=name, gh=GITHUB, rel=os.path.relpath(readme, ROOT).replace(os.sep, "/")))
    out.append(":Source: `{rel} <{gh}/{rel}>`_".format(
        gh=GITHUB, rel=os.path.relpath(os.path.join(source_dir, module), ROOT).replace(os.sep, "/")))
    out.append("")

    for key, label in (("global_variables", "Global variables"),
                       ("commandline_variables", "Command line variables"),
                       ("command_line_variables", "Command line variables")):
        values = definition.get(key) or {}
        if isinstance(values, dict) and values:
            out.append(heading(label, "-"))
            out.append("Values this module shares with the other modules of the pipeline"
                       " (``dmriprep run -g <name>=<value>`` sets one).\n")
            for variable in values:
                out.append("- ``{}``".format(variable))
            out.append("")

    protocol = definition.get("protocol") or {}
    out.append(heading("Protocol options", "-"))
    if not protocol:
        out.append("This module has no options.\n")
    else:
        for option, spec in protocol.items():
            out.append(option_block(option, spec))
    return "\n".join(out)


def generate(app=None):
    """Write docs/modules/ from the module definitions."""
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    tool_pages = []
    for command, title, relative, intro in TOOLS:
        source_dir = os.path.join(ROOT, relative)
        if not os.path.isdir(source_dir):
            continue
        modules = sorted(m for m in os.listdir(source_dir)
                         if os.path.isfile(os.path.join(source_dir, m, m + ".yml")))
        rows, pages = [], []
        folder = os.path.join(OUT, command)
        os.makedirs(folder, exist_ok=True)
        for module in modules:
            with open(os.path.join(source_dir, module, module + ".yml")) as fh:
                definition = yaml.safe_load(fh) or {}
            with open(os.path.join(folder, module + ".rst"), "w") as fh:
                fh.write(module_page(command, definition, source_dir, module))
            pages.append("{}/{}".format(command, module))
            summary = definition.get("description") or definition.get("caption") or ""
            rows.append((module, esc(summary), len(definition.get("protocol") or {})))

        page = [heading("{} modules".format(title), "=")]
        page.append(intro + "\n")
        page.append(".. list-table::")
        page.append("   :header-rows: 1")
        page.append("   :widths: 25 60 15\n")
        page.append("   * - Module\n     - Purpose\n     - Options")
        for module, summary, count in rows:
            page.append("   * - :doc:`{m} <{c}/{m}>`\n     - {s}\n     - {n}".format(
                m=module, c=command, s=summary or "\\-", n=count))
        page.append("")
        page.append(".. toctree::")
        page.append("   :maxdepth: 1")
        page.append("   :hidden:\n")
        for p in pages:
            page.append("   {}".format(p))
        page.append("")
        with open(os.path.join(OUT, command + ".rst"), "w") as fh:
            fh.write("\n".join(page))
        tool_pages.append(command)

    index = [heading("Modules", "=")]
    index.append("A pipeline is a list of modules, and a protocol gives the value of each of their options. These"
                 " pages are generated from the module definitions (``<MODULE>.yml`` next to the code of each"
                 " module), so they describe the modules of this version.\n")
    index.append("A module writes its results into its own folder of the output directory, and the pipeline passes"
                 " the image from one module to the next. ``make-protocols`` writes a protocol with the defaults"
                 " listed here, which can then be edited.\n")
    index.append(".. toctree::")
    index.append("   :maxdepth: 2\n")
    for command in tool_pages:
        index.append("   {}".format(command))
    index.append("")
    with open(os.path.join(OUT, "index.rst"), "w") as fh:
        fh.write("\n".join(index))


def setup(app):
    app.connect("builder-inited", lambda _app: generate(_app))
    return {"parallel_read_safe": True, "parallel_write_safe": True}


if __name__ == "__main__":  # generating them by hand is useful when checking the output
    generate()
    print("written to {}".format(OUT))

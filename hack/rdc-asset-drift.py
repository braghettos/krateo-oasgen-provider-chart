#!/usr/bin/env python3
"""Compare the RDC asset templates that exist in two places, and fail on semantic drift.

The oasgen-provider repo carries reference copies under manifests/rdc/; this chart carries the
copies that actually ship, under chart/assets/rdc/ (mounted into the provider as
/tmp/assets/rdc-*). Nothing keeps the two in sync, and three production bugs have come from that:

  * the chart's ConfigMap never supplied REST_CONTROLLER_SERVICEACCOUNT_NAME/_NAMESPACE, so every
    RDC >= 0.12.0 crash-looped                                     (chart#18)
  * the chart's ClusterRole lacked roles/rolebindings, so secretRef could not self-provision
    its per-CR Role                                                (fixed in chart 0.9.11)
  * the repo's ClusterRole lacked secrets, so that same Role creation failed Kubernetes'
    privilege-escalation check                                     (chart#20)

Each bug was invisible from the other install path, which is why they were found one at a time.

This does NOT require the two copies to be identical — they differ deliberately (the chart adds
Helm labels, a three-part resource name, a .Values.rdc.env passthrough). It compares only the
things that bit us: the SET of RBAC grants, and the SET of ConfigMap data keys.

Exit 0 = aligned, 1 = drift, 2 = could not read an input.
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# The chart escapes second-stage Go templating so Helm emits a literal {{ .x }} for the provider to
# render later, and it uses BOTH spellings: the backtick form {{`{{ .x }}`}} and the quoted form
# {{ "{{" }} .x {{ "}}" }}. Unwrap both, then flatten what remains. We compare grants and key names,
# never rendered values, so any placeholder collapsing to the same token is fine.
BACKTICK = re.compile(r"\{\{`(.*?)`\}\}", re.S)
QUOTED = re.compile(r'\{\{\s*"\{\{"\s*\}\}(.*?)\{\{\s*"\}\}"\s*\}\}', re.S)
# A line that is nothing but a control-flow action ({{- if }}, {{- end }}, {{- range }} …) carries no
# YAML structure — dropping it keeps the document parseable, whereas substituting a token would
# inject a bare scalar between list items and break the parse.
CONTROL_LINE = re.compile(
    r"^\s*\{\{-?\s*(if|else|end|range|with|define|template|block)\b.*?-?\}\}\s*$",
    re.M,
)
INLINE = re.compile(r"\{\{.*?\}\}", re.S)


def detemplate(text: str) -> str:
    text = BACKTICK.sub(lambda m: m.group(1), text)  # unwrap one escaping level
    text = QUOTED.sub(r"\1", text)
    text = CONTROL_LINE.sub("", text)
    return INLINE.sub("TPL", text)


def load_doc(text: str):
    try:
        return yaml.safe_load(detemplate(text))
    except yaml.YAMLError as exc:
        print(f"  (unparseable after de-templating: {exc})", file=sys.stderr)
        return None


def embedded(path: Path, key: str):
    """Pull one templated document out of a ConfigMap's data block."""
    doc = yaml.safe_load(detemplate(path.read_text()))
    if not doc or "data" not in doc or key not in doc["data"]:
        return None
    return yaml.safe_load(doc["data"][key])


def grants(doc) -> set:
    """Normalise a ClusterRole/Role into a comparable set of grants.

    Rules whose apiGroups or resources are template placeholders are dropped: they name the
    per-resource CRD, which is legitimately spelled differently in the two copies.
    """
    out = set()
    for rule in (doc or {}).get("rules") or []:
        groups = tuple(sorted(str(g) for g in rule.get("apiGroups") or []))
        resources = tuple(sorted(str(r) for r in rule.get("resources") or []))
        verbs = tuple(sorted(str(v) for v in rule.get("verbs") or []))
        if any("TPL" in x for x in groups + resources):
            continue
        out.add((groups, resources, verbs))
    return out


def data_keys(doc) -> set:
    """ConfigMap data keys, minus placeholder keys produced by a range block."""
    return {k for k in ((doc or {}).get("data") or {}) if "TPL" not in k}


def report(label: str, repo_set: set, chart_set: set) -> bool:
    only_repo = repo_set - chart_set
    only_chart = chart_set - repo_set
    if not only_repo and not only_chart:
        print(f"OK    {label}: aligned ({len(repo_set)} entries)")
        return True
    print(f"DRIFT {label}:")
    for item in sorted(only_repo, key=str):
        print(f"        only in oasgen-provider manifests/rdc/: {item}")
    for item in sorted(only_chart, key=str):
        print(f"        only in chart assets/rdc/:              {item}")
    return False


def main(repo_root: Path, chart_root: Path) -> int:
    try:
        repo_cr = embedded(repo_root / "manifests/rdc/rbac.yaml", "clusterrole.yaml")
        repo_cm = embedded(repo_root / "manifests/rdc/cm.yaml", "configmap.yaml")
        chart_cr = load_doc((chart_root / "chart/assets/rdc/rbac/clusterrole.yaml").read_text())
        chart_cm = load_doc((chart_root / "chart/assets/rdc/configmap.yaml").read_text())
    except OSError as exc:
        print(f"could not read an input: {exc}", file=sys.stderr)
        return 2

    if any(d is None for d in (repo_cr, repo_cm, chart_cr, chart_cm)):
        print("could not parse one of the templates", file=sys.stderr)
        return 2

    ok = report("RDC ClusterRole grants", grants(repo_cr), grants(chart_cr))
    ok &= report("RDC ConfigMap data keys", data_keys(repo_cm), data_keys(chart_cm))

    if not ok:
        print(
            "\nThese two copies feed different install paths (manifests/ = local dev, "
            "chart assets/ = what ships), so a difference here is a bug users hit on one path "
            "and not the other. Add the missing entry to whichever side lacks it — or, if the "
            "difference is deliberate, teach this script to ignore it.",
            file=sys.stderr,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <oasgen-provider-root> <chart-root>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))

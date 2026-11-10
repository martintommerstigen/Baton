"""Validate the coordination registry without modifying any research repository."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
REGISTRY=ROOT/"project-map"/"tasks.json"
VALID_PROJECTS={"Baton","GTRCM","RustWorld"}
VALID_PHASES={"research","discovery","implementation","verification","blocked"}

def validate(data):
    assert data["schema"]=="gtrcm-project-map/v1"
    tasks=data["tasks"]
    ids=[t["id"] for t in tasks]
    assert len(ids)==19 and len(ids)==len(set(ids))
    assert {t["project"] for t in tasks}==VALID_PROJECTS
    assert all(t["phase"] in VALID_PHASES for t in tasks)
    assert all(t["source"].startswith("https://github.com/martintommerstigen/") for t in tasks)
    assert all(t["verified_done"] is False for t in tasks)
    assert all(dep in ids and dep!=t["id"] for t in tasks for dep in t["dependencies"])
    visiting=set();visited=set();byid={t["id"]:t for t in tasks}
    def visit(id):
        if id in visiting: raise ValueError("Dependency cycle at "+id)
        if id in visited: return
        visiting.add(id)
        for dep in byid[id]["dependencies"]: visit(dep)
        visiting.remove(id);visited.add(id)
    for id in ids: visit(id)
    automation_path=ROOT/'project-map'/'automations.json'
    if automation_path.exists():
        mapping=json.loads(automation_path.read_text())
        assert mapping['schema']=='gtrcm-automation-map/v1'
        aids=[a['id'] for a in mapping['automations']]
        assert len(aids)==len(set(aids))
        assert all(tid in ids for a in mapping['automations'] for tid in a['tasks'])
        assert all(tid in ids for tid in mapping['unassigned'])
        assigned={tid for a in mapping['automations'] for tid in a['tasks']}
        assert not (set(mapping['unassigned']) & assigned)
    return len(tasks)

if __name__=="__main__":
    print("Validated",validate(json.loads(REGISTRY.read_text())),"tasks")

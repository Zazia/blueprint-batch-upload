"""Local upload planning and evidence ledger. Never opens PACK members or calls JGTGL.

Run with uv run scripts/upload_plan.py --help. All persisted text is UTF-8.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(value):
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def project(context):
    return tuple(str(context[k]).rstrip("/") for k in ("site", "WID", "OrgId"))


def scope(context):
    return tuple(str(context[k]) for k in ("unit", "profession"))


def validate_context(c):
    for key in ("site", "WID", "OrgId", "unit", "profession"):
        if not str(c.get(key, "")).strip():
            raise ValueError(f"缺少上下文: {key}")
    if c["unit"] in ("所有", "全部", "all"):
        raise ValueError("上传计划必须指定具体单体")


def row_key(c, bpid):
    return json.dumps([*scope(c), str(bpid)], ensure_ascii=False)


def versions(row):
    return row.get("versions", row.get("xml", []))


def missing_completion(rows):
    return [r for r in rows if (r.get("BGID") not in (None, "") or r.get("selectedEver") is True)
            and not any(v.get("status") == "竣工" for v in versions(r))]


def safe_name(name):
    if not name or name != Path(name).name or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError(f"非法文件名: {name}")
    if name.endswith((" ", ".")) or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I):
        raise ValueError(f"Windows 保留文件名: {name}")


@contextmanager
def locked(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".upload.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("项目正在写入；若上次崩溃，先核查运行与改名日志再移除 .upload.lock")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield root
    finally:
        lock.unlink(missing_ok=True)


def load_catalog(root, context):
    path = root / "catalog.json"
    cat = read(path) if path.exists() else {"schemaVersion": 1, "context": context, "rows": {}, "revisions": []}
    if project(cat["context"]) != project(context):
        raise ValueError("项目账本与站点/工程/单位不一致")
    return cat


def validate_snapshot(snapshot):
    validate_context(snapshot["context"])
    seen = set()
    for r in snapshot["rows"]:
        bpid = str(r.get("BPID", ""))
        if not bpid or bpid in seen:
            raise ValueError("快照含空或重复 BPID")
        seen.add(bpid)
        for key in ("WID", "OrgId"):
            if key in r and str(r[key]) != str(snapshot["context"][key]):
                raise ValueError(f"快照行的 {key} 与上下文不一致")
        if not isinstance(versions(r), list):
            raise ValueError("版本列表必须是数组")


def remember_selected(cat, context, rows):
    """Keep observed selection history even if a later response has an empty BGID."""
    result = []
    for row in rows:
        old = cat["rows"].get(row_key(context, row["BPID"]), {}).get("system", {})
        selected = any(r.get("selectedEver") is True or r.get("BGID") not in (None, "") for r in (row, old))
        result.append({**row, **({"selectedEver": True} if selected else {})})
    return result


def sync(root, snapshot):
    validate_snapshot(snapshot)
    with locked(root) as root:
        c = snapshot["context"]
        cat = load_catalog(root, c)
        drift = []
        observed = set()
        for r in remember_selected(cat, c, snapshot["rows"]):
            key = row_key(c, r["BPID"])
            observed.add(key)
            old = cat["rows"].get(key)
            if old and old["system"] != r:
                drift.append(str(r["BPID"]))
            cat["rows"][key] = {"drawingId": old["drawingId"] if old else uuid.uuid4().hex,
                                 "scope": list(scope(c)), "system": r,
                                 "status": old.get("status", "unknown") if old else "unknown",
                                 "observedAt": now(), "source": "system-snapshot"}
        # Missing rows are retained; even a complete snapshot does not prove cancellation.
        cat["lastScope"] = {"scope": list(scope(c)), "complete": snapshot.get("complete") is True,
                            "observedKeys": sorted(observed), "at": now()}
        write(root / "snapshots" / (uuid.uuid4().hex + ".json"), snapshot)
        write(root / "catalog.json", cat)
        return {"observed": len(observed), "changedBPIDs": drift, "complete": snapshot.get("complete") is True}


def make_plan(root, snapshot, request):
    """One scope per plan. Explicit add/cancel intents; never infer deletion from absence."""
    validate_snapshot(snapshot)
    c = snapshot["context"]
    if request["mode"] not in ("initial", "change", "completion"):
        raise ValueError("mode 必须是 initial/change/completion")
    if not request.get("expectedStatus"):
        raise ValueError("填写当前页面阶段的 expectedStatus，不能猜测")
    with locked(root) as root:
        cat = load_catalog(root, c)
        write(root / "catalog.json", cat)
        aliases_path = root / "aliases.json"
        aliases = read(aliases_path) if aliases_path.exists() else []
        rows = remember_selected(cat, c, snapshot["rows"])
        snapshot = {**snapshot, "rows": rows}
        reusable = []
        for previous_id in request.get("reuseVerifiedFrom", []):
            previous = read(run_path(root, previous_id))
            if (project(previous["context"]) != project(c) or scope(previous["context"]) != scope(c)
                    or previous["mode"] != request["mode"] or previous["expectedStatus"] != request["expectedStatus"]):
                raise ValueError("复用批次的范围或阶段不同")
            if previous.get("finish"):
                raise ValueError("已提交批次不能作为本次新上传的免传依据")
            for old in previous["items"]:
                if old["status"] == "verified":
                    reusable.append((previous_id, old))
        plan = {"schemaVersion": 1, "runId": uuid.uuid4().hex, "createdAt": now(), "context": c,
                "mode": request["mode"], "expectedStatus": request["expectedStatus"],
                "completeRequested": request.get("completeRequested", True), "snapshot": snapshot,
                "items": [], "blockers": [], "warnings": [], "finish": None}
        if snapshot.get("complete") is not True:
            plan["blockers"].append("系统范围未完整采集，不能完成上传或自动判定新增")
        if plan["mode"] == "completion" and any("BGID" not in r or ("versions" not in r and "xml" not in r) for r in rows):
            plan["blockers"].append("竣工快照缺 BGID 或版本字段，不能将未知当作无缺项")
        for spec in request.get("files", []):
            item = {"itemId": uuid.uuid4().hex, "action": spec.get("action", "auto"),
                    "kind": spec.get("kind", "drawing"), "status": "planned", "issues": []}
            plan["items"].append(item)
            try:
                if item["action"] not in ("auto", "update", "add", "cancel"):
                    raise ValueError("action 无效")
                if item["kind"] not in ("drawing", "directory", "cancellation", "material"):
                    raise ValueError("kind 无效")
                file = Path(spec["path"]).resolve(strict=True)
                if not file.is_file() or not file.stat().st_size:
                    raise ValueError("文件为空或不是文件")
                if file.suffix.lower() not in (".pack", ".pdf", ".gdb"):
                    raise ValueError("不支持的扩展名；不读取包内或用改后缀转换格式")
                code, sep, title = file.stem.partition("_")
                code, title = spec.get("code", code), spec.get("name", title)
                if not code or not title or (not sep and not (spec.get("code") and spec.get("name"))):
                    raise ValueError("需 图号_图名 或在清单明确 code/name")
                item.update({"path": str(file), "originalName": file.name, "originalCode": code,
                             "name": title, "sha256": digest(file), "size": file.stat().st_size})
                target = []
                if spec.get("BPID") is not None:
                    target = [r for r in rows if str(r["BPID"]) == str(spec["BPID"])]
                    if len(target) != 1:
                        raise ValueError("指定 BPID 不在当前完整范围或不唯一")
                else:
                    relevant = [a for a in aliases if a["scope"] == list(scope(c)) and norm(a["name"]) == norm(title)]
                    if len(relevant) > 1:
                        relevant = [a for a in relevant if norm(code) in (norm(a["originalCode"]), norm(a["uploadCode"]))]
                    if len(relevant) > 1:
                        raise ValueError("同图名映射不唯一，请指定 BPID")
                    if relevant:
                        a = relevant[0]
                        target = [r for r in rows if (a.get("BPID") is not None and str(r["BPID"]) == str(a["BPID"]))
                                  or (norm(r["code"]) == norm(a["uploadCode"]) and norm(r["fullName"]) == norm(title))]
                        if not target:
                            raise ValueError("已有映射在系统快照中找不到，先对账，不能重复新增")
                    if not target:
                        target = [r for r in rows if norm(r["code"]) == norm(code)]
                    if len(target) > 1:
                        target = [r for r in target if norm(r["fullName"]) == norm(title)]
                    if not target:
                        target = [r for r in rows if norm(r["fullName"]) == norm(title)]
                if len(target) > 1:
                    raise ValueError("图纸对应不唯一，请指定 BPID")
                if target:
                    r = target[0]
                    reuse = [(rid, old) for rid, old in reusable if old.get("BPID") == str(r["BPID"])
                             and old["sha256"] == item["sha256"] and old["kind"] == item["kind"]
                             and norm(old["uploadCode"]) == norm(r["code"])
                             and (old["action"] == item["action"] or (item["action"] in ("auto", "update") and old["action"] != "cancel"))
                             and any(str(v.get("VSID")) == str(old["result"]["VSID"])
                                     and v.get("status") == request["expectedStatus"] for v in versions(r))]
                    if item["action"] == "add" and not reuse:
                        raise ValueError("增补与已有图纸冲突，不能重复新增")
                    if norm(r["fullName"]) != norm(title) and not spec.get("matchConfirmed"):
                        raise ValueError("图号相同但图名不同，核对后设置 matchConfirmed 或纠正目标")
                    item.update({"BPID": str(r["BPID"]), "uploadCode": r["code"], "before": versions(r),
                                 "action": "cancel" if item["action"] == "cancel" else "update"})
                    if reuse:
                        rid, old = reuse[-1]
                        item.update({"status": "verified", "action": old["action"],
                                     "result": {**old["result"], "itemId": item["itemId"]},
                                     "reusedFrom": {"runId": rid, "itemId": old["itemId"]}})
                else:
                    allowed = item["action"] == "add" or (plan["mode"] == "initial" and item["action"] == "auto")
                    if not allowed or snapshot.get("complete") is not True:
                        item["candidates"] = [str(r["BPID"]) for r in rows if SequenceMatcher(None, norm(title), norm(r["fullName"])).ratio() >= .75]
                        raise ValueError("未匹配；相似项仅供核查，明确增补才能新增")
                    item.update({"BPID": None, "uploadCode": unicodedata.normalize("NFKC", code).strip().replace(".", "-"), "before": [], "action": "add"})
                    if any(norm(r["code"]) == norm(item["uploadCode"]) for r in rows):
                        raise ValueError("点号转换后与系统已有图号冲突")
                if item["action"] == "cancel" and item["kind"] != "cancellation":
                    raise ValueError("取消图纸必须提供 kind=cancellation 的取消变更单")
                item["uploadName"] = f'{item["uploadCode"]}_{title}{file.suffix.lower()}'
                safe_name(item["uploadName"])
                item["route"] = "native-add" if item["action"] == "add" else ("B" if "." in item["uploadCode"] else "A")
                if item["action"] != "add" and (item["action"] == "cancel" or file.suffix.lower() != ".pack"):
                    item["route"] = "native-target"  # Preserve native PDF/type/sign checks.
                item["directoryFor"] = [str(x) for x in spec.get("directoryFor", [])]
                item["directoryImpact"] = spec.get("directoryImpact", False)
            except (ValueError, OSError, KeyError) as exc:
                item["status"] = "blocked"
                item["issues"].append(str(exc))
        occupied = {}
        for item in plan["items"]:
            if item["status"] not in ("planned", "verified"):
                continue
            key = ("bpid", item["BPID"]) if item["BPID"] else ("code", norm(item["uploadCode"]))
            if key in occupied:
                other = occupied[key]
                for x in (other, item):
                    x["status"] = "blocked"
                    x["issues"].append("多个计划项指向同一图纸或转换后同图号")
            occupied[key] = item
        changed = [i for i in plan["items"] if i.get("kind") != "directory" and
                   (i["action"] in ("add", "cancel") or i.get("directoryImpact"))]
        directories = [i for i in plan["items"] if i["kind"] == "directory" and i["status"] in ("planned", "verified")]
        if plan["mode"] != "initial" and changed:
            for i in changed:
                identity = str(i.get("BPID") or i.get("originalCode", ""))
                identities = {identity}
                if i["action"] == "add":
                    identities.add(str(i.get("originalCode", "")))
                if not any(identities.intersection(d.get("directoryFor", [])) for d in directories):
                    plan["blockers"].append(f"缺覆盖 {identity or i['itemId']} 的新版图纸目录；directoryFor 明确其范围")
        if plan["mode"] == "initial" and not directories:
            plan["warnings"].append("未识别正式图纸目录，请提醒用户；本地账本不是正式目录")
        supplied = {i.get("BPID") for i in plan["items"] if i["status"] in ("planned", "verified")}
        if plan["mode"] == "completion":
            for r in missing_completion(rows):
                if str(r["BPID"]) not in supplied:
                    plan["blockers"].append(f"缺竣工成品: {r['BPID']} {r['code']} {r['fullName']}")
        if not plan["items"]:
            plan["warnings"].append("无文件项，仅能对已完成上传的任务进行有证据的收尾")
        write(root / "runs" / plan["runId"] / "plan.json", plan)
        return plan


def rename(root, run_id):
    """Journal two-phase in-place rename. No overwrite, resume after either phase."""
    with locked(root) as root:
        path = run_path(root, run_id)
        p = read(path)
        if p.get("finish"):
            raise ValueError("已完成的批次不能再改名")
        journal = path.with_name("rename.json")
        if journal.exists():
            moves = read(journal)
        else:
            moves = []
            for i in p["items"]:
                if i["status"] != "planned" or i["action"] == "cancel":
                    continue
                src = Path(i["path"])
                dst = src.with_name(i["uploadName"])
                if src.name != dst.name:
                    moves.append({"itemId": i["itemId"], "src": str(src), "dst": str(dst),
                                  "tmp": str(src.with_name(".rename-" + uuid.uuid4().hex)), "sha256": i["sha256"]})
            sources = [norm(m["src"]) for m in moves]
            if len(set(sources)) != len(sources):
                raise ValueError("同一文件服务多个目标时不能原地多重改名；取消单用原生按目标上传")
            dests = [norm(m["dst"]) for m in moves]
            if len(set(dests)) != len(dests):
                raise ValueError("目标文件名冲突")
            for m in moves:
                if digest(m["src"]) != m["sha256"]:
                    raise ValueError("源文件内容已变化，重新计划")
                if Path(m["dst"]).exists() and norm(m["dst"]) not in sources:
                    raise ValueError("目标文件已存在，拒绝覆盖")
            write(journal, {"phase": "staging", "moves": moves})
            moves = read(journal)
        if moves["phase"] == "staging":
            for m in moves["moves"]:
                src, tmp = Path(m["src"]), Path(m["tmp"])
                check = tmp if tmp.exists() else src
                if digest(check) != m["sha256"]:
                    raise ValueError("改名日志与文件不一致，暂停恢复")
                if not tmp.exists():
                    src.rename(tmp)
            moves["phase"] = "placing"
            write(journal, moves)
        if moves["phase"] == "placing":
            for m in moves["moves"]:
                tmp, dst = Path(m["tmp"]), Path(m["dst"])
                if tmp.exists():
                    if dst.exists():
                        raise ValueError("恢复时目标被占用，拒绝覆盖")
                    if digest(tmp) != m["sha256"]:
                        raise ValueError("临时文件内容变化")
                    tmp.rename(dst)
                elif not dst.exists() or digest(dst) != m["sha256"]:
                    raise ValueError("改名恢复找不到正确目标")
            moves["phase"] = "done"
            write(journal, moves)
        by_id = {m["itemId"]: m for m in moves["moves"]}
        for i in p["items"]:
            if i["itemId"] in by_id:
                i["path"] = by_id[i["itemId"]]["dst"]
        save_aliases(root, p, verified=False)
        write(path, p)
        return {"renamed": len(by_id), "journal": str(journal)}


def run_path(root, run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("runId 格式不正确")
    return Path(root) / "runs" / run_id / "plan.json"


def save_aliases(root, plan, verified):
    file = root / "aliases.json"
    data = read(file) if file.exists() else []
    for i in plan["items"]:
        if i["status"] == "blocked" or "uploadCode" not in i or i["action"] == "cancel":
            continue
        if verified and i["status"] != "verified":
            continue
        a = {"scope": list(scope(plan["context"])), "name": i["name"], "originalCode": i["originalCode"],
             "originalName": i["originalName"], "uploadName": i["uploadName"], "uploadCode": i["uploadCode"],
             "BPID": i.get("BPID"), "runId": plan["runId"], "state": "verified" if verified else "applied",
             "ruleVersion": 1}
        data = [x for x in data if not (x["scope"] == a["scope"] and x["name"] == a["name"] and x["originalCode"] == a["originalCode"])]
        data.append(a)
    write(file, data)


def record(root, run_id, evidence):
    """Accept per-item, post-upload server readback; does not claim to fetch it itself."""
    with locked(root) as root:
        path = run_path(root, run_id)
        p = read(path)
        if p.get("finish"):
            raise ValueError("已完成的批次不能再修改回执")
        snap = evidence["snapshot"]
        validate_snapshot(snap)
        if project(snap["context"]) != project(p["context"]) or scope(snap["context"]) != scope(p["context"]):
            raise ValueError("回读上下文不同")
        results = evidence.get("items", [])
        if len({r["itemId"] for r in results}) != len(results):
            raise ValueError("重复 itemId")
        index = {i["itemId"]: i for i in p["items"]}
        for result in results:
            if result["itemId"] not in index:
                raise ValueError("未知 itemId")
            i = index[result["itemId"]]
            state = result["state"]
            if i["status"] == "blocked":
                raise ValueError("blocked 项需先重新计划，不能以回执跳过预检")
            if state not in ("verified", "failed", "unknown", "processing"):
                raise ValueError("无效结果状态")
            if state == "verified":
                if not result.get("evidenceRef") or result.get("fileSha256") != i["sha256"]:
                    raise ValueError("缺少本次文件哈希或证据引用")
                bpid = str(result["BPID"])
                if i.get("BPID") and i["BPID"] != bpid:
                    raise ValueError("回执挂到错误 BPID")
                matches = [r for r in snap["rows"] if str(r["BPID"]) == bpid]
                if len(matches) != 1 or norm(matches[0]["code"]) != norm(i["uploadCode"]):
                    raise ValueError("回读图号/BPID 不匹配")
                vs = [v for v in versions(matches[0]) if str(v.get("VSID")) == str(result["VSID"])]
                if len(vs) != 1 or vs[0].get("status") != p["expectedStatus"]:
                    raise ValueError("回读版本或阶段不匹配")
                if i["action"] == "add" and bpid in {str(r["BPID"]) for r in p["snapshot"]["rows"]}:
                    raise ValueError("增补误覆盖原记录")
                if any(str(v.get("VSID")) == str(result["VSID"]) for v in i["before"]):
                    if not result.get("replacementEvidence"):
                        raise ValueError("仍是上传前版本；同 VSID 更新须给出内容替换证据")
                if Path(i["path"]).suffix.lower() == ".pack" and result.get("processing") != "success":
                    raise ValueError("PACK 解压尚未成功")
                i["BPID"] = bpid
            i.update({"status": state, "result": result})
        write(path.with_name("evidence-" + uuid.uuid4().hex + ".json"), evidence)
        write(path, p)
        save_aliases(root, p, verified=True)
        cat = load_catalog(root, p["context"])
        for r in remember_selected(cat, p["context"], snap["rows"]):
            key = row_key(p["context"], r["BPID"])
            old = cat["rows"].get(key, {})
            cat["rows"][key] = {**old, "drawingId": old.get("drawingId", uuid.uuid4().hex),
                                 "scope": list(scope(p["context"])), "system": r, "observedAt": now(),
                                 "status": old.get("status", "unknown")}
        write(root / "catalog.json", cat)
        return report(p)


def finalize(root, run_id, receipt):
    with locked(root) as root:
        path = run_path(root, run_id)
        p = read(path)
        if not p["completeRequested"]:
            raise ValueError("用户限制为部分/试传，不得完成整个上传节点")
        if p["blockers"] or any(i["status"] != "verified" for i in p["items"]):
            raise ValueError("仍有缺件/未知/未验证项，不能记录完成上传")
        snap = receipt["snapshot"]
        validate_snapshot(snap)
        if project(snap["context"]) != project(p["context"]) or scope(snap["context"]) != scope(p["context"]):
            raise ValueError("收尾回读范围不同")
        if snap.get("complete") is not True:
            raise ValueError("收尾回读范围不完整")
        cat = load_catalog(root, p["context"])
        snap = {**snap, "rows": remember_selected(cat, p["context"], snap["rows"])}
        if p["mode"] == "completion" and (any("BGID" not in r or ("versions" not in r and "xml" not in r) for r in snap["rows"]) or missing_completion(snap["rows"])):
            raise ValueError("竣工必传仍缺项或字段缺失，取消标记不能豁免")
        for i in p["items"]:
            rr = [r for r in snap["rows"] if str(r["BPID"]) == i["BPID"]]
            if len(rr) != 1 or norm(rr[0]["code"]) != norm(i["uploadCode"]) or not any(
                    str(v.get("VSID")) == str(i["result"]["VSID"]) and v.get("status") == p["expectedStatus"]
                    for v in versions(rr[0])):
                raise ValueError("收尾时目标版本漂移，重新核对")
        if receipt.get("accepted") is not True or not receipt.get("evidenceRef") or not receipt.get("serverState"):
            raise ValueError("缺少完成上传成功响应及状态回读证据")
        p["finish"] = {**receipt, "recordedAt": now()}
        cat = load_catalog(root, p["context"])
        for r in snap["rows"]:
            key = row_key(p["context"], r["BPID"])
            old = cat["rows"].get(key, {})
            cat["rows"][key] = {**old, "drawingId": old.get("drawingId", uuid.uuid4().hex),
                                 "scope": list(scope(p["context"])), "system": r, "observedAt": now(),
                                 "status": old.get("status", "unknown")}
        for i in p["items"]:
            key = row_key(p["context"], i["BPID"])
            cat["rows"][key]["status"] = "cancelled-submitted" if i["action"] == "cancel" else "active"
        if run_id not in cat["revisions"]:
            cat["revisions"].append(run_id)
        write(root / "revisions" / (run_id + ".json"), p)
        write(root / "catalog.json", cat)
        write(path, p)
        return report(p)


def report(p):
    counts = {}
    for i in p["items"]:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    return {"runId": p["runId"], "mode": p["mode"], "counts": counts,
            "total": len(p["items"]), "blockers": p["blockers"], "warnings": p["warnings"],
            "completeUpload": bool(p["finish"]), "items": p["items"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="项目长期数据目录，不是图纸目录")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sync"); s.add_argument("snapshot")
    s = sub.add_parser("plan"); s.add_argument("snapshot"); s.add_argument("request")
    for command in ("rename", "report", "record", "finalize"):
        s = sub.add_parser(command); s.add_argument("run_id")
        if command in ("record", "finalize"):
            s.add_argument("evidence")
    args = parser.parse_args()
    try:
        if args.command == "sync":
            result = sync(args.project, read(args.snapshot))
        elif args.command == "plan":
            result = make_plan(args.project, read(args.snapshot), read(args.request))
        elif args.command == "rename":
            result = rename(args.project, args.run_id)
        elif args.command == "report":
            result = report(read(run_path(args.project, args.run_id)))
        else:
            result = globals()[args.command](args.project, args.run_id, read(args.evidence))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"错误: {exc}\n")


if __name__ == "__main__":
    main()

"""Canonical corpus mapping and exact revision validation for V2 tools."""
from pathlib import Path

def verify_source_revision(corpus, org, space, document_id, revision):
    prefix=f"{org}/{space}/"
    if not isinstance(document_id,str) or not document_id.startswith(prefix):
        raise PermissionError("TENANT_LEAK: source outside fixed principal")
    rel=document_id[len(prefix):].removesuffix(".md")
    parts=Path(rel).parts
    if not rel or Path(rel).is_absolute() or any(p in ("", ".", "..") for p in parts):
        raise PermissionError("invalid canonical source identifier")
    root=Path(corpus); org_root=root/org; scope=org_root/space
    if org_root.is_symlink() or scope.is_symlink(): raise PermissionError("symlinked principal scope rejected")
    source=scope.joinpath(*parts[:-1],parts[-1]+".md")
    cursor=scope
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink(): raise PermissionError("symlinked evidence source rejected")
    if source.is_symlink(): raise PermissionError("symlinked evidence source rejected")
    real=source.resolve(strict=True); real.relative_to(scope.resolve(strict=True))
    data=real.read_bytes().decode("utf-8")
    if not data.startswith("---\n"): raise ValueError("source lacks frontmatter revision")
    end=data.find("\n---",4)
    if end<0: raise ValueError("malformed source frontmatter")
    meta={}
    for line in data[4:end].splitlines():
        key,sep,value=line.partition(":")
        if sep: meta[key.strip()]=value.strip().strip("\\\"'")
    if meta.get("organization_id",org)!=org or meta.get("knowledge_space_id",space)!=space:
        raise PermissionError("source frontmatter principal mismatch")
    expected_id=f"{org}/{space}/{Path(rel).as_posix()}"
    if meta.get("document_id",expected_id)!=expected_id: raise PermissionError("source document identifier mismatch")
    if meta.get("revision")!=revision: raise ValueError("retriever revision differs from current source")
    return len(data.encode("utf-8"))

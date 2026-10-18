"""Post-pilot repair: deterministic native assignment preparation (not rerun).

Use one trusted question/session pair to create the entire message. The native
coordinator must pass these exact bytes or an immutable message file, rather
than manually recopying question text, authority or bearer capabilities.
"""
import hashlib,json,shlex
from pathlib import Path

def build_prompt(common_prompt,question,session,port,repo_root):
    for qkey,skey in [('id','question_id'),('organization_id','organization_id'),('knowledge_space_id','knowledge_space_id')]:
        if question[qkey]!=session[skey]:raise ValueError('Question and trusted session assignment differ')
    if hashlib.sha256(session['handle'].encode()).hexdigest()!=session['token_sha256']:
        raise ValueError('Session capability digest mismatch')
    if not 1<=int(port)<=65535:raise ValueError('Invalid broker port')
    client=Path(repo_root).resolve()/'benchkit/v2/session_client.py'
    command=f"python3 {shlex.quote(str(client))} --port {int(port)} --handle {shlex.quote(session['handle'])} --request JSON"
    schema='Request JSON examples: {"op":"list"}; {"op":"search","question":"query text","top_k":5}; {"op":"read","document_id":"canonical source ID"}. Scope/path overrides are forbidden.'
    return common_prompt.rstrip()+'\n\n'+schema+f"\nQuestion ID: {question['id']}\nQuestion: {question['question']}\nAuthorized scope label: {question['organization_id']} / {question['knowledge_space_id']}\nCommand: `{command}`\n"

def write_assignment(path,common_prompt,question,session,port,repo_root):
    text=build_prompt(common_prompt,question,session,port,repo_root)
    path=Path(path);path.write_text(text);path.chmod(0o600)
    return {'question_id':question['id'],'organization_id':question['organization_id'],'knowledge_space_id':question['knowledge_space_id'],'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'capability_sha256':session['token_sha256'],'client_is_absolute':True}

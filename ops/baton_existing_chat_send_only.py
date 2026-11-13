"""Pilot send-only variant of one source-bound authorized existing-chat turn.

No blind resend, never reprocess historical uncertain jobs, preserve the
legacy PAUSE_UI_WRITES file bit-for-bit. Shared Baton browser-write lock.
This is *not* a worker scheduler or independent multi-LLM wake service.
"""
import argparse,asyncio,fcntl,hashlib,json,os,signal,sqlite3,sys,tempfile,time,uuid
from pathlib import Path
H=Path.home()
B=H/'.local/share/baton/releases/00f0d4d0c0c7ec74ebb1618712e22a210c43fd71'
sys.path[:0]=[str(B),str(H/'GTRCM-newborn-bootstrap/browser-test')]
from baton_chat_observe import inspect_delivery_script,verified_reply_observation
from baton_embedded_send import prepare_send_script,send_click_script
from baton_ui_pause import ui_writes_paused
from rolf_mailbox import Browser,SNAPSHOT_JS,last_user_key,norm
PAUSE=H/'GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES'
LOCK=H/'GTRCM-newborn-bootstrap/browser-test/rolf_chat_shared.lock'
ROOT=H/'.local/state/baton/continuity'

def atomic_write(path,obj,create=False):
    if create and (path.exists() or path.is_symlink()):raise RuntimeError('request ID collision')
    fd,tmp=tempfile.mkstemp(prefix='.baton-message-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(obj,out,ensure_ascii=False,indent=2,sort_keys=True)
            out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

async def main(args):
    target='https://chatgpt.com/c/'+args.chat_id
    request_id='BATON-FRESH-'+uuid.uuid4().hex.upper()
    text=args.body.read_text(encoding='utf-8').strip()
    body='[Avsender: en faktisk ChatGPT-kjøring i Martins samtale via Baton på Greg. Dette er IKKE 🍪/Martin. Ny, uavhengig invitasjon ID '+request_id+'. Mottaker: '+args.name+' eksisterende /c/'+args.chat_id+'. Ingen tidligere uavklart melding gjensendes.]\n\n'+text
    if not 0<len(body)<=4000:raise RuntimeError('outgoing turn length invalid')
    if not PAUSE.is_file() or not ui_writes_paused():raise RuntimeError('old historical pause not present')
    if not LOCK.exists():raise RuntimeError('shared browser lock missing')
    if not (B/'.git').is_dir():raise RuntimeError('pinned release missing')
    if not (H/'.local/state/baton/diagnostics/siv_full_sweep_result.json').is_file():raise RuntimeError('previous independent witness absent')
    c=sqlite3.connect('file:'+str((H/'GTRCM-newborn-bootstrap/transport/mailbox.sqlite3').resolve())+'?mode=ro',uri=True,timeout=2)
    ready=c.execute("SELECT count(*) FROM jobs WHERE status='ready'").fetchone()[0]
    historical=c.execute("SELECT status FROM jobs WHERE id='ROLF-20261108-CONTINUATION-SIV-NEWROUND-04'").fetchone()
    c.close()
    if ready!=0 or historical!=('needs_review',):raise RuntimeError('historical queue no longer quiescent')
    path=ROOT/(request_id.lower()+'.json')
    paused_copy=PAUSE.with_name('PAUSE_UI_WRITES.scoped-'+request_id.lower())
    if paused_copy.exists():raise RuntimeError('hold name collision')
    receipt={'request_id':request_id,'target_url':target,'name':args.name,'outgoing_text':body,'outgoing_sha256':hashlib.sha256(body.encode()).hexdigest(),'created':time.time(),'status':'intent_recorded_not_sent','old_job_id':'ROLF-20261108-CONTINUATION-SIV-NEWROUND-04','old_job_preserved':True,'return_id':None}
    atomic_write(path,receipt,create=True)
    b=Browser('http://127.0.0.1:9335')
    import websockets
    page=b.page()
    try:
      with LOCK.open('a+') as lockfile:
        fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        async with websockets.connect(page['webSocketDebuggerUrl'],max_size=40000000) as ws:
          s=await b.value(ws,1,SNAPSHOT_JS)
          if s['url']!=target or s['title']!=args.name or not s.get('source_bound') or not s.get('schema_ok') or s.get('busy') or s.get('draft','').strip() or s.get('composer_count')!=1 or s.get('load_error'):
            raise RuntimeError('recipient not exact, stable, source-bound and empty')
          if not s.get('messages') or s['messages'][-1]['role']!='assistant':
            raise RuntimeError('recipient not at an idle assistant turn')
          receipt['preflight']={'last_assistant_id':s['messages'][-1]['key'],'source_bound':True,'empty_draft':True,'message_count_visible':len(s['messages'])}
          atomic_write(path,receipt)
          if args.expected_last and s['messages'][-1]['key']!=args.expected_last:raise RuntimeError('conversation changed before new message')
          current_key=last_user_key(s)
          hold_digest=hashlib.sha256(PAUSE.read_bytes()).hexdigest()
          lifted=False;click=False
          try:
            os.replace(PAUSE,paused_copy);lifted=True
            if ui_writes_paused():raise RuntimeError('pause not lifted for new authorized message')
            prepared=await b.value(ws,2,prepare_send_script(body))
            if not isinstance(prepared,dict) or not prepared.get('ok'):
              receipt['status']='composer_rejected_not_sent';receipt['reason']=str(prepared)[:300]
            else:
              await asyncio.sleep(0.5)
              check=await b.value(ws,3,SNAPSHOT_JS)
              if check['url']!=target or check['title']!=args.name or not check.get('source_bound') or check['busy'] or norm(check['draft'])!=norm(body) or last_user_key(check)!=current_key:
                receipt['status']='draft_filled_preclick_context_failed';receipt['reason']='no Send click'
              else:
                # Only one attempt; even unknown returned state must not retry.
                receipt['status']='click_intent_durable';atomic_write(path,receipt)
                outcome=await b.value(ws,4,send_click_script(body))
                if isinstance(outcome,dict) and outcome.get('ok'):
                  click=True;receipt['status']='send_click_attempted_no_delivery_proof'
                  print('CLICK_ATTEMPT',request_id,args.name,flush=True)
                else:
                  receipt['status']='send_result_uncertain_no_retry'
                  receipt['reason']=str(outcome)[:300]
            atomic_write(path,receipt)
          finally:
            if lifted and paused_copy.exists():
              if PAUSE.exists():raise RuntimeError('original pause unexpectedly recreated; reviewed copy retained')
              os.replace(paused_copy,PAUSE)
              print('HISTORIC_HOLD_RESTORED',hashlib.sha256(PAUSE.read_bytes()).hexdigest()==hold_digest,flush=True)
            if not PAUSE.exists():raise RuntimeError('original pause restoration failure')
        fcntl.flock(lockfile,fcntl.LOCK_UN)
    except BaseException as e:
      if paused_copy.exists() and not PAUSE.exists():
        os.replace(paused_copy,PAUSE)
      receipt['error']=type(e).__name__+': '+str(e)[:300]
      atomic_write(path,receipt)
      raise
    if not click:
      print('NOT_SENT_OR_UNCERTAIN',receipt['status'],request_id,flush=True)
      return
    if args.send_only:
      print('SEND_ATTEMPT_PENDING_NO_REPLY_PROOF', request_id, str(path), flush=True)
      return
    async with websockets.connect(page['webSocketDebuggerUrl'],max_size=40000000) as ws:
      for n in range(75):
        await asyncio.sleep(1.8)
        v=await b.value(ws,100+n,inspect_delivery_script(body))
        if verified_reply_observation(v):
          reply=v.get('assistantText','')
          receipt['status']='reply_observed_in_exact_chat'
          receipt['return_id']=v['assistantMessageId']
          receipt['return_text']=reply
          receipt['return_sha256']=hashlib.sha256(reply.encode()).hexdigest()
          receipt['reply_observed_at']=time.time()
          atomic_write(path,receipt)
          print('VERIFIED_REPLY',args.name,request_id,v['assistantMessageId'],flush=True)
          print('REPLY_TEXT',reply[:6100],flush=True)
          return
        if n%8==0:print('WAIT',n,v.get('userVisible'),v.get('replyVisible'),v.get('reason'),flush=True)
    receipt['status']='reply_timeout_no_retry';atomic_write(path,receipt)
    print('NO_REPLY_VERIFIED',request_id,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--chat-id',required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--body',required=True,type=Path)
    p.add_argument('--expected-last')
    p.add_argument('--send-only',action='store_true',help='Release after one send attempt; verify later without resend')
    args=p.parse_args()
    asyncio.run(main(args))

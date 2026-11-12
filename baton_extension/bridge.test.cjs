"use strict";
const {readFileSync}=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const test=require("node:test");
const crypto=require("node:crypto").webcrypto;
const {spawnSync}=require("node:child_process");

const CHAT="6aef828e-0150-83eb-bbac-061f79a8fd4a";
const NONCE="a".repeat(32);
const REQ="b".repeat(32);

class Textarea {
  constructor(){this._value="";this.isConnected=true;this.tagName="TEXTAREA";}
  set value(x){this._value=x;}
  get value(){return this._value;}
  getBoundingClientRect(){return {width:250,height:60};}
  closest(name){return name==="form"?form:null;}
  focus(){}
  dispatchEvent(){}
}
let editor;
let form;
let sent;

function harness(){
  sent=[];
  editor=new Textarea();
  const button={
    isConnected:true,disabled:false,
    getBoundingClientRect:()=>({width:25,height:20}),
    getAttribute:()=>null,
    click:()=>{sent.push(editor.value);editor.value="";}
  };
  form={querySelectorAll:(s)=>s.includes("composer-submit-button")?[button]:[]};
  const controls=new Map();
  const start={disabled:false,addEventListener:(name,fn)=>controls.set("start",fn)};
  const stop={disabled:true,addEventListener:(name,fn)=>controls.set("stop",fn)};
  const status={textContent:""};
  const root={innerHTML:"",getElementById:id=>({start,stop,status})[id]};
  let listener;
  let poll;
  let assistant="";
  const messages=[];
  const writeResults=[];
  const document={
    getElementById:()=>null,
    createElement:()=>({id:"",style:{},attachShadow:()=>root}),
    documentElement:{appendChild:()=>{}},
    querySelectorAll:(selector)=>{
      if(selector==="#prompt-textarea") return [editor];
      if(selector==='[data-message-author-role="assistant"]')
        return assistant?[{querySelector:()=>({innerText:assistant})}]:[];
      return [];
    }
  };
  const chrome={
    runtime:{
      lastError:null,
      sendMessage:(payload,callback)=>{
        messages.push(payload);
        if (payload.op==="ui_write_check") {
          const allowed=writeResults.length ? writeResults.shift() : true;
          callback?.(allowed
            ? {ok:true,op:"ui_write_allowed",chat_id:payload.chat_id,check_id:payload.check_id}
            : {ok:false,error:"ui-writes-paused",check_id:payload.check_id});
        } else callback?.({queued:true});
      },
      onMessage:{addListener:fn=>listener=fn}
    }
  };
  const ctx={
    document,chrome,location:{origin:"https://chatgpt.com",pathname:"/c/"+CHAT},
    crypto,getComputedStyle:()=>({visibility:"visible",display:"block"}),
    HTMLTextAreaElement:Textarea,
    Event:class{},InputEvent:class{},
    setInterval:fn=>poll=fn,
    setTimeout:(fn,delay)=>{if(delay >= 3500) return 42; fn(); return 1;},
    clearTimeout:()=>{}
  };
  const source=readFileSync(path.join(__dirname,"content.js"),"utf8");
  vm.runInNewContext(source,ctx,{timeout:1000});
  return {
    ctx,controls,chrome,status,start,stop,messages,sent,
    receive:reply=>listener({type:"baton-native",reply}),
    poll:()=>poll(),
    setAssistant:x=>{assistant=x;},
    setWriteResults:(...states)=>writeResults.push(...states),
    writeChecks:()=>messages.filter(x=>x.op==="ui_write_check")
  };
}

async function flush(){
  await new Promise(resolve=>setImmediate(resolve));
  await new Promise(resolve=>setImmediate(resolve));
}

test("one explicit activation creates one message in the original chat",async()=>{
  const h=harness();
  assert.equal(h.messages.length,0);
  h.controls.get("start")();
  assert.equal(h.messages.length,1);
  assert.equal(h.messages[0].op,"arm");
  assert.equal(h.messages[0].chat_id,CHAT);
  assert.equal(h.sent.length,0);
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  assert.equal(h.sent.length,1);
  assert.match(h.sent[0],/BATON_TOOL_V2 a{32} [0-9a-f]{32} 15/);
  assert.match(h.sent[0],/bridge-proof-/);
  const frame=h.sent[0].split("\n").find(s=>s.startsWith("BATON_TOOL_V2 "));
  assert.ok(frame, "bootstrap contains exactly one tool line");
  const verify=spawnSync("python3",["-c",
    "import shlex,sys; f=shlex.split(sys.argv[1]); assert f[0]=='BATON_TOOL_V2'; assert f[6]=='/usr/bin/python3'; assert f[7]=='-c'; compile(f[8], '<baton-bootstrap>', 'exec')",
    frame],{encoding:"utf8"});
  assert.equal(verify.status,0,verify.stderr);
  assert.equal(h.stop.disabled,false);
});

test("one command is sent once; native result returned to same chat",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  const command="BATON_TOOL_V2 "+NONCE+" "+REQ+" 10 /home/olliver -- /usr/bin/hostname";
  h.setAssistant(command);
  h.poll();
  h.poll();
  assert.equal(h.messages.filter(x=>x.op==="execute_frame").length,1);
  h.receive({ok:true,op:"tool_result",chat_id:CHAT,request_id:REQ,
    frame:"BATON_TOOL_RESULT_V1 "+NONCE+" "+REQ+"\n"+
      '{"exit_code":0,"output":"Greg"}\nEND_BATON_TOOL_RESULT_V1'});
  await flush();
  assert.equal(h.sent.length,2);
  assert.match(h.sent[1],/BATON_TOOL_RESULT_V1/);
  h.poll();
  assert.equal(h.messages.filter(x=>x.op==="execute_frame").length,1);
});

test("page navigation automatically revokes access without a second execution",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  h.ctx.location.pathname="/c/6af04e14-3e68-83eb-b53b-e4b352c84091";
  h.poll();
  assert.equal(h.messages.at(-1).op,"stop");
  assert.equal(h.start.disabled,false);
  assert.equal(h.messages.filter(x=>x.op==="execute_frame").length,0);
});

test("explicit Stop disconnects even when no command has been run",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  h.controls.get("stop")();
  assert.equal(h.messages.at(-1).op,"stop");
  assert.equal(h.start.disabled,false);
});

test("one Bootstrap send requires two distinct host safety checks",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  assert.equal(h.sent.length,1);
  const checks=h.writeChecks();
  assert.equal(checks.length,2);
  assert.equal(checks[0].chat_id,CHAT);
  assert.notEqual(checks[0].check_id,checks[1].check_id);
});

test("host pause before drafting blocks Brave Bootstrap without UI send",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.setWriteResults(false);
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  assert.equal(h.sent.length,0);
  assert.equal(editor.value,"");
  assert.equal(h.writeChecks().length,1);
  assert.match(h.status.textContent,/sperre|usikkert/);
});

test("host pause arriving at final click prevents Brave send",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.setWriteResults(true,false);
  h.receive({ok:true,op:"armed",chat_id:CHAT,nonce:NONCE,cwd:"/home/olliver"});
  await flush();
  assert.equal(h.writeChecks().length,2);
  assert.equal(h.sent.length,0);
  assert.ok(editor.value.trim(),"unsent exact draft is preserved, not retried");
  assert.match(h.status.textContent,/sperre|usikkert/);
});

test("native arm rejection never writes into ChatGPT",async()=>{
  const h=harness();
  h.controls.get("start")();
  h.receive({ok:false,error:"ui-writes-paused"});
  await flush();
  assert.equal(h.sent.length,0);
  assert.equal(h.writeChecks().length,0);
  assert.equal(h.start.disabled,false);
});

// Exercise the actual Save As function using isolated file-picker/browser adapters.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../bigdelta/static/app.js'),'utf8');
const implementation=source.slice(source.indexOf('async function savePackage('),source.indexOf('function newProject('));
async function scenario(mode) {
  const calls=[], control={disabled:false}, payload=Buffer.from('%PDF sample');
  const context={
    project:()=>({packages:[{id:'pkg12345',filename:'BD-200-draft.pdf'}]}),
    toast:message=>calls.push(['toast',message]),
    fetch:async url=>{calls.push(['fetch',url]);return {ok:true,blob:async()=>payload};},
    window:{},document:{createElement:()=>({click(){calls.push(['download',this.href,this.download]);}})}
  };
  if(mode!=='fallback')context.window.showSaveFilePicker=async options=>{
    calls.push(['picker',options.suggestedName]);
    if(mode==='cancel'){const e=new Error('Canceled');e.name='AbortError';throw e;}
    return {name:'chosen.pdf',createWritable:async()=>({
      write:async data=>{calls.push(['write',data]);if(mode==='write-error')throw new Error('Disk full');},
      close:async()=>calls.push(['close']),abort:async()=>calls.push(['abort'])
    })};
  };
  vm.createContext(context);vm.runInContext(implementation,context);
  let failure;
  try{await context.savePackage('pkg12345',control);}catch(e){failure=e;}
  assert.equal(control.disabled,false);
  if(mode==='success'){
    assert.equal(calls[0][0],'picker');assert.equal(calls[0][1],'BD-200-draft.pdf');
    assert.deepEqual(calls.find(x=>x[0]==='write')[1],payload);assert.ok(calls.some(x=>x[0]==='close'));
  }else if(mode==='cancel'){
    assert.equal(failure,undefined);assert.equal(calls.length,1);
  }else if(mode==='write-error'){
    assert.match(failure.message,/Disk full/);assert.ok(calls.some(x=>x[0]==='abort'));assert.ok(!calls.some(x=>x[0]==='close'));
  }else{
    assert.deepEqual(calls[0],['download','/download/pkg12345','BD-200-draft.pdf']);
  }
}
(async()=>{for(const mode of ['success','cancel','write-error','fallback'])await scenario(mode);console.log('4 Save As checks passed.');})().catch(e=>{console.error(e);process.exitCode=1;});
